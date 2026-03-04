import asyncio
import logging

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.db.database import db
from app.services.billing import (
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_subscription_updated,
)
from app.services.llm import create as llm_create, extract_text
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = settings.stripe_secret_key


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
):
    """Handle Stripe webhook events.

    Verifies the webhook signature, then routes to the appropriate handler.
    """
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook: event_type=%s id=%s", event_type, event.get("id", "?"))

    try:
        if event_type == "checkout.session.completed":
            logger.info(
                "Checkout completed: customer=%s client_ref=%s mode=%s",
                data.get("customer"), data.get("client_reference_id"), data.get("mode"),
            )
            user, was_upgrade = await handle_checkout_completed(data)
            logger.info(
                "Checkout result: user=%s was_upgrade=%s",
                user.get("phone") if user else None, was_upgrade,
            )
            if user:
                # Run welcome message and re-trigger as INDEPENDENT tasks
                # so failure in one doesn't block the other
                asyncio.create_task(_send_welcome_sms(user, was_upgrade))
                asyncio.create_task(_retrigger_paywalled_request(user))

        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(data)

        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(data)
    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)
        raise HTTPException(status_code=500, detail="Webhook handler error")

    return {"status": "ok"}


async def _send_welcome_sms(user: dict, was_upgrade: bool) -> None:
    """Generate and send a welcome message. Falls back to static text on LLM failure."""
    phone = user["phone"]
    name = user.get("name") or "there"
    plan_type = user.get("plan_type", "basic")
    plan_desc = (
        "monthly plan ($9.99/mo, calls included)"
        if plan_type == "basic"
        else "pay-per-request plan ($1 per answered question)"
    )

    try:
        resp = await llm_create(
            messages=[{
                "role": "user",
                "content": (
                    f"Generate a welcome SMS for {name} who just signed up for Hold Plz ({plan_desc}).\n"
                    f"{'This is an upgrade from free tier.' if was_upgrade else 'This is a new signup.'}\n\n"
                    "Rules:\n"
                    "- Under 160 chars if possible, 320 max\n"
                    "- No emoji, no markdown\n"
                    "- Warm, casual, like a friend\n"
                    "- Don't be salesy or corporate\n"
                    "- Sign off as Hold Plz only if it's a new user who hasn't interacted yet\n\n"
                    "Return ONLY the SMS text."
                ),
            }],
            max_tokens=200,
            tier="standard",
        )
        welcome_text = extract_text(resp)
        if welcome_text:
            await send_sms(phone, welcome_text.strip())
            return
    except Exception:
        logger.exception("LLM welcome message failed for %s", phone)

    # Static fallback — always works, no LLM needed
    await send_sms(phone, f"Hey {name}, you're all set with Hold Plz. Text me what you need.")


async def _retrigger_paywalled_request(user: dict) -> None:
    """If the user had a paywalled request, replay it now that they've paid.

    This runs independently from the welcome message. If this fails,
    the user can just text again and it'll work (payment is recorded).
    """
    phone = user["phone"]

    try:
        recent_msgs = await db.fetch_all(
            "SELECT direction, body FROM message_log WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            [phone],
        )
        if not recent_msgs:
            return

        # Walk newest-first: find the paywall outbound (contains buy.stripe.com),
        # then find the first inbound BEFORE it that's longer than 5 chars
        # (skip "Y", "yes", "pay" etc which are consent/payment replies)
        paywalled_body = None
        found_paywall = False
        for m in recent_msgs:
            if not found_paywall:
                if m["direction"] == "out" and "buy.stripe.com" in (m.get("body") or ""):
                    found_paywall = True
            else:
                if m["direction"] == "in":
                    body = (m.get("body") or "").strip()
                    if len(body) > 5:
                        paywalled_body = body
                        break

        if not paywalled_body:
            return

        logger.info("Re-triggering paywalled request for %s: %s", phone, paywalled_body[:80])
        from app.services.orchestrator import handle_message
        result = await handle_message(
            phone, paywalled_body, is_free_tier=False, skip_payment_gate=True,
        )
        if result:
            await send_sms(phone, result)

    except Exception:
        logger.exception("Failed to re-trigger paywalled request for %s", phone)
