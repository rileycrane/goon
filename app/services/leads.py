"""Unregistered user handling — teaser responses, attempt logging."""

from app.db.database import db


async def log_unregistered_attempt(phone: str, body: str) -> None:
    """Log an SMS from an unregistered number."""
    await db.execute(
        "INSERT INTO unregistered_attempts (phone, body) VALUES (?, ?)",
        [phone, body],
    )


async def get_teaser_response() -> str:
    """Return a teaser response for unregistered users."""
    return (
        "Hey! Goon is an AI concierge that handles calls and errands for you. "
        "Sign up at getgoon.com to get started."
    )
