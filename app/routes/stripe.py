import asyncio
import logging

import anthropic
import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.db.database import db
from app.services.billing import (
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_subscription_updated,
)
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

    try:
        if event_type == "checkout.session.completed":
            user, was_upgrade = await handle_checkout_completed(data)
            if user:
                asyncio.create_task(
                    _send_welcome_message(user, was_upgrade)
                )

        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(data)

        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(data)
    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)
        raise HTTPException(status_code=500, detail="Webhook handler error")

    return {"status": "ok"}


async def _send_welcome_message(user: dict, was_upgrade: bool) -> None:
    """Generate and send an LLM-crafted welcome message after payment.

    If there's a pending request from before the upgrade, pick it back up.
    """
    try:
        phone = user["phone"]
        name = user.get("name") or "there"
        plan_type = user.get("plan_type", "basic")

        # Check for pending/open requests this user had before paying
        pending_requests = await db.fetch_all(
            """SELECT r.task_summary, r.task_type, s.business_name
               FROM requests r JOIN sessions s ON r.session_id = s.id
               WHERE s.user_id = ? AND r.status IN ('open', 'pending_call')
               ORDER BY r.created_at DESC LIMIT 3""",
            [phone],
        )

        # Also check recent messages for context
        recent_msgs = await db.fetch_all(
            "SELECT direction, body FROM message_log WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            [phone],
        )

        pending_context = ""
        if pending_requests:
            items = [f"- {r['business_name']}: {r['task_summary']}" for r in pending_requests]
            pending_context = f"\n\nPending requests from before payment:\n" + "\n".join(items)

        recent_context = ""
        if recent_msgs:
            lines = []
            for m in reversed(recent_msgs):
                prefix = "User" if m["direction"] == "in" else "Hold Plz"
                lines.append(f"{prefix}: {m['body']}")
            recent_context = f"\n\nRecent conversation:\n" + "\n".join(lines)

        plan_desc = "monthly plan ($9.99/mo, calls included)" if plan_type == "basic" else "pay-per-request plan ($1 per answered question)"

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"""Generate a welcome SMS for {name} who just signed up for Hold Plz ({plan_desc}).
{"This is an upgrade from free tier." if was_upgrade else "This is a new signup."}
{pending_context}
{recent_context}

Rules:
- Under 160 chars if possible, 320 max
- No emoji, no markdown
- Warm, casual, like a friend
- If there's a pending request, acknowledge it and say you're picking it back up
- If no pending request, welcome them and suggest something concrete they could try (restaurant reservation, checking business hours, etc.)
- Don't be salesy or corporate
- Sign off as Hold Plz only if it's a new user who hasn't interacted yet

Return ONLY the SMS text.""",
            }],
        )
        welcome_text = response.content[0].text.strip()

        await send_sms(phone, welcome_text)

        # If there were pending requests from a gated call attempt, re-trigger them
        if was_upgrade and pending_requests:
            for req in pending_requests:
                if req["task_type"] in ("reservation", "appointment", "custom_request"):
                    # The user can just text again — the welcome message will prompt them
                    pass

    except Exception:
        logger.exception("Failed to send welcome message to %s", user.get("phone"))
        # Fallback to static message
        try:
            name = user.get("name") or "there"
            await send_sms(
                user["phone"],
                f"Hey {name}, you're all set with Hold Plz. Text me what you need.",
            )
        except Exception:
            logger.exception("Failed to send fallback welcome message")
