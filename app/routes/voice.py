"""Twilio voice webhook — routes inbound calls to Vapi."""

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.post("/webhook")
async def voice_webhook(request: Request) -> Response:
    """Handle inbound voice call from Twilio, forward to Vapi."""
    # TODO: return TwiML to forward call to Vapi SIP endpoint
    return Response(content="<Response></Response>", media_type="application/xml")
