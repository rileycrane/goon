"""Vapi call event webhook — receives call status updates and transcripts."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request

from app.db.database import db
from app.services.cache import store_fact, update_phone_score
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
        await _handle_end_of_call(msg)
    elif msg_type == "status-update":
        status = msg.get("status", "")
        call_id = msg.get("call", {}).get("id", "")
        logger.info("Vapi status update: call=%s status=%s", call_id, status)

    return {"status": "ok"}


async def _handle_end_of_call(msg: dict) -> None:
    """Process end-of-call-report from Vapi."""
    call_data = msg.get("call", {})
    call_id = call_data.get("id", "")

    if not call_id:
        logger.warning("End-of-call report with no call ID")
        return

    record = await db.fetch_one(
        "SELECT * FROM call_log WHERE vapi_call_id = ?", [call_id]
    )
    if not record:
        logger.info("No call_log record for vapi_call_id=%s (may be inbound)", call_id)
        return

    transcript = msg.get("transcript", "")
    ended_reason = call_data.get("endedReason", "unknown")
    duration = call_data.get("durationSeconds")

    # Classify the outcome
    outcome = classify_call_outcome(ended_reason, transcript)

    logger.info(
        "Call ended: call=%s reason=%s success=%s",
        call_id, ended_reason, outcome["success"],
    )

    # Update phone score if we have a place_id
    if record.get("place_id"):
        await update_phone_score(
            record["place_id"],
            record["business_phone"],
            outcome,
        )

    if outcome["success"]:
        summary = await _summarize_call_result(transcript, record["task"])

        # Text the user the result
        await send_sms(record["user_id"], summary)

        # Cache the learned fact
        if record.get("place_id"):
            await store_fact(
                place_id=record["place_id"],
                business_name=record.get("business_name", ""),
                fact_type=record.get("task_type", "general"),
                question=record["task"],
                answer=summary,
                source="phone_call",
            )

        # Update call log
        await db.execute(
            "UPDATE call_log SET status='success', result=?, transcript=?, "
            "duration_seconds=? WHERE vapi_call_id=?",
            [summary, transcript, duration, call_id],
        )
    else:
        await _handle_call_failure(record, outcome)

        # Update call log with failure
        await db.execute(
            "UPDATE call_log SET status='failed', result=?, transcript=?, "
            "duration_seconds=? WHERE vapi_call_id=?",
            [outcome["reason"], transcript, duration, call_id],
        )


def classify_call_outcome(ended_reason: str, transcript: str) -> dict:
    """Classify call outcome based on Vapi's ended reason and transcript length.

    Taxonomy from original TalkTo:
      busy, no_answer, voicemail, wrong_number, hostile, timeout, success
    """
    outcome: dict = {"success": False, "reason": ended_reason, "retry": False}

    if ended_reason == "assistant-ended-call":
        # Agent chose to end -- could be success or deliberate hangup
        if transcript and len(transcript) > 50:
            outcome["success"] = True
        else:
            outcome["reason"] = "no_useful_info"
            outcome["retry"] = True

    elif ended_reason == "customer-ended-call":
        # Business hung up
        if len(transcript) > 100:
            outcome["success"] = True
        else:
            outcome["reason"] = "hung_up"
            outcome["retry"] = True

    elif ended_reason in ("no-answer", "busy"):
        outcome["reason"] = ended_reason
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 10

    elif ended_reason == "voicemail":
        outcome["reason"] = "voicemail"
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 30

    elif ended_reason == "max-duration-reached":
        outcome["reason"] = "timeout"
        outcome["retry"] = False  # Probably stuck on hold

    return outcome


async def _summarize_call_result(transcript: str, task: str) -> str:
    """Use Claude to summarize a call transcript into a user-friendly SMS."""
    import anthropic

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarize this phone call result for an SMS to the user. "
                    f"Be concise (under 300 chars). No emoji.\n\n"
                    f"Task: {task}\n\n"
                    f"Transcript:\n{transcript[:2000]}"
                ),
            }
        ],
    )
    return response.content[0].text


async def _handle_call_failure(record: dict, outcome: dict) -> None:
    """Handle a failed call -- notify user and schedule retry if appropriate."""
    user_id = record["user_id"]
    business = record.get("business_name", "the business")
    reason = outcome["reason"]

    retry = outcome.get("retry", False)
    retry_count = record.get("retry_count", 0)
    max_retries = 2

    if retry and retry_count < max_retries:
        delay = outcome.get("retry_delay_minutes", 10)
        retry_after = datetime.now().isoformat()

        await db.execute(
            "UPDATE call_log SET status='retry_pending', retry_count=retry_count+1, "
            "retry_after=? WHERE id=?",
            [retry_after, record["id"]],
        )

        msg = (
            f"Couldn't reach {business} ({reason}). "
            f"Will try again in {delay} minutes."
        )
        await send_sms(user_id, msg)
    else:
        msg = (
            f"Couldn't reach {business} after multiple attempts ({reason}). "
            f"Want me to try a different approach or look online instead?"
        )
        await send_sms(user_id, msg)
