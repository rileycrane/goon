"""Vapi call event webhook — receives call status updates and transcripts."""
from __future__ import annotations

import logging
from datetime import datetime

import anthropic
from fastapi import APIRouter, Request

from app.config.settings import settings
from app.db.database import db
from app.services.cache import store_fact, update_phone_score
from app.services.calls import handle_call_failure
from app.services.memory import append_conversation
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/events")
async def vapi_event(request: Request) -> dict:
    """Handle Vapi call event webhook.

    Vapi sends events for:
      - status-update: call started, ringing, in-progress, ended
      - end-of-call-report: final transcript, duration, ended reason
      - tool-calls: when the voice agent invokes a tool (future)
    """
    event = await request.json()
    msg = event.get("message", {})
    msg_type = msg.get("type", "")

    logger.info("Vapi event type=%s", msg_type)

    if msg_type == "end-of-call-report":
        await _handle_end_of_call(event)
    elif msg_type == "status-update":
        status = msg.get("status", "")
        call_id = msg.get("call", {}).get("id", "")
        logger.info("Vapi status update: call=%s status=%s", call_id, status)

    return {"status": "ok"}


async def _handle_end_of_call(event: dict) -> None:
    """Process an end-of-call report from Vapi."""
    call_data = event["message"]["call"]
    call_id = call_data["id"]

    record = await db.fetch_one(
        "SELECT * FROM call_log WHERE vapi_call_id = ?", [call_id],
    )
    if not record:
        logger.warning("No call_log record for vapi_call_id=%s", call_id)
        return

    transcript = event["message"].get("transcript", "")
    ended_reason = call_data.get("endedReason", "unknown")
    duration = call_data.get("duration")

    outcome = classify_call_outcome(ended_reason, transcript)

    # Update phone score
    if record.get("place_id"):
        await update_phone_score(
            record["place_id"], record["business_phone"], outcome,
        )

    if outcome["success"]:
        summary = await summarize_call_result(transcript, record["task"])

        # Text user the result
        await send_sms(record["user_id"], summary)

        # Cache the fact
        if record.get("place_id"):
            await store_fact(
                place_id=record["place_id"],
                business_name=record["business_name"],
                fact_type=record.get("task_type", "general"),
                question=record["task"],
                answer=summary,
                source="phone_call",
            )

        # Update memory
        await append_conversation(
            record["user_id"], "out",
            f"[Call result: {record['business_name']}] {summary}",
            metadata={"type": "call_result", "business": record["business_name"]},
        )

        # Update call log
        await db.execute(
            """
            UPDATE call_log SET status='success', result=?,
                transcript=?, duration_seconds=?
            WHERE vapi_call_id=?
            """,
            [summary, transcript, duration, call_id],
        )
        logger.info("Call success: %s -> %s", call_id, record["business_name"])

    else:
        await handle_call_failure(record, outcome)
        # Store transcript even on failure
        await db.execute(
            "UPDATE call_log SET transcript=?, duration_seconds=? WHERE vapi_call_id=?",
            [transcript, duration, call_id],
        )
        logger.info(
            "Call failed: %s -> %s reason=%s",
            call_id, record["business_name"], outcome["reason"],
        )


def classify_call_outcome(ended_reason: str, transcript: str) -> dict:
    """Classify call outcome based on Vapi's ended reason and transcript content.

    Based on original TalkTo's failure taxonomy:
    busy, no_answer, ivr_stuck, voicemail, wrong_number, hostile, timeout, success.
    """
    outcome: dict = {"success": False, "reason": ended_reason, "retry": False}

    if ended_reason == "assistant-ended-call":
        # Agent chose to end -- could be success or deliberate hangup
        if transcript and len(transcript) > 50:
            outcome["success"] = True
            outcome["reason"] = "success"
        else:
            outcome["reason"] = "no_useful_info"
            outcome["retry"] = True

    elif ended_reason == "customer-ended-call":
        # Business hung up
        if len(transcript) > 100:
            outcome["success"] = True
            outcome["reason"] = "success"
        else:
            outcome["reason"] = "hung_up"
            outcome["retry"] = True

    elif ended_reason in ("no-answer", "busy"):
        outcome["reason"] = ended_reason
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 10 if ended_reason == "no-answer" else 5

    elif ended_reason == "voicemail":
        outcome["reason"] = "voicemail"
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 30

    elif ended_reason == "max-duration-reached":
        outcome["reason"] = "timeout"
        outcome["retry"] = False  # Probably stuck on hold

    return outcome


async def summarize_call_result(transcript: str, task: str) -> str:
    """Summarize a call transcript into an SMS-length response."""
    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarize this phone call result in 1-2 sentences for an SMS. "
                    f"Be concise, no emoji. The user's original request was: {task}\n\n"
                    f"Transcript:\n{transcript[:2000]}"
                ),
            }
        ],
    )
    return response.content[0].text.strip()
