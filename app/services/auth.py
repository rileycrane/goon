from datetime import datetime

from app.db.database import db


async def get_user(phone: str) -> dict | None:
    """Look up a user by phone number (E.164 format)."""
    return await db.fetch_one(
        "SELECT * FROM users WHERE phone = ?", [phone]
    )


def is_user_active(user: dict) -> bool:
    """Check if a user has an active subscription or valid trial."""
    if user["allowlisted"]:
        return True
    status = user["subscription_status"]
    if status == "active":
        return True
    if status == "trial" and user["trial_ends_at"]:
        trial_end = datetime.fromisoformat(user["trial_ends_at"])
        if trial_end > datetime.now():
            return True
    return False


async def create_user(
    phone: str,
    name: str,
    email: str,
    stripe_customer_id: str,
    subscription_status: str = "active",
    trial_ends_at: str | None = None,
    allowlisted: bool = False,
) -> dict:
    """Create a new user record. ID = phone number."""
    await db.execute(
        """INSERT INTO users (id, phone, name, email, stripe_customer_id,
           subscription_status, trial_ends_at, allowlisted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            phone,
            phone,
            name,
            email,
            stripe_customer_id,
            subscription_status,
            trial_ends_at,
            allowlisted,
        ],
    )
    return await get_user(phone)  # type: ignore[return-value]


async def update_subscription_status(phone: str, status: str) -> None:
    """Update a user's subscription status.

    Valid statuses: trial, active, past_due, canceled.
    """
    await db.execute(
        "UPDATE users SET subscription_status = ? WHERE phone = ?",
        [status, phone],
    )


async def set_stripe_customer_id(phone: str, customer_id: str) -> None:
    """Link a Stripe customer ID to a user."""
    await db.execute(
        "UPDATE users SET stripe_customer_id = ? WHERE phone = ?",
        [customer_id, phone],
    )
