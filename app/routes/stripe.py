import logging

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.services.billing import (
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_subscription_updated,
)

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
                from app.services.sms import send_sms

                if was_upgrade:
                    await send_sms(
                        user["phone"],
                        "You're in. I can make calls for you now -- "
                        "20 per month. Text me what you need.",
                    )
                else:
                    name = user.get("name") or "there"
                    await send_sms(
                        user["phone"],
                        f"Hey {name}, this is Hold Plz. Text me when you "
                        "need something done -- restaurant reservations, business "
                        "questions, anything. I'll handle it.",
                    )

        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(data)

        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(data)
    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)
        raise HTTPException(status_code=500, detail="Webhook handler error")

    return {"status": "ok"}
