"""Outbound call management -- Vapi calls, retries, outcome classification."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config.settings import settings
from app.db.database import db
from app.services.cache import get_ivr_map, get_phone_score, update_phone_score
from app.services.places import get_place_details, is_chain_business
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"
MAX_RETRIES = 2


async def pre_call_check(
    business_name: str,
    business_phone: str,
    place_id: Optional[str] = None,
) -> dict:
    """Run all checks before committing to a phone call.

    Returns {"ok": bool, "issues": [{"type": str, "message": str}, ...]}.
    """
    issues: list[dict] = []

    if not business_phone:
        issues.append({
            "type": "no_phone",
            "message": "No phone number available",
        })
        return {"ok": False, "issues": issues}

    # Check phone score -- flag unreliable numbers
    if place_id:
        score = await get_phone_score(place_id, business_phone)
        if score:
            failures = score["call_count"] - score["success_count"]
            if failures >= 2:
                issues.append({
                    "type": "bad_number",
                    "message": (
                        f"This number has failed {failures} times. "
                        f"Last outcome: {score['last_outcome']}."
                    ),
                })
            if score.get("last_outcome") == "wrong_number":
                issues.append({
                    "type": "wrong_number",
                    "message": "This number was previously flagged as wrong.",
                })

        # Check if business is open now via Google Places
        place = await get_place_details(place_id)
        if place:
            if place.open_now is False:
                issues.append({
                    "type": "closed",
                    "message": f"{business_name} appears to be closed right now.",
                })
            if is_chain_business(place):
                issues.append({
                    "type": "chain",
                    "message": (
                        "This looks like a chain. The phone number may route "
                        "to a corporate call center."
                    ),
                })

    ok = not any(i["type"] in ("wrong_number", "no_phone") for i in issues)
    return {"ok": ok, "issues": issues}


def build_call_prompt(
    task: str,
    task_type: str,
    business_name: str,
    user_name: str,
    details: dict | None = None,
    ivr_map: dict | None = None,
) -> str:
    """Build the system prompt for the Vapi voice agent."""
    base = f"""You are calling {business_name}.

## Your Task
{task}

## Rules
- Sound like a regular person calling. Be natural, friendly, efficient.
- Do NOT say "I'm calling on behalf of" or "I'm an AI" or "I'm an assistant"
- Just ask the question like a normal customer would
- Get straight to the point after a brief "hi"
- If they ask for a name, say "{user_name}"
- If they ask for a callback number, say "{settings.goon_number}"

## IVR / Phone Tree Navigation
If you reach an automated phone system:
1. Listen for "representative", "operator", or "speak to someone"
2. Common shortcuts: press 0, say "representative", say "agent"
3. If options are numbered, pick the most relevant
   (e.g., "press 2 for reservations")
4. If the IVR ITSELF answers your question (e.g., announces hours),
   capture that info -- you don't need a human
5. If stuck in a loop after 30 seconds, hang up
"""

    if ivr_map and ivr_map.get("menu_structure"):
        menu = ivr_map["menu_structure"]
        base += "\n## Known IVR Menu for This Business\n"
        for key, label in menu.items():
            base += f"- Press {key}: {label}\n"

    base += """
## Hold
- If put on hold, wait up to 90 seconds
- After 90 seconds, hang up

## Edge Cases
- Voicemail: hang up (do not leave a message)
- Hostile/rude: "Sorry to bother you, thanks" -> hang up
- Wrong number/disconnected: hang up immediately
- Employee needs clarification: rephrase your question with more context
- Complex answer (full menu, long list): capture key facts, don't need everything
- "We don't give that info over phone": thank them, hang up
- "Check our website": ask for the URL if you don't have it, hang up

## After Getting the Answer — CRITICAL
- Once they confirm your request is handled, say "Great, thank you so much" and END THE CALL IMMEDIATELY
- Do NOT ask "anything else?" or "is there anything else I can help with?" — YOU called THEM
- Do NOT repeat back details they just told you -- it sounds robotic
- Do NOT linger. One brief "thanks, bye" and hang up. You are the caller, not the receptionist.
"""

    details = details or {}
    if task_type == "reservation":
        base += f"""
## Reservation-Specific
1. "Hi, I'd like to make a reservation."
2. Party size: {details.get('party_size', 'ask user')}
3. Date: {details.get('date', 'ask user')}
4. Time: {details.get('time', 'ask user')}
5. Name: {user_name}
6. If preferred time unavailable: ask what's available nearby and note it
   (do NOT book a different time without user confirmation)
7. Get confirmation number if they offer one
"""
    elif task_type == "appointment":
        base += f"""
## Appointment-Specific
1. "Hi, I'd like to schedule an appointment."
2. Service: {details.get('service', task)}
3. Preferred date/time: {details.get('date', 'flexible')} {details.get('time', 'flexible')}
4. Name: {user_name}
5. If they need a phone number: {settings.goon_number}
"""

    return base


def build_first_message(task: str, task_type: str, details: dict | None = None) -> str:
    """Build the opening message for the voice agent. Sound human.

    Different task types get different openings to sound natural.
    """
    details = details or {}

    if task_type == "reservation":
        party = details.get("party_size", "2")
        return f"Hi, I'd like to make a reservation for {party}."
    elif task_type == "appointment":
        return "Hi, I'd like to schedule an appointment."
    elif task_type == "availability_check":
        return f"Hi, I have a quick question: {task}"

    # Generic: rewrite task as a natural first-person request
    t = task.strip()
    command_starts = ["make", "book", "reserve", "schedule", "check", "ask", "find", "get", "call"]
    first_word = t.split()[0].lower() if t else ""
    if first_word in command_starts:
        t = f"I'd like to {t[0].lower()}{t[1:]}"
    return f"Hi, {t}"


async def check_duplicate_call(user_id: str, business_phone: str) -> dict | None:
    """Check if there's already an in-progress call for this user+business.

    Returns the existing call record if found, None otherwise.
    """
    record = await db.fetch_one(
        """
        SELECT * FROM call_log
        WHERE user_id = ? AND business_phone = ? AND status = 'in_progress'
        """,
        [user_id, business_phone],
    )
    return record


async def initiate_outbound_call(
    business_name: str,
    business_phone: str,
    task: str,
    user_id: str,
    task_type: str = "info_query",
    place_id: str | None = None,
    user_name: str = "",
    details: dict | None = None,
) -> dict:
    """Initiate an outbound AI voice call to a business via Vapi.

    Returns immediately. Result arrives via the Vapi webhook.
    """
    if not settings.vapi_api_key:
        raise RuntimeError("VAPI_API_KEY not configured")
    if not settings.vapi_phone_number_id:
        raise RuntimeError("VAPI_PHONE_NUMBER_ID not configured")

    # Check for duplicate in-progress call to same business
    existing = await check_duplicate_call(user_id, business_phone)
    if existing:
        logger.info(
            "Duplicate call blocked: user=%s biz=%s existing_call=%s",
            user_id, business_name, existing["vapi_call_id"],
        )
        return {
            "call_log_id": existing["id"],
            "vapi_call_id": existing["vapi_call_id"],
            "status": "already_in_progress",
        }

    # Look up IVR map if we have one
    ivr_map = None
    if place_id:
        ivr_map = await get_ivr_map(place_id, business_phone)

    system_prompt = build_call_prompt(
        task=task,
        task_type=task_type,
        business_name=business_name,
        user_name=user_name or "the customer",
        details=details,
        ivr_map=ivr_map,
    )
    first_message = build_first_message(task, task_type, details)
    server_url = settings.vapi_server_url or f"{settings.base_url}/vapi/events"

    # Create the call via Vapi REST API
    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": business_phone},
        "assistant": {
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "system", "content": system_prompt}],
                "tools": [
                    {
                        "type": "dtmf",
                        "function": {
                            "name": "dtmf",
                            "description": "Press a phone keypad button. Use this to navigate phone menus (IVR). For example, press '1' to talk to staff, '0' for operator.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "button": {
                                        "type": "string",
                                        "description": "The button to press: 0-9, *, or #"
                                    }
                                },
                                "required": ["button"]
                            }
                        }
                    }
                ],
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "jBzLvP03992lMFEkj2kJ",
            },
            "firstMessage": first_message,
            "endCallFunctionEnabled": True,
            "endCallMessage": "thanks",
            "maxDurationSeconds": 180,
            "serverUrl": server_url,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{VAPI_BASE}/call/phone",
                headers={
                    "Authorization": f"Bearer {settings.vapi_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error("Vapi API error: %s %s", resp.status_code, resp.text)
            resp.raise_for_status()
            call_data = resp.json()
    except httpx.TimeoutException:
        logger.error("Vapi call initiation timed out for %s", business_name)
        raise RuntimeError(f"Call to {business_name} timed out. Try again later.")
    except httpx.HTTPStatusError:
        raise RuntimeError(f"Could not initiate call to {business_name}. Service temporarily unavailable.")
    except Exception:
        logger.exception("Unexpected error initiating Vapi call to %s", business_name)
        raise RuntimeError(f"Could not initiate call to {business_name}.")

    vapi_call_id = call_data.get("id", "")

    # Store call record for tracking
    call_log_id = await db.execute(
        """
        INSERT INTO call_log
            (user_id, vapi_call_id, business_name, business_phone,
             place_id, task, task_type, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress')
        """,
        [user_id, vapi_call_id, business_name, business_phone,
         place_id, task, task_type],
    )

    logger.info("Outbound call initiated: vapi_call_id=%s biz=%s", vapi_call_id, business_name)

    return {
        "call_log_id": call_log_id,
        "vapi_call_id": vapi_call_id,
        "status": "in_progress",
    }


async def handle_call_failure(record: dict, outcome: dict) -> None:
    """Route call failures to appropriate retry/response strategy."""
    user_id = record["user_id"]
    biz = record["business_name"]

    try:
        if outcome["reason"] == "busy":
            await send_sms(user_id, f"{biz}'s line is busy. Trying again in 5 min.")
            await schedule_retry(record, delay_minutes=5)

        elif outcome["reason"] == "no-answer":
            await send_sms(user_id, f"No answer at {biz}. I'll try again in 10 min.")
            await schedule_retry(record, delay_minutes=10)

        elif outcome["reason"] == "voicemail":
            await send_sms(
                user_id,
                f"Got voicemail at {biz}. I'll try again in 30 min, "
                f"or I can look online instead. Reply 'web' to skip the call.",
            )
            await schedule_retry(record, delay_minutes=30)

        elif outcome["reason"] == "wrong_number":
            await send_sms(
                user_id,
                f"That number doesn't seem right for {biz}. "
                f"Do you have their number? Or I can look for another one.",
            )
            # Blacklist this number
            if record.get("place_id"):
                await update_phone_score(
                    record["place_id"], record["business_phone"],
                    {"success": False, "reason": "wrong_number"},
                )

        elif outcome["reason"] == "hung_up":
            if record.get("retry_count", 0) < 1:
                await send_sms(user_id, f"{biz} hung up. I'll try once more in a few minutes.")
                await schedule_retry(record, delay_minutes=15)
            else:
                await send_sms(
                    user_id,
                    f"Couldn't get through to {biz}. "
                    f"You might need to call them directly at {record['business_phone']}.",
                )

        elif outcome["reason"] == "timeout":
            await send_sms(
                user_id,
                f"Was on hold too long at {biz}. Want me to try again later?",
            )

        else:
            await send_sms(
                user_id,
                f"Had trouble reaching {biz}. "
                f"Want me to try again or look online instead?",
            )
    except Exception:
        logger.exception("Error handling call failure for %s -> %s", record.get("vapi_call_id"), biz)

    # Update call log status
    try:
        await db.execute(
            "UPDATE call_log SET status=? WHERE vapi_call_id=?",
            [f"failed_{outcome['reason']}", record["vapi_call_id"]],
        )
    except Exception:
        logger.exception("Failed to update call_log status for %s", record.get("vapi_call_id"))


async def schedule_retry(record: dict, delay_minutes: int) -> None:
    """Schedule a retry for a failed call. Max 2 retries."""
    retry_count = record.get("retry_count", 0)
    if retry_count >= MAX_RETRIES:
        await send_sms(
            record["user_id"],
            f"Tried {record['business_name']} {retry_count + 1} times. "
            f"Giving up for now. Their number: {record['business_phone']}",
        )
        return

    retry_after = datetime.now() + timedelta(minutes=delay_minutes)
    try:
        await db.execute(
            """
            UPDATE call_log SET status='retry_pending',
                retry_count=?, retry_after=?
            WHERE vapi_call_id=?
            """,
            [retry_count + 1, retry_after.isoformat(), record["vapi_call_id"]],
        )
    except Exception:
        logger.exception("Failed to schedule retry for %s", record.get("vapi_call_id"))


async def process_retries() -> int:
    """Check for pending retries and re-initiate calls. Returns count processed."""
    now = datetime.now().isoformat()
    pending = await db.fetch_all(
        """
        SELECT * FROM call_log
        WHERE status = 'retry_pending' AND retry_after <= ?
        """,
        [now],
    )

    count = 0
    for record in pending:
        try:
            await initiate_outbound_call(
                business_name=record["business_name"],
                business_phone=record["business_phone"],
                task=record["task"],
                user_id=record["user_id"],
                task_type=record.get("task_type", "info_query"),
                place_id=record.get("place_id"),
            )
            count += 1
        except Exception:
            logger.exception("Retry failed for call %s", record["vapi_call_id"])

    return count
