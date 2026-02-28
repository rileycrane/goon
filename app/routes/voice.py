"""Twilio voice webhook — routes inbound calls to Vapi."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from app.config.settings import settings
from app.services.auth import get_user, is_user_active

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def voice_webhook(request: Request) -> Response:
    """Handle inbound voice call from Twilio, forward to Vapi.

    Flow:
      1. Twilio receives inbound call to the Goon number
      2. Twilio POSTs to this webhook
      3. We check caller auth (registered + active subscription)
      4. If authorized, return TwiML that forwards to Vapi assistant
      5. If not authorized, play a brief rejection message
    """
    form = await request.form()
    caller = str(form.get("From", ""))
    call_sid = str(form.get("CallSid", ""))

    logger.info("Inbound voice call from=%s sid=%s", caller, call_sid)

    # Auth check
    user = await get_user(caller) if caller else None
    if not user or not is_user_active(user):
        logger.info("Unauthorized caller: %s", caller)
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>Sorry, this number is not registered with Goon. "
            "Visit get goon dot com to sign up.</Say>"
            "<Hangup/>"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Forward to Vapi assistant via SIP
    # Vapi provides a SIP URI for each phone number imported into the platform.
    # The assistant_id is passed as a SIP header so Vapi knows which assistant to use.
    assistant_id = settings.vapi_assistant_id
    if not assistant_id:
        logger.error("VAPI_ASSISTANT_ID not configured")
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>We are experiencing technical difficulties. Please try again later.</Say>"
            "<Hangup/>"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Build TwiML to connect caller to Vapi
    # Vapi SIP endpoint: sip:{assistant_id}@sip.vapi.ai
    # Pass caller info as SIP headers so Vapi can identify the user
    sip_uri = f"sip:{assistant_id}@sip.vapi.ai"
    server_url = settings.vapi_server_url or f"{settings.base_url}/vapi/events"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Dial>"
        f'<Sip>{sip_uri}'
        f"?X-Vapi-Server-Url={server_url}"
        f"&amp;X-Caller-Phone={caller}"
        f"&amp;X-Caller-Name={user.get('name', '')}"
        f"&amp;X-Call-Sid={call_sid}"
        "</Sip>"
        "</Dial>"
        "</Response>"
    )

    logger.info("Forwarding call to Vapi assistant=%s caller=%s", assistant_id, caller)
    return Response(content=twiml, media_type="application/xml")
