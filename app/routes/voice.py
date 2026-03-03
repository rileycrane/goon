"""Twilio voice webhook — routes inbound calls to Vapi."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request, Response

from app.config.settings import settings
from app.services.auth import get_user, is_user_active

logger = logging.getLogger(__name__)

router = APIRouter()

VAPI_BASE = "https://api.vapi.ai"

FALLBACK_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Sorry, I'm having technical difficulties. Please try texting this number instead.</Say>
  <Hangup/>
</Response>"""


@router.post("/webhook")
async def voice_webhook(request: Request) -> Response:
    """Handle inbound voice call from Twilio, forward to Vapi.

    Flow:
      1. Twilio receives inbound call to the Goon number
      2. Twilio POSTs to this webhook
      3. We check caller auth (registered + active subscription)
      4. If authorized, call Vapi API which returns TwiML to bridge the call
      5. If not authorized, play a brief rejection message
    """
    form = await request.form()
    caller = str(form.get("From", ""))
    call_sid = str(form.get("CallSid", ""))

    logger.info("Inbound voice call from=%s sid=%s", caller, call_sid)

    # Auth check
    try:
        user = await get_user(caller) if caller else None
    except Exception:
        logger.exception("Auth lookup failed for voice call from %s", caller)
        return Response(content=FALLBACK_TWIML, media_type="application/xml")

    if not user or not is_user_active(user):
        logger.info("Unauthorized caller: %s", caller)
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>Sorry, this number is not registered with Hold Plz. "
            "Visit hold plz dot ai to sign up.</Say>"
            "<Hangup/>"
            "</Response>"
        )
        return Response(content=twiml, media_type="application/xml")

    # Forward to Vapi assistant via provider bypass
    assistant_id = settings.vapi_assistant_id
    if not assistant_id:
        logger.error("VAPI_ASSISTANT_ID not configured")
        return Response(content=FALLBACK_TWIML, media_type="application/xml")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{VAPI_BASE}/call",
                headers={
                    "Authorization": f"Bearer {settings.vapi_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "phoneNumberId": settings.vapi_phone_number_id,
                    "phoneCallProviderBypassEnabled": True,
                    "customer": {"number": caller},
                    "assistantId": assistant_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Failed to create Vapi inbound call for %s", caller)
        return Response(content=FALLBACK_TWIML, media_type="application/xml")

    twiml = data.get("phoneCallProviderDetails", {}).get("twiml", "")
    if not twiml:
        logger.error("Vapi response missing TwiML for inbound call from %s", caller)
        return Response(content=FALLBACK_TWIML, media_type="application/xml")

    logger.info("Forwarding call to Vapi assistant=%s caller=%s", assistant_id, caller)
    return Response(content=twiml, media_type="application/xml")
