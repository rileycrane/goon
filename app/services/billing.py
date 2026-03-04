from __future__ import annotations

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


def _link_with_ref(base_url: str, phone: str) -> str:
    """Append client_reference_id to a Stripe payment link URL."""
    return f"{base_url}?client_reference_id={urllib.parse.quote(phone)}"


def get_payment_url(phone: str) -> str | None:
    """Return the legacy Stripe Payment Link URL, or None if not configured."""
    if not settings.stripe_payment_link_url:
        return None
    return _link_with_ref(settings.stripe_payment_link_url, phone)


def get_payment_options(phone: str) -> dict[str, str]:
    """Return available payment links for a phone number.

    Returns a dict with keys 'basic' and/or 'request', each mapping to a URL.
    Falls back to legacy 'stripe_payment_link_url' if the new ones aren't set.
    """
    options: dict[str, str] = {}
    if settings.stripe_payment_link_basic:
        options["basic"] = _link_with_ref(settings.stripe_payment_link_basic, phone)
    if settings.stripe_payment_link_request:
        options["request"] = _link_with_ref(settings.stripe_payment_link_request, phone)
    # Fallback to legacy single link
    if not options and settings.stripe_payment_link_url:
        options["basic"] = _link_with_ref(settings.stripe_payment_link_url, phone)
    return options


async def send_payment_link(phone: str) -> None:
    """Send Stripe Payment Link URL(s) via SMS with client_reference_id."""
    from app.services.sms import send_sms

    options = get_payment_options(phone)
    if not options:
        await send_sms(
            phone,
            "Payment isn't set up yet. Hang tight -- we'll have it ready soon.",
        )
        return

    if "basic" in options and "request" in options:
        await send_sms(
            phone,
            f"Two ways to use Hold Plz:\n"
            f"Monthly ($9.99/mo): {options['basic']}\n"
            f"Pay per request ($1): {options['request']}",
        )
    elif "basic" in options:
        await send_sms(phone, f"Upgrade Hold Plz ($9.99/mo): {options['basic']}")
    elif "request" in options:
        await send_sms(phone, f"Pay per request ($1): {options['request']}")


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

    logger.info(
        "handle_checkout_completed: phone=%s name=%s customer=%s client_ref=%s",
        phone, name, customer_id, session.get("client_reference_id", ""),
    )

    if not phone:
        logger.warning("handle_checkout_completed: no phone found in session")
        return None, False

    # Normalize phone — Stripe may URL-encode or strip the + prefix
    import urllib.parse
    phone = urllib.parse.unquote(phone)
    if not phone.startswith("+"):
        # Assume US number if 10-11 digits
        digits = phone.lstrip("+")
        if len(digits) == 10:
            phone = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            phone = f"+{digits}"
        else:
            phone = f"+{digits}"

    customer = stripe.Customer.retrieve(customer_id)
    email = customer.get("email", "")

    # Detect plan type from payment link used
    plan_type = _detect_plan_type(session)

    existing = await get_user(phone)
    if existing:
        was_free = existing["subscription_status"] == "free"
        await update_subscription_status(phone, "active")
        await set_stripe_customer_id(phone, customer_id)
        await reset_call_count(phone)
        try:
            await db.execute(
                "UPDATE users SET plan_type = ? WHERE id = ?", [plan_type, phone]
            )
        except Exception:
            logger.debug("plan_type column not yet available, skipping")
        # Also store email if we got it from Stripe
        if email:
            try:
                await db.execute(
                    "UPDATE users SET email = ? WHERE id = ? AND (email IS NULL OR email = '')",
                    [email, phone],
                )
            except Exception:
                pass
        return await get_user(phone), was_free

    user = await create_user(
        phone=phone,
        name=name,
        email=email,
        stripe_customer_id=customer_id,
        subscription_status="active",
    )
    await reset_call_count(phone)
    try:
        await db.execute(
            "UPDATE users SET plan_type = ? WHERE id = ?", [plan_type, phone]
        )
    except Exception:
        logger.debug("plan_type column not yet available, skipping")
    return user, False


def _detect_plan_type(session: dict) -> str:
    """Detect plan type from the Stripe checkout session.

    Checks metadata first, then matches against known payment link IDs.
    """
    metadata = session.get("metadata", {})
    if metadata.get("plan_type"):
        return metadata["plan_type"]

    # Match by payment link ID
    payment_link = session.get("payment_link", "")
    if payment_link:
        from app.config.settings import settings as cfg
        if cfg.stripe_payment_link_request and payment_link == cfg.stripe_payment_link_request.split("?")[0]:
            return "request"
        if cfg.stripe_payment_link_basic and payment_link == cfg.stripe_payment_link_basic.split("?")[0]:
            return "basic"

    # Check mode — subscription = basic, payment = request
    mode = session.get("mode", "")
    if mode == "payment":
        return "request"
    return "basic"


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


async def charge_request(request_id: int, user_id: str) -> None:
    """Charge $1.00 for a resolved request on the pay-per-use plan."""
    user = await get_user(user_id)
    if not user or not user.get("stripe_customer_id"):
        logger.warning("Cannot charge request %d: no Stripe customer for %s", request_id, user_id)
        return

    try:
        # Get default payment method
        customer = stripe.Customer.retrieve(user["stripe_customer_id"])
        payment_method = customer.get("invoice_settings", {}).get("default_payment_method")
        if not payment_method:
            # Try the first attached payment method
            methods = stripe.PaymentMethod.list(
                customer=user["stripe_customer_id"], type="card", limit=1,
            )
            if methods.data:
                payment_method = methods.data[0].id
            else:
                logger.warning("No payment method for user %s, skipping charge", user_id)
                return

        intent = stripe.PaymentIntent.create(
            amount=100,  # $1.00
            currency="usd",
            customer=user["stripe_customer_id"],
            payment_method=payment_method,
            off_session=True,
            confirm=True,
            description=f"Hold Plz request #{request_id}",
            metadata={"request_id": str(request_id), "user_id": user_id},
        )

        await db.execute(
            "UPDATE requests SET charged = TRUE, stripe_charge_id = ?, charged_at = CURRENT_TIMESTAMP WHERE id = ?",
            [intent.id, request_id],
        )
        logger.info("Charged $1.00 for request %d (pi: %s)", request_id, intent.id)

    except stripe.CardError as e:
        logger.warning("Card declined for request %d user %s: %s", request_id, user_id, e)
    except Exception:
        logger.exception("Failed to charge request %d", request_id)


async def verify_payment_method(user_id: str) -> bool:
    """Check if a user has a valid payment method on file."""
    user = await get_user(user_id)
    if not user or not user.get("stripe_customer_id"):
        return False
    try:
        methods = stripe.PaymentMethod.list(
            customer=user["stripe_customer_id"], type="card", limit=1,
        )
        return len(methods.data) > 0
    except Exception:
        logger.exception("Failed to verify payment method for %s", user_id)
        return False


async def _get_user_by_stripe_id(customer_id: str) -> dict | None:
    """Look up user by Stripe customer ID."""
    return await db.fetch_one(
        "SELECT * FROM users WHERE stripe_customer_id = ?", [customer_id]
    )
