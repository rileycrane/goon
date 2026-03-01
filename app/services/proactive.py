"""Proactive intelligence — trigger-based outreach, scheduled tasks.

Design principle: deterministic trigger computation (no LLM), then LLM
message composition only when we have something concrete to say. We never
run an LLM speculatively for every user.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from app.config import settings
from app.db.database import db
from app.services.memory import append_conversation, load_memory
from app.services.sms import send_sms

logger = logging.getLogger(__name__)


async def compute_triggers(user_id: str) -> list[dict]:
    """Check for actionable triggers for a user (deterministic, no LLM).

    Returns a list of trigger dicts, each with at least a "type" key.
    Empty list means nothing to say — skip this user.
    """
    triggers: list[dict] = []
    now = datetime.now()

    # 1. Scheduled followups that are due
    due_tasks = await db.fetch_all(
        """
        SELECT * FROM scheduled_tasks
        WHERE user_id = ? AND due_at <= ? AND status = 'pending'
        """,
        [user_id, now.isoformat()],
    )
    for task in due_tasks:
        triggers.append({
            "type": "scheduled_followup",
            "message": task["message"],
            "trigger": task.get("trigger", ""),
            "scheduled_task_id": task["id"],
        })
        await db.execute(
            "UPDATE scheduled_tasks SET status = 'fired' WHERE id = ?",
            [task["id"]],
        )

    # 2. Pending call retries that are due
    retries = await db.fetch_all(
        """
        SELECT * FROM call_log
        WHERE user_id = ? AND status = 'retry_pending' AND retry_after <= ?
        """,
        [user_id, now.isoformat()],
    )
    for retry in retries:
        triggers.append({
            "type": "call_retry",
            "business_name": retry["business_name"],
            "task": retry["task"],
            "retry_count": retry["retry_count"],
            "call_log_id": retry["id"],
        })

    # 3. Profile pattern matching
    profile_triggers = await _check_profile_patterns(user_id, now)
    triggers.extend(profile_triggers)

    return triggers


async def _check_profile_patterns(
    user_id: str, now: datetime
) -> list[dict]:
    """Parse user profile for time-based patterns. No LLM — pure text matching."""
    triggers: list[dict] = []

    try:
        memory = await load_memory(user_id)
    except Exception:
        logger.warning("Could not load memory for %s", user_id)
        return triggers

    profile = memory.profile.lower()

    # Friday dinner pattern
    if now.weekday() == 4 and 6 <= now.hour < 12:
        if "friday" in profile and "dinner" in profile:
            if not _mentioned_today(memory.recent, now, ["dinner", "reservation"]):
                triggers.append({
                    "type": "pattern_match",
                    "pattern": "friday_dinner",
                    "detail": "It's Friday morning -- user typically books dinner.",
                })

    # Recurring service due (e.g. "haircut every 6 weeks, last: 2026-02-10")
    service_pattern = re.compile(
        r"(\w[\w\s]*?)\s+every\s+~?(\d+)\s+(weeks?|days?),\s*last:\s*(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    )
    for match in service_pattern.finditer(memory.profile):
        service = match.group(1).strip()
        interval = int(match.group(2))
        unit = match.group(3).lower()
        last_str = match.group(4)

        try:
            last_date = datetime.strptime(last_str, "%Y-%m-%d")
        except ValueError:
            continue

        if unit.startswith("week"):
            delta = timedelta(weeks=interval)
        else:
            delta = timedelta(days=interval)

        next_due = last_date + delta
        # Fire if within 3 days of due
        if next_due.date() <= now.date() <= (next_due + timedelta(days=3)).date():
            if not _mentioned_today(memory.recent, now, [service.lower()]):
                triggers.append({
                    "type": "recurring_service_due",
                    "service": service,
                    "last_date": last_str,
                    "next_due": next_due.strftime("%Y-%m-%d"),
                })

    return triggers


def _mentioned_today(
    recent: list[dict], now: datetime, keywords: list[str]
) -> bool:
    """Check if any keyword was mentioned in today's messages."""
    today = now.strftime("%Y-%m-%d")
    for msg in recent:
        ts = msg.get("timestamp", "")
        if not ts.startswith(today):
            continue
        text = msg.get("text", "").lower()
        if any(kw in text for kw in keywords):
            return True
    return False


async def compose_proactive_message(
    user_id: str, triggers: list[dict]
) -> Optional[str]:
    """Generate a proactive SMS from trigger data (uses LLM).

    Returns None if the LLM decides there's nothing useful to say.
    """
    if not triggers:
        return None

    try:
        memory = await load_memory(user_id)
    except Exception:
        logger.warning("Could not load memory for compose, user %s", user_id)
        return None

    trigger_lines = []
    for t in triggers:
        if t["type"] == "scheduled_followup":
            trigger_lines.append(f"- Scheduled followup: {t['message']}")
        elif t["type"] == "call_retry":
            trigger_lines.append(
                f"- Pending retry: call {t['business_name']} about {t['task']}"
            )
        elif t["type"] == "pattern_match":
            trigger_lines.append(f"- Pattern: {t['detail']}")
        elif t["type"] == "recurring_service_due":
            trigger_lines.append(
                f"- {t['service']} is due (last: {t['last_date']}, "
                f"due: {t['next_due']})"
            )
        else:
            trigger_lines.append(f"- {t['type']}: {t.get('detail', '')}")

    trigger_summary = "\n".join(trigger_lines)
    profile_excerpt = memory.profile[:500]

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""Compose a short proactive SMS (under 160 chars, no emoji) for a user.

Triggers:
{trigger_summary}

User context:
{profile_excerpt}

Rules:
1. Be warm and brief, like a helpful friend texting
2. Suggest a specific action (e.g. "Want me to call them?" or "Should I book it?")
3. One message, one primary topic (pick the most time-sensitive trigger)
4. No emoji -- they force unicode encoding and halve SMS capacity
5. If multiple triggers, you can mention a second briefly
6. If you genuinely can't compose something useful, respond with exactly: SKIP

Return ONLY the SMS text, nothing else.""",
                }
            ],
        )

        text = response.content[0].text.strip()
        if text.upper() == "SKIP":
            return None
        # Strip any quotes the LLM might wrap the message in
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text
    except Exception:
        logger.exception("Failed to compose proactive message for user %s", user_id)
        return None


async def run_proactive_checks() -> int:
    """Run proactive trigger checks for all active users.

    Returns the number of messages sent.
    """
    users = await db.fetch_all(
        "SELECT id FROM users WHERE subscription_status IN ('active', 'trial')"
    )

    sent = 0
    for user in users:
        user_id = user["id"]
        try:
            triggers = await compute_triggers(user_id)
            if not triggers:
                continue

            message = await compose_proactive_message(user_id, triggers)
            if not message:
                continue

            await send_sms(user_id, message)
            await append_conversation(
                user_id,
                "out",
                message,
                metadata={"type": "proactive", "triggers": [t["type"] for t in triggers]},
            )
            sent += 1
            logger.info("Proactive message sent to %s: %s", user_id, message[:60])

        except Exception:
            logger.exception("Proactive check failed for user %s", user_id)

    logger.info("Proactive check complete: %d messages sent for %d users", sent, len(users))
    return sent
