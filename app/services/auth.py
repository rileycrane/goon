"""User auth — lookup, subscription check, tier management."""
from __future__ import annotations

from datetime import datetime

from app.db.database import db


async def get_user(phone: str) -> dict | None:
    """Look up a user by phone number (E.164 format)."""
    return await db.fetch_one(
        "SELECT * FROM users WHERE phone = ?", [phone]
    )


def get_user_tier(user: dict) -> str:
    """Return the effective tier: 'active', 'free', or 'none'.

    - active: paying subscriber or allowlisted or valid trial
    - free: free tier user (status='free')
    - none: canceled, past_due, expired trial
    """
    if user["allowlisted"]:
        return "active"
    status = user["subscription_status"]
    if status == "active":
        return "active"
    if status == "trial" and user.get("trial_ends_at"):
        trial_end = datetime.fromisoformat(user["trial_ends_at"])
        if trial_end > datetime.now():
            return "active"
    if status == "free":
        return "free"
    return "none"


def is_user_active(user: dict) -> bool:
    """Check if a user has an active subscription or valid trial."""
    return get_user_tier(user) == "active"


async def is_authorized(phone: str) -> bool:
    """Check if a phone number is authorized to use Hold Plz."""
    user = await get_user(phone)
    if user is None:
        return False
    return is_user_active(user)


async def create_user(
    phone: str,
    name: str = "",
    email: str = "",
    stripe_customer_id: str = "",
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


async def create_free_user(phone: str) -> dict:
    """Create a free-tier user record."""
    return await create_user(
        phone=phone,
        subscription_status="free",
    )


async def increment_free_message_count(phone: str) -> int:
    """Increment free_messages_used and return the new count."""
    await db.execute(
        "UPDATE users SET free_messages_used = free_messages_used + 1 WHERE phone = ?",
        [phone],
    )
    user = await get_user(phone)
    return user["free_messages_used"] if user else 0


def is_free_tier_exhausted(user: dict, limit: int) -> bool:
    """Check if a free-tier user has used all their free messages."""
    return user.get("free_messages_used", 0) >= limit


async def is_call_quota_available(user: dict, quota: int) -> bool:
    """Check if a paying user has calls remaining this period."""
    if user["allowlisted"]:
        return True
    return user.get("calls_used_this_period", 0) < quota


async def increment_call_count(phone: str) -> None:
    """Increment calls_used_this_period for a user."""
    await db.execute(
        "UPDATE users SET calls_used_this_period = calls_used_this_period + 1 WHERE phone = ?",
        [phone],
    )


async def reset_call_count(phone: str) -> None:
    """Reset call count and update billing period start (on subscription renewal)."""
    await db.execute(
        """UPDATE users SET calls_used_this_period = 0,
           billing_period_start = CURRENT_TIMESTAMP
           WHERE phone = ?""",
        [phone],
    )


async def update_subscription_status(phone: str, status: str) -> None:
    """Update a user's subscription status.

    Valid statuses: free, trial, active, past_due, canceled.
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


async def get_signups_enabled() -> bool:
    """Check if signups are enabled (runtime toggle via app_settings table)."""
    row = await db.fetch_one(
        "SELECT value FROM app_settings WHERE key = 'signups_enabled'"
    )
    if row is None:
        return True  # default to enabled
    return row["value"] == "true"


async def set_signups_enabled(enabled: bool) -> None:
    """Toggle signups_enabled in app_settings."""
    value = "true" if enabled else "false"
    await db.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES ('signups_enabled', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP""",
        [value, value],
    )
