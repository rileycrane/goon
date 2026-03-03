import logging
import urllib.parse

import stripe

from app.config import settings
from app.db.database import db
from app.services.auth import (
    create_user,
    get_user,
    reset_call_count,
    set_stripe_customer_id,
    update_subscription_status,
)

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


async def send_payment_link(phone: str) -> None:
    """Send Stripe Payment Link URL via SMS with client_reference_id."""
    from app.services.sms import send_sms

    if not settings.stripe_payment_link_url:
        await send_sms(
            phone,
            "Payment isn't set up yet. Hang tight -- we'll have it ready soon.",
        )
        return

    # Append client_reference_id so webhook can identify the phone
    url = (
        f"{settings.stripe_payment_link_url}"
        f"?client_reference_id={urllib.parse.quote(phone)}"
    )
    await send_sms(
        phone,
        f"Here's your link to upgrade Hold Plz ($19.99/mo, 20 calls): {url}",
    )


async def create_checkout_session(
    phone: str, name: str, email: str
) -> str:
    """Create a Stripe Checkout session for new subscriber signup.

    Returns the checkout session URL to redirect the user to.
    """
    customer = stripe.Customer.create(
        email=email,
        name=name,
        phone=phone,
        metadata={"goon_phone": phone},
    )

    session = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        line_items=[
            {
                "price": settings.stripe_price_id,
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url=f"{settings.base_url}/signup/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.base_url}/signup",
        metadata={"goon_phone": phone, "goon_name": name},
    )

    return session.url


async def handle_checkout_completed(session: dict) -> tuple[dict | None, bool]:
    """Process a successful Stripe checkout.

    Returns (user, was_upgrade) — was_upgrade is True if user went from free→active.
    """
    customer_id = session["customer"]
    metadata = session.get("metadata", {})

    # Check both metadata.goon_phone and client_reference_id for phone
    phone = metadata.get("goon_phone", "")
    if not phone:
        phone = session.get("client_reference_id", "")
    name = metadata.get("goon_name", "")

    if not phone:
        return None, False

    customer = stripe.Customer.retrieve(customer_id)
    email = customer.get("email", "")

    existing = await get_user(phone)
    if existing:
        was_free = existing["subscription_status"] == "free"
        await update_subscription_status(phone, "active")
        await set_stripe_customer_id(phone, customer_id)
        await reset_call_count(phone)
        return await get_user(phone), was_free

    user = await create_user(
        phone=phone,
        name=name,
        email=email,
        stripe_customer_id=customer_id,
        subscription_status="active",
    )
    await reset_call_count(phone)
    return user, False


async def handle_subscription_updated(subscription: dict) -> None:
    """Handle subscription status changes from Stripe webhooks."""
    customer_id = subscription["customer"]
    status = subscription["status"]

    status_map = {
        "active": "active",
        "past_due": "past_due",
        "canceled": "canceled",
        "unpaid": "past_due",
        "incomplete": "trial",
        "incomplete_expired": "canceled",
        "trialing": "trial",
    }
    holdplz_status = status_map.get(status, "canceled")

    user = await _get_user_by_stripe_id(customer_id)
    if user:
        await update_subscription_status(user["phone"], holdplz_status)
        # Reset call count on renewal (status going back to active)
        if holdplz_status == "active" and user["subscription_status"] != "active":
            await reset_call_count(user["phone"])


async def handle_subscription_deleted(subscription: dict) -> None:
    """Handle subscription cancellation."""
    customer_id = subscription["customer"]
    user = await _get_user_by_stripe_id(customer_id)
    if user:
        await update_subscription_status(user["phone"], "canceled")


async def _get_user_by_stripe_id(customer_id: str) -> dict | None:
    """Look up user by Stripe customer ID."""
    return await db.fetch_one(
        "SELECT * FROM users WHERE stripe_customer_id = ?", [customer_id]
    )
