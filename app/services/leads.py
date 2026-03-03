"""Leads & Growth Engine — Component 9.

Handles unregistered users who text the Goon number:
- Logs their attempts
- Sends warm teaser responses (escalating with repeat contact)
- Re-engages warm leads weekly
"""
from __future__ import annotations

import logging

import anthropic

from app.config import settings
from app.db.database import db
from app.services.sms import send_sms

logger = logging.getLogger(__name__)


async def handle_unregistered(phone: str, body: str) -> str:
    """Log attempt and send teaser response. Returns the response sent."""
    try:
        await db.execute(
            "INSERT INTO unregistered_attempts (phone, body) VALUES (?, ?)",
            [phone, body],
        )
    except Exception:
        logger.exception("Failed to log unregistered attempt from %s", phone)

    try:
        count = await db.fetch_one(
            "SELECT COUNT(*) as n FROM unregistered_attempts WHERE phone = ?",
            [phone],
        )
        n = count["n"] if count else 1
    except Exception:
        logger.exception("Failed to count unregistered attempts for %s", phone)
        n = 1

    try:
        if n == 1:
            response = await compose_teaser(body, attempt_count=1)
        elif n <= 3:
            history = await _recent_messages(phone, limit=3)
            response = await compose_teaser(body, attempt_count=n, history=history)
        else:
            response = (
                f"You've texted {n} times -- sounds like you need Hold Plz. "
                f"Sign up: {settings.base_url}/signup"
            )
    except Exception:
        logger.exception("Failed to compose teaser for %s", phone)
        response = (
            f"Hey! Hold Plz is an AI concierge that handles calls for you. "
            f"Sign up at {settings.base_url}/signup to get started."
        )

    await send_sms(phone, response)
    return response


async def log_unregistered_attempt(phone: str, body: str) -> None:
    """Log an SMS from an unregistered number."""
    await db.execute(
        "INSERT INTO unregistered_attempts (phone, body) VALUES (?, ?)",
        [phone, body],
    )


async def compose_teaser(
    body: str,
    attempt_count: int = 1,
    history: list[str] | None = None,
) -> str:
    """Give a partial answer + signup nudge. Under 160 chars, no emoji."""
    is_first = attempt_count == 1
    history_context = ""
    if history and not is_first:
        history_context = (
            "\nTheir previous messages: " + " | ".join(history)
        )

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=160,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Someone texted our service with: "{body}"\n'
                        f"\n{'First time texter.' if is_first else f'Repeat texter (attempt {attempt_count}).'}"
                        f"{history_context}\n"
                        f"\nGive a brief, helpful response that:\n"
                        f"1. Acknowledges what they're asking\n"
                        f"2. Gives a partial/teaser answer if possible\n"
                        f"3. Mentions signup: {settings.base_url}/signup\n"
                        f"\nMUST be under 155 chars total. No emoji. Be warm, not salesy."
                    ),
                }
            ],
        )
        return response.content[0].text.strip()
    except Exception:
        logger.exception("Failed to compose teaser via LLM")
        return (
            f"Hey! Hold Plz is an AI concierge that handles calls for you. "
            f"Sign up at {settings.base_url}/signup to get started."
        )


async def get_teaser_response() -> str:
    """Return a static teaser response for unregistered users."""
    return (
        "Hey! Hold Plz is an AI concierge that handles calls for you. "
        f"Sign up at {settings.base_url} to get started."
    )


async def run_reengagement() -> list[dict]:
    """Weekly cron. Re-engage warm leads who texted 2+ times in last 7 days.

    Returns list of {phone, message} for each lead contacted.
    """
    warm_leads = await db.fetch_all("""
        SELECT phone, COUNT(*) as n,
               GROUP_CONCAT(body, ' | ') as messages
        FROM unregistered_attempts
        WHERE phone NOT IN (SELECT phone FROM users)
        GROUP BY phone
        HAVING n >= 2
        AND MAX(created_at) > datetime('now', '-7 days')
        AND MAX(created_at) < datetime('now', '-1 day')
    """)

    results = []
    for lead in warm_leads:
        try:
            msg = await compose_reengagement(lead)
            if msg:
                await send_sms(lead["phone"], msg)
                results.append({"phone": lead["phone"], "message": msg})
        except Exception:
            logger.exception("Re-engagement failed for lead %s", lead.get("phone"))
    return results


async def compose_reengagement(lead: dict) -> str | None:
    """Compose a personalized re-engagement message for a warm lead."""
    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=160,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Re-engage a warm lead who has texted us {lead['n']} times.\n"
                        f"\nTheir past messages: {lead['messages']}\n"
                        f"\nCompose a short follow-up SMS that:\n"
                        f"1. References what they were trying to do\n"
                        f"2. Shows the value they'd get from signing up\n"
                        f"3. Includes signup link: {settings.base_url}/signup\n"
                        f"\nMUST be under 155 chars. No emoji. Warm, not salesy.\n"
                        f"If the messages don't warrant follow-up, respond exactly: SKIP"
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        return None if text == "SKIP" else text
    except Exception:
        logger.exception("Failed to compose re-engagement for lead %s", lead.get("phone"))
        return None


async def get_lead_stats() -> dict:
    """Get lead funnel stats for admin dashboard."""
    total = await db.fetch_one(
        "SELECT COUNT(DISTINCT phone) as n FROM unregistered_attempts"
    )
    repeat = await db.fetch_one("""
        SELECT COUNT(*) as n FROM (
            SELECT phone FROM unregistered_attempts
            GROUP BY phone HAVING COUNT(*) >= 2
        )
    """)
    converted = await db.fetch_one("""
        SELECT COUNT(DISTINCT ua.phone) as n
        FROM unregistered_attempts ua
        INNER JOIN users u ON ua.phone = u.phone
    """)
    recent = await db.fetch_all("""
        SELECT phone, body, created_at
        FROM unregistered_attempts
        ORDER BY created_at DESC
        LIMIT 20
    """)

    return {
        "total_unique_leads": total["n"] if total else 0,
        "repeat_leads": repeat["n"] if repeat else 0,
        "converted": converted["n"] if converted else 0,
        "recent_attempts": recent,
    }


async def _recent_messages(phone: str, limit: int = 5) -> list[str]:
    """Get recent message bodies from an unregistered number."""
    rows = await db.fetch_all(
        "SELECT body FROM unregistered_attempts WHERE phone = ? ORDER BY created_at DESC LIMIT ?",
        [phone, limit],
    )
    return [r["body"] for r in rows if r["body"]]
