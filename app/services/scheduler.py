"""Scheduling — closed-business queuing, exponential backoff retries."""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta

from app.db.database import db

logger = logging.getLogger(__name__)

# Base retry delays in minutes by failure reason
BASE_DELAYS: dict[str, int] = {
    "busy": 5,
    "no_answer": 10,
    "no-answer": 10,
    "voicemail": 30,
    "hung_up": 15,
    "timeout": 20,
}

MAX_RETRY_DELAY_MINUTES = 240  # 4 hours


async def queue_call_for_opening(
    user_id: str,
    business_name: str,
    business_phone: str,
    task: str,
    task_type: str,
    place_id: str | None,
    opening_time: datetime,
) -> int:
    """Queue a call for 15min after opening. Returns scheduled_task id."""
    call_at = opening_time + timedelta(minutes=15)
    call_params = {
        "business_name": business_name,
        "business_phone": business_phone,
        "task": task,
        "task_type": task_type,
        "place_id": place_id,
        "user_id": user_id,
    }
    task_id = await db.execute(
        """INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
           VALUES (?, ?, 'closed_business_queue', ?, 'pending')""",
        [user_id, json.dumps(call_params), call_at.isoformat()],
    )
    logger.info(
        "Queued call for %s to %s at %s (task_id=%d)",
        user_id, business_name, call_at.isoformat(), task_id,
    )
    return task_id


def compute_retry_delay(retry_count: int, failure_reason: str) -> int:
    """Exponential backoff with jitter. Returns delay in minutes.

    Formula: base * (2^retry_count) + random(0, base/2)
    Cap: 4 hours.
    """
    base = BASE_DELAYS.get(failure_reason, 10)
    delay = base * (2 ** retry_count) + random.randint(0, base // 2)
    return min(delay, MAX_RETRY_DELAY_MINUTES)


async def process_queued_calls() -> int:
    """Process closed_business_queue tasks that are due.

    Initiates calls directly. Returns count processed.
    """
    from app.services.calls import initiate_outbound_call
    from app.services.sms import send_sms

    now = datetime.now().isoformat()
    pending = await db.fetch_all(
        """SELECT * FROM scheduled_tasks
           WHERE trigger = 'closed_business_queue' AND status = 'pending'
           AND due_at <= ?""",
        [now],
    )

    count = 0
    for task in pending:
        try:
            params = json.loads(task["message"])
            user_id = params["user_id"]
            biz_name = params["business_name"]

            # Notify user
            await send_sms(
                user_id,
                f"Calling {biz_name} now -- they just opened.",
            )

            # Initiate the call
            await initiate_outbound_call(
                business_name=biz_name,
                business_phone=params["business_phone"],
                task=params["task"],
                user_id=user_id,
                task_type=params.get("task_type", "information"),
                place_id=params.get("place_id"),
            )

            await db.execute(
                "UPDATE scheduled_tasks SET status = 'fired' WHERE id = ?",
                [task["id"]],
            )
            count += 1
            logger.info("Fired queued call: task_id=%d biz=%s", task["id"], biz_name)

        except Exception:
            logger.exception("Failed to fire queued call: task_id=%d", task["id"])

    return count
