"""Twilio SMS webhook — receives inbound SMS, dispatches to orchestrator."""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.db.database import db
from app.services.auth import (
    get_signups_enabled,
    get_user,
    get_user_tier,
    increment_free_message_count,
)
from app.services.consent import STOP_PATTERN, handle_consent_reply, handle_stop, handle_web_signup
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



@router.post("/webhook")
async def sms_webhook(request: Request) -> Response:
    """Handle inbound SMS from Twilio.

    Acknowledges immediately with empty TwiML, then processes async.
    Consent flow intercepts are checked first (STOP, declined, pending).
    """
    form = await request.form()
    sender = form.get("From", "")
    body = form.get("Body", "")
    message_sid = form.get("MessageSid")

    if not sender or not body:
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    body = body.strip()

    # 1. STOP interception -- universal, works for any sender
    if STOP_PATTERN.match(body):
        asyncio.create_task(handle_stop(sender))
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 2. Look up user
    user = await get_user(sender)

    # 3. Declined user -- silently drop
    if user and user.get("consent_state") == "declined":
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 4. Pending consent -- handle consent reply (YES/STOP/other)
    if user and user.get("subscription_status") == "pending_consent":
        asyncio.create_task(handle_consent_reply(sender, body))
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 5. Unknown number -- start consent flow (not auto-create)
    if not user:
        signups_on = await get_signups_enabled()
        if signups_on:
            asyncio.create_task(handle_web_signup(sender))
        else:
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

    # --- Below here: confirmed users only ---

    # 6. Determine tier
    tier = get_user_tier(user)

    # 7. Check for upgrade keywords (any tier)
    if UPGRADE_KEYWORDS.match(body):
        asyncio.create_task(_send_payment_link(sender))
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 8. Log inbound message
    await _log_message(user["id"], "in", body, message_sid)

    # 9. Route by tier
    if tier == "active":
        asyncio.create_task(_process_and_respond(user["id"], sender, body))
    elif tier == "free":
        await increment_free_message_count(sender)
        asyncio.create_task(
            _process_and_respond(user["id"], sender, body, is_free_tier=True)
        )
    else:
        asyncio.create_task(
            send_sms(
                sender,
                "Your Hold Plz subscription is inactive. "
                "Text 'pay' to resubscribe.",
            )
        )

    return Response(content=TWIML_EMPTY, media_type="application/xml")
