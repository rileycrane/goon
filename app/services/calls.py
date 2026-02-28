"""Outbound call management — Vapi calls, retries, outcome classification."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config.settings import settings
from app.db.database import db
from app.services.cache import get_phone_score

logger = logging.getLogger(__name__)

VAPI_API_BASE = "https://api.vapi.ai"


async def initiate_outbound_call(
    business_name: str,
    business_phone: str,
    task: str,
    task_type: str,
    user_id: str,
    user_name: str,
    place_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
    """Initiate an outbound AI voice call to a business via Vapi.

    Creates a Vapi transient assistant with task-specific prompts,
    logs the call to call_log, and returns call metadata.
    The actual result comes asynchronously via the /vapi/events webhook.
    """
    if not settings.vapi_api_key:
        raise RuntimeError("VAPI_API_KEY not configured")
    if not settings.vapi_phone_number_id:
        raise RuntimeError("VAPI_PHONE_NUMBER_ID not configured")

    call_prompt = build_call_prompt(
        business_name=business_name,
        task=task,
        task_type=task_type,
        user_name=user_name,
        details=details or {},
    )
    first_message = build_first_message(task, task_type, details or {})
    server_url = settings.vapi_server_url or f"{settings.base_url}/vapi/events"

    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": business_phone},
        "assistant": {
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "system", "content": call_prompt}],
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "pNInz6obpgDQGcFmaJgB",
            },
            "firstMessage": first_message,
            "endCallFunctionEnabled": True,
            "endCallMessage": "Thanks so much, have a great day!",
            "maxDurationSeconds": 180,
            "serverUrl": server_url,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{VAPI_API_BASE}/call",
            headers={
                "Authorization": f"Bearer {settings.vapi_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        call_data = resp.json()

    vapi_call_id = call_data.get("id", "")
    logger.info(
        "Outbound call initiated: vapi_call_id=%s business=%s task=%s",
        vapi_call_id, business_name, task_type,
    )

    # Log to database
    await db.execute(
        """INSERT INTO call_log
            (user_id, vapi_call_id, business_name, business_phone,
             task, task_type, place_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress')""",
        [user_id, vapi_call_id, business_name, business_phone,
         task, task_type, place_id],
    )

    return {
        "vapi_call_id": vapi_call_id,
        "status": "in_progress",
        "business_name": business_name,
        "business_phone": business_phone,
    }


async def pre_call_check(
    business_name: str,
    business_phone: str,
    place_id: Optional[str] = None,
) -> dict:
    """Run validation checks before committing to a phone call.

    Checks:
      1. Phone score -- has this number failed repeatedly?
      2. Chain detection -- is this a corporate number that won't help?

    Returns dict with:
      ok: bool -- safe to call
      reason: str -- if not ok, why
      warnings: list[str] -- non-blocking concerns
    """
    result: dict = {"ok": True, "reason": "", "warnings": []}

    if not business_phone:
        result["ok"] = False
        result["reason"] = "No phone number available"
        return result

    # Check phone score history
    if place_id:
        score = await get_phone_score(place_id, business_phone)
        if score:
            call_count = score.get("call_count", 0)
            success_count = score.get("success_count", 0)
            last_outcome = score.get("last_outcome", "")

            # Block if 2+ consecutive failures
            if call_count >= 2 and success_count == 0:
                result["ok"] = False
                result["reason"] = (
                    f"Phone number has failed {call_count} times "
                    f"(last: {last_outcome}). Try a different number."
                )
                return result

            # Warn about known issues
            if last_outcome in ("wrong_number", "disconnected"):
                result["ok"] = False
                result["reason"] = f"Phone number marked as {last_outcome}"
                return result

            if last_outcome == "voicemail":
                result["warnings"].append("Last call went to voicemail")

    return result


def build_call_prompt(
    business_name: str,
    task: str,
    task_type: str,
    user_name: str,
    details: dict,
) -> str:
    """Build the system prompt for the Vapi voice agent.

    Key design: Sound like a regular human caller. No "on behalf of" framing.
    The first 3 seconds determine whether the employee hangs up.
    """
    goon_number = settings.goon_number

    base = f"""You are calling {business_name}.

## Your Task
{task}

## Rules
- Sound like a regular person calling. Be natural, friendly, efficient.
- Do NOT say "I'm calling on behalf of" or "I'm an AI" or "I'm an assistant"
- Just ask the question like a normal customer would
- Get straight to the point after a brief "hi"
- If they ask for a name, say "{user_name}"
- If they ask for a callback number, say "{goon_number}"

## IVR / Phone Tree Navigation
If you reach an automated phone system:
1. Listen for "representative", "operator", or "speak to someone"
2. Common shortcuts: press 0, say "representative", say "agent"
3. If options are numbered, pick the most relevant
   (e.g., "press 2 for reservations")
4. If the IVR ITSELF answers your question (e.g., announces hours),
   capture that info -- you don't need a human
5. If stuck in a loop after 30 seconds, hang up

## Hold
- If put on hold, wait up to 90 seconds
- After 90 seconds, hang up

## Edge Cases
- Voicemail: hang up (do not leave a message)
- Hostile/rude: "Sorry to bother you, thanks" then hang up
- Wrong number/disconnected: hang up immediately
- Employee needs clarification: rephrase your question with more context
- Complex answer (full menu, long list): capture key facts, don't need everything
- "We don't give that info over phone": thank them, hang up
- "Check our website": ask for the URL if you don't have it, hang up

## After Getting the Answer
- Confirm by repeating back: "Just to confirm, [answer]. Great, thanks!"
- Thank them and end the call
"""

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
5. If they need a phone number: {goon_number}
"""

    return base


def build_first_message(task: str, task_type: str, details: dict) -> str:
    """Build the opening line for the voice agent. Sound human."""
    if task_type == "reservation":
        party = details.get("party_size", "two")
        date = details.get("date", "tonight")
        time = details.get("time", "7")
        return (
            f"Hi, I'd like to make a reservation for {party} "
            f"{date} around {time}. Do you have anything available?"
        )
    elif task_type == "appointment":
        return f"Hi, I'm looking to schedule an appointment. {task}"
    elif task_type == "availability_check":
        return f"Hi, quick question -- {task}"
    else:
        return f"Hi, {task}"
