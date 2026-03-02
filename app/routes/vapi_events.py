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
    call_id = msg.get("call", {}).get("id", "unknown")

    logger.info("Vapi event received: type=%s call_id=%s", msg_type, call_id)

    try:
        if msg_type == "end-of-call-report":
            logger.info("Processing end-of-call-report for call_id=%s", call_id)
            await _handle_end_of_call(event)
            logger.info("Finished processing end-of-call-report for call_id=%s", call_id)
        elif msg_type == "status-update":
            status = msg.get("status", "")
            logger.info("Vapi status update: call=%s status=%s", call_id, status)
            # Update call_log on terminal status events that aren't end-of-call
            if status in ("ended", "failed"):
                await _ensure_call_status_updated(call_id, status)
    except Exception:
        logger.exception(
            "Unhandled error processing Vapi event type=%s call_id=%s", msg_type, call_id,
        )
        # On any error, try to mark the call as failed so it doesn't stay in_progress
        if call_id != "unknown":
            await _mark_call_failed_on_error(call_id, msg_type)

    return {"status": "ok"}


async def _handle_end_of_call(event: dict) -> None:
    """Process an end-of-call report from Vapi."""
    try:
        msg = event.get("message", {})
        call_data = msg.get("call", {})
        call_id = call_data.get("id")
        if not call_id:
            logger.warning("Vapi end-of-call event missing call ID")
            return
    except Exception:
        logger.exception("Failed to parse Vapi end-of-call event")
        return

    record = await db.fetch_one(
        "SELECT * FROM call_log WHERE vapi_call_id = ?", [call_id],
    )
    if not record:
        logger.warning("No call_log record for vapi_call_id=%s", call_id)
        return

    transcript = msg.get("transcript", "")
    ended_reason = call_data.get("endedReason", call_data.get("ended_reason", "unknown"))
    # Normalize: Vapi may send camelCase, kebab-case, or spaced
    ended_reason = ended_reason.lower().replace(" ", "-").replace("_", "-")
    duration = call_data.get("duration")

    outcome = classify_call_outcome(ended_reason, transcript)
    logger.info(
        "Call %s outcome: success=%s reason=%s ended_reason=%s transcript_len=%d",
        call_id, outcome["success"], outcome["reason"], ended_reason,
        len(transcript) if transcript else 0,
    )

    # Update phone score
    if record.get("place_id"):
        try:
            await update_phone_score(
                record["place_id"], record["business_phone"], outcome,
            )
        except Exception:
            logger.exception("Failed to update phone score for call %s", call_id)

    if outcome["success"]:
        try:
            summary = await summarize_call_result(transcript, record["task"])
        except Exception:
            logger.exception("Failed to summarize call %s", call_id)
            summary = f"Call to {record['business_name']} completed. I wasn't able to summarize the result -- please try asking again."

        # Text user the result
        await send_sms(record["user_id"], summary)

        # Cache the fact
        if record.get("place_id"):
            try:
                await store_fact(
                    place_id=record["place_id"],
                    business_name=record["business_name"],
                    fact_type=record.get("task_type", "general"),
                    question=record["task"],
                    answer=summary,
                    source="phone_call",
                )
            except Exception:
                logger.exception("Failed to cache fact for call %s", call_id)

        # Update memory
        try:
            await append_conversation(
                record["user_id"], "out",
                f"[Call result: {record['business_name']}] {summary}",
                metadata={"type": "call_result", "business": record["business_name"]},
            )
        except Exception:
            logger.exception("Failed to append conversation for call %s", call_id)

        # Update call log
        try:
            await db.execute(
                """
                UPDATE call_log SET status='success', result=?,
                    transcript=?, duration_seconds=?
                WHERE vapi_call_id=?
                """,
                [summary, transcript, duration, call_id],
            )
        except Exception:
            logger.exception("Failed to update call_log for successful call %s", call_id)
        logger.info("Call success: %s -> %s", call_id, record["business_name"])

    else:
        await handle_call_failure(record, outcome)
        # Store transcript even on failure
        try:
            await db.execute(
                "UPDATE call_log SET transcript=?, duration_seconds=? WHERE vapi_call_id=?",
                [transcript, duration, call_id],
            )
        except Exception:
            logger.exception("Failed to update call_log for failed call %s", call_id)
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

    # Catch-all: if we got a substantial transcript, likely success
    if not outcome["success"] and transcript and len(transcript) > 200:
        outcome["success"] = True
        outcome["reason"] = "success_inferred"

    return outcome


async def summarize_call_result(transcript: str, task: str) -> str:
    """Summarize a call transcript into an SMS-length response."""
    client = anthropic.AsyncAnthropic()
    try:
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
    except Exception:
        logger.exception("Failed to summarize call transcript")
        # Fallback: return a truncated transcript snippet
        snippet = transcript[:150].strip() if transcript else "Call completed"
        return f"Call result: {snippet}..."


async def _ensure_call_status_updated(call_id: str, status: str) -> None:
    """Ensure call_log status is updated on terminal status events.

    If we receive an 'ended' or 'failed' status-update but the end-of-call-report
    hasn't arrived (or was lost), this prevents calls from staying in_progress forever.
    """
    record = await db.fetch_one(
        "SELECT status FROM call_log WHERE vapi_call_id = ?", [call_id],
    )
    if not record:
        logger.warning("Status update for unknown call_id=%s status=%s", call_id, status)
        return
    if record["status"] == "in_progress":
        logger.info(
            "Call %s got status=%s while still in_progress, "
            "waiting for end-of-call-report before updating",
            call_id, status,
        )


async def _mark_call_failed_on_error(call_id: str, event_type: str) -> None:
    """Safety net: if event processing errors out, mark the call as failed.

    This prevents calls from getting stuck in in_progress status forever
    when an exception occurs during webhook processing.
    """
    try:
        record = await db.fetch_one(
            "SELECT status FROM call_log WHERE vapi_call_id = ?", [call_id],
        )
        if record and record["status"] == "in_progress":
            logger.warning(
                "Marking call %s as failed due to error processing event %s",
                call_id, event_type,
            )
            await db.execute(
                "UPDATE call_log SET status='failed_webhook_error' WHERE vapi_call_id=?",
                [call_id],
            )
    except Exception:
        logger.exception("Failed to mark call %s as failed after error", call_id)
