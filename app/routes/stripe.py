"""Stripe webhook — handles subscription lifecycle events."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events (subscription changes, payments)."""
    # TODO: verify signature, handle checkout.session.completed,
    #       customer.subscription.updated, customer.subscription.deleted
    return {"status": "ok"}
