"""Twilio SMS webhook — receives inbound SMS, dispatches to orchestrator."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, Response

from app.config.settings import settings
from app.db.database import db
from app.services.auth import get_user, is_user_active
from app.services.leads import handle_unregistered
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()

TWIML_EMPTY = "<Response></Response>"


async def _log_message(
    user_id: str, direction: str, body: str, twilio_sid: str | None = None
) -> None:
    """Append to message_log table."""
    await db.execute(
        "INSERT INTO message_log (user_id, direction, body, twilio_sid) VALUES (?, ?, ?, ?)",
        [user_id, direction, body, twilio_sid],
    )


async def _process_and_respond(user_id: str, phone: str, body: str) -> None:
    """Run the orchestrator and send the response SMS.

    Runs as a background task so Twilio gets an immediate 200.
    """
    from app.services.orchestrator import handle_message

    try:
        response_text = await handle_message(user_id, body)
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

    await send_sms(phone, response_text)
    await _log_message(user_id, "out", response_text)


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

    # 1. Auth: check if sender is a registered user
    user = await get_user(sender)

    if not user:
        # Unregistered — route to leads funnel (logs + teaser)
        asyncio.create_task(handle_unregistered(sender, body))
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 2. Subscription check
    if not is_user_active(user):
        asyncio.create_task(
            send_sms(
                sender,
                "Your Goon subscription is inactive. "
                f"Renew at {settings.base_url}/billing",
            )
        )
        return Response(content=TWIML_EMPTY, media_type="application/xml")

    # 3. Log inbound message
    await _log_message(user["id"], "in", body, message_sid)

    # 4. Dispatch to orchestrator (async — don't block Twilio)
    asyncio.create_task(_process_and_respond(user["id"], sender, body))

    return Response(content=TWIML_EMPTY, media_type="application/xml")
