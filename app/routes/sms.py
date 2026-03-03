"""Twilio SMS webhook — receives inbound SMS, dispatches to orchestrator."""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.db.database import db
from app.services.auth import (
    create_free_user,
    get_signups_enabled,
    get_user,
    get_user_tier,
    increment_free_message_count,
    is_free_tier_exhausted,
)
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()

TWIML_EMPTY = "<Response></Response>"

UPGRADE_KEYWORDS = re.compile(r"^(upgrade|pay|subscribe|billing)$", re.IGNORECASE)


async def _log_message(
    user_id: str, direction: str, body: str, twilio_sid: str | None = None
) -> None:
    """Append to message_log table."""
    try:
        await db.execute(
            "INSERT INTO message_log (user_id, direction, body, twilio_sid) VALUES (?, ?, ?, ?)",
            [user_id, direction, body, twilio_sid],
        )
    except Exception:
        logger.exception("Failed to log message for user %s", user_id)


async def _process_and_respond(
    user_id: str, phone: str, body: str, is_free_tier: bool = False
) -> None:
    """Run the orchestrator and send the response SMS.

    Runs as a background task so Twilio gets an immediate 200.
    """
    from app.services.orchestrator import handle_message

    try:
        response_text = await handle_message(user_id, body, is_free_tier=is_free_tier)
    except NotImplementedError:
        response_text = (
            "Got it -- I'm still getting set up. "
            "Check back soon and I'll be ready to help."
        )
    except Exception:
        logger.exception("Orchestrator error for user %s", user_id)
        response_text = (
            "Something went wrong on my end. Try again in a minute."
        )

    try:
        await send_sms(phone, response_text)
    except Exception:
        logger.exception("Failed to send response SMS to %s", phone)
    await _log_message(user_id, "out", response_text)


async def _send_payment_link(phone: str) -> None:
    """Send the Stripe Payment Link to a user."""
    from app.services.billing import send_payment_link
    await send_payment_link(phone)


async def _send_paywall_message(phone: str, user: dict) -> None:
    """Compose and send a paywall message when free messages are exhausted."""
    import anthropic
    from app.services.memory import load_memory

    try:
        memory = await load_memory(phone)
        profile_excerpt = memory.profile[:300]
    except Exception:
        profile_excerpt = ""

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "A free user has hit their 10-message limit on Hold Plz. "
                        "Compose a short, warm SMS (under 300 chars, no emoji) that:\n"
                        "1. Acknowledges they've used their free messages\n"
                        "2. References something specific they asked about if possible\n"
                        "3. Mentions the paid plan lets them make calls to businesses\n"
                        "4. Says to text 'pay' to get a payment link\n"
                        "Be warm, not salesy. Sound like a friend, not a company.\n\n"
                        f"User context: {profile_excerpt}"
                    ),
                }
            ],
        )
        msg = response.content[0].text.strip()
    except Exception:
        logger.exception("Failed to compose paywall message for %s", phone)
        msg = (
            "You've used your 10 free messages. To keep going and unlock "
            "business calls, text 'pay' for a link to the paid plan ($19.99/mo)."
        )

    await send_sms(phone, msg)
    await _log_message(phone, "out", msg)


@router.post("/webhook")
async def sms_webhook(request: Request) -> Response:
    """Handle inbound SMS from Twilio.

    Acknowledges immediately with empty TwiML, then processes async.
    """
    form = await request.form()
    sender = form.get("From", "")
    body = form.get("Body", "")
    message_sid = form.get("MessageSid")

    if not sender or not body:
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    body = body.strip()

    # 1. Look up user
    user = await get_user(sender)

    # 2. No user record — create free user or send waitlist msg
    if not user:
        signups_on = await get_signups_enabled()
        if signups_on:
            user = await create_free_user(sender)
            await _log_message(user["id"], "in", body, message_sid)
            # Send welcome + process first message
            welcome = (
                "Hey, this is Hold Plz. I look up info and call businesses "
                "so you don't have to. You've got 10 free messages -- go ahead, "
                "ask me something."
            )
            await send_sms(sender, welcome)
            await _log_message(user["id"], "out", welcome)
            await increment_free_message_count(sender)
            asyncio.create_task(
                _process_and_respond(user["id"], sender, body, is_free_tier=True)
            )
        else:
            # Signups disabled — log attempt and send waitlist msg
            try:
                await db.execute(
                    "INSERT INTO unregistered_attempts (phone, body) VALUES (?, ?)",
                    [sender, body],
                )
            except Exception:
                pass
            asyncio.create_task(
                send_sms(
                    sender,
                    "Hold Plz isn't open to new users right now. "
                    "We'll text you when there's a spot.",
                )
            )
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 3. Determine tier
    tier = get_user_tier(user)

    # 4. Check for upgrade keywords (any tier)
    if UPGRADE_KEYWORDS.match(body):
        asyncio.create_task(_send_payment_link(sender))
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 5. Log inbound message
    await _log_message(user["id"], "in", body, message_sid)

    # 6. Route by tier
    if tier == "active":
        # Paying user — full access
        asyncio.create_task(_process_and_respond(user["id"], sender, body))
    elif tier == "free":
        # Free tier — check message limit
        if is_free_tier_exhausted(user, settings.free_message_limit):
            asyncio.create_task(_send_paywall_message(sender, user))
        else:
            await increment_free_message_count(sender)
            asyncio.create_task(
                _process_and_respond(user["id"], sender, body, is_free_tier=True)
            )
    else:
        # Inactive (canceled, past_due, etc.)
        asyncio.create_task(
            send_sms(
                sender,
                "Your Hold Plz subscription is inactive. "
                "Text 'pay' to resubscribe.",
            )
        )

    return Response(content=TWIML_EMPTY, media_type="application/xml")
