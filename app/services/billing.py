import stripe

from app.config import settings
from app.db.database import db
from app.services.auth import (
    create_user,
    get_user,
    set_stripe_customer_id,
    update_subscription_status,
)

stripe.api_key = settings.stripe_secret_key


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


async def handle_checkout_completed(session: dict) -> dict | None:
    """Process a successful Stripe checkout.

    Creates the user record and returns the new user, or None if
    the user already exists.
    """
    customer_id = session["customer"]
    metadata = session.get("metadata", {})
    phone = metadata.get("goon_phone", "")
    name = metadata.get("goon_name", "")

    if not phone:
        return None

    # Get email from customer object
    customer = stripe.Customer.retrieve(customer_id)
    email = customer.get("email", "")

    existing = await get_user(phone)
    if existing:
        # Re-subscribing user: update status
        await update_subscription_status(phone, "active")
        await set_stripe_customer_id(phone, customer_id)
        return await get_user(phone)

    return await create_user(
        phone=phone,
        name=name,
        email=email,
        stripe_customer_id=customer_id,
        subscription_status="active",
    )


async def handle_subscription_updated(subscription: dict) -> None:
    """Handle subscription status changes from Stripe webhooks."""
    customer_id = subscription["customer"]
    status = subscription["status"]

    # Map Stripe status to our status
    status_map = {
        "active": "active",
        "past_due": "past_due",
        "canceled": "canceled",
        "unpaid": "past_due",
        "incomplete": "trial",
        "incomplete_expired": "canceled",
        "trialing": "trial",
    }
    goon_status = status_map.get(status, "canceled")

    user = await _get_user_by_stripe_id(customer_id)
    if user:
        await update_subscription_status(user["phone"], goon_status)


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
