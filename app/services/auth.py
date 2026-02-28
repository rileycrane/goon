"""User auth — lookup, subscription check, allowlist."""
from __future__ import annotations

from app.db.database import db


async def get_user(phone: str) -> dict | None:
    """Look up a user by phone number."""
    return await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])


async def is_authorized(phone: str) -> bool:
    """Check if a phone number is authorized to use Goon."""
    user = await get_user(phone)
    if user is None:
        return False
    if user["allowlisted"]:
        return True
    return user["subscription_status"] in ("trial", "active")
