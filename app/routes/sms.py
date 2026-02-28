"""Twilio SMS webhook — receives inbound SMS, dispatches to orchestrator."""

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.post("/webhook")
async def sms_webhook(request: Request) -> Response:
    """Handle inbound SMS from Twilio."""
    # TODO: parse Twilio form data, authenticate sender, dispatch to orchestrator
    return Response(content="<Response></Response>", media_type="application/xml")
