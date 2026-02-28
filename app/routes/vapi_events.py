"""Vapi call event webhook — receives call status updates and transcripts."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/events")
async def vapi_event(request: Request) -> dict:
    """Handle Vapi call event webhook."""
    # TODO: parse event, update call_log, notify user of result
    return {"status": "ok"}
