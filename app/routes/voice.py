"""Twilio voice webhook -- routes inbound calls to Vapi."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.config.settings import settings

router = APIRouter()

# TwiML template to forward an inbound call to Vapi's SIP endpoint.
# Vapi provides a SIP URI that accepts forwarded calls from Twilio.
FORWARD_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Please hold while I connect you.</Say>
  <Dial>
    <Sip>sip:{assistant_id}@sip.vapi.ai</Sip>
  </Dial>
</Response>"""

FALLBACK_TWIML = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Sorry, I'm having trouble connecting. Please try texting this number instead.</Say>
  <Hangup/>
</Response>"""


@router.post("/webhook")
async def voice_webhook(request: Request) -> Response:
    """Handle inbound voice call from Twilio, forward to Vapi SIP endpoint."""
    assistant_id = settings.vapi_assistant_id
    if not assistant_id:
        return Response(content=FALLBACK_TWIML, media_type="application/xml")

    twiml = FORWARD_TWIML.format(assistant_id=assistant_id)
    return Response(content=twiml, media_type="application/xml")
