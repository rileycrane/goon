"""SMS consent flow -- opt-in state machine and message generation."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import anthropic

from app.config.settings import settings
from app.db.database import db
from app.services.auth import get_user
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

# How long before a consent SMS can be re-sent
CONSENT_COOLDOWN = timedelta(minutes=5)

# Consent reply patterns
YES_PATTERN = re.compile(r"^(yes|yeah|yep|y|yea|sure|ok|okay|go|start|confirm)$", re.IGNORECASE)
STOP_PATTERN = re.compile(r"^(stop|unsubscribe|cancel|quit|end)$", re.IGNORECASE)

# Hardcoded fallback messages (used if LLM generation fails)
FALLBACK_MESSAGES = {
    "confirmation_request": (
        "Hey, someone entered your number for Hold Plz -- "
        "a concierge that calls businesses so you don't have to. "
        "Reply YES to start or STOP to opt out."
    ),
    "welcome": (
        "You're in. I'm Hold Plz -- text me a question about any business "
        "and I'll find the answer or call them for you."
    ),
    "already_active": (
        "You're already set up. Just text me directly -- "
        "ask me anything about a business."
    ),
    "ghosted": (
        "Still here if you want me. Text me a question about any business "
        "and I'll handle it."
    ),
    "nudge_reply": (
        "Just need a YES to get started, or STOP if you're not interested. "
        "No worries either way."
    ),
}


async def generate_consent_message(scenario: str, context: str = "") -> str:
    """Generate an on-brand consent message via LLM, with hardcoded fallback."""
    fallback = FALLBACK_MESSAGES.get(scenario, FALLBACK_MESSAGES["confirmation_request"])

    try:
        from app.prompts.soul import get_consent_soul
        soul = get_consent_soul()
    except Exception:
        soul = ""

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""Write a single SMS message for this scenario.

Tone guide:
{soul}

Scenario: {scenario}
Context: {context or "none"}

Rules:
- Under 160 characters (one SMS segment)
- No emoji
- Must sound like a real person, not a corporation
- For confirmation_request: MUST include "reply YES to start" and "STOP to opt out"
- For welcome: tell them what to do next (just text a question)
- For ghosted: playful, not guilt-trippy
- For nudge_reply: brief re-ask, relaxed

Return ONLY the message text, nothing else.""",
                }
            ],
        )
        text = response.content[0].text.strip().strip('"')
        if len(text) > 300:
            return fallback
        # Confirmation messages MUST contain opt-out language
        if scenario == "confirmation_request" and "stop" not in text.lower():
            return fallback
        return text
    except Exception:
        logger.exception("Failed to generate consent message for scenario %s", scenario)
        return fallback


async def handle_web_signup(phone: str) -> None:
    """State machine dispatcher for web signup / phone entry.

    Always returns silently to the caller (privacy-preserving).
    Sends SMS asynchronously based on user state.
    """
    user = await get_user(phone)

    if user is None:
        # No record -- create pending user, send confirmation
        await _create_pending_and_send(phone)
        return

    consent = user.get("consent_state", "confirmed")

    if consent == "declined":
        # Never contact again
        return

    if consent == "fresh":
        # Re-send confirmation if cooldown has passed
        sent_at = user.get("consent_sent_at")
        if sent_at:
            sent_time = datetime.fromisoformat(sent_at)
            if datetime.now() - sent_time < CONSENT_COOLDOWN:
                return  # too soon, don't re-send
        msg = await generate_consent_message("confirmation_request")
        await send_sms(phone, msg)
        await db.execute(
            "UPDATE users SET consent_sent_at = ? WHERE phone = ?",
            [datetime.now().isoformat(), phone],
        )
        return

    if consent == "confirmed":
        # Check if they've ever actually messaged
        msg_count = await db.fetch_one(
            "SELECT COUNT(*) as c FROM message_log WHERE user_id = ? AND direction = 'in'",
            [phone],
        )
        has_messages = msg_count and msg_count["c"] > 0

        if has_messages:
            msg = await generate_consent_message("already_active")
            await send_sms(phone, msg)
        else:
            msg = await generate_consent_message("ghosted")
            await send_sms(phone, msg)
        return


async def _create_pending_and_send(phone: str) -> None:
    """Create a pending-consent user and send confirmation SMS."""
    from app.services.auth import create_pending_user

    await create_pending_user(phone)
    msg = await generate_consent_message("confirmation_request")
    await send_sms(phone, msg)
    await db.execute(
        "UPDATE users SET consent_sent_at = ? WHERE phone = ?",
        [datetime.now().isoformat(), phone],
    )


async def handle_consent_reply(phone: str, body: str) -> bool:
    """Handle a reply from a user in pending consent state.

    Returns True if the message was handled (consumed), False if it should
    pass through to normal processing.
    """
    body_stripped = body.strip()

    if YES_PATTERN.match(body_stripped):
        await _confirm_user(phone)
        return True

    if STOP_PATTERN.match(body_stripped):
        await handle_stop(phone)
        return True

    # Unrecognized reply -- send nudge
    msg = await generate_consent_message("nudge_reply")
    await send_sms(phone, msg)
    return True


async def _confirm_user(phone: str) -> None:
    """Confirm a user's consent and send welcome message."""
    from app.services.auth import confirm_user
    from app.services.memory import seed_soul

    await confirm_user(phone)
    msg = await generate_consent_message("welcome")
    await send_sms(phone, msg)

    # Seed initial SOUL.md for this user
    try:
        await seed_soul(phone)
    except Exception:
        logger.exception("Failed to seed soul for %s", phone)


async def handle_stop(phone: str) -> None:
    """Universal STOP handler -- mark user as declined, never contact again."""
    from app.services.auth import decline_user

    user = await get_user(phone)
    if user is None:
        # Unknown number sent STOP -- create declined record so we never contact
        await db.execute(
            """INSERT INTO users (id, phone, subscription_status, consent_state)
               VALUES (?, ?, 'canceled', 'declined')
               ON CONFLICT(id) DO UPDATE SET consent_state = 'declined'""",
            [phone, phone],
        )
        return

    await decline_user(phone)
