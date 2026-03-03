"""Failure tracking — auto-log failures with type, severity, and context."""
from __future__ import annotations

import json
import logging

from app.db.database import db

logger = logging.getLogger(__name__)

# Severity mapping by failure type
SEVERITY_MAP: dict[str, str] = {
    "wrong_number": "high",
    "hung_up": "medium",
    "busy": "low",
    "no_answer": "low",
    "no-answer": "low",
    "voicemail": "low",
    "timeout": "medium",
    "composition_failure": "medium",
    "webhook_error": "high",
}


async def log_failure(
    failure_type: str,
    description: str,
    user_id: str | None = None,
    call_log_id: int | None = None,
    business_name: str | None = None,
    place_id: str | None = None,
    severity: str | None = None,
    context: dict | None = None,
) -> int:
    """Insert a failure_log record. Returns the row id."""
    sev = severity or SEVERITY_MAP.get(failure_type, "medium")
    ctx = json.dumps(context) if context else None
    try:
        row_id = await db.execute(
            """INSERT INTO failure_log
               (user_id, call_log_id, failure_type, severity,
                business_name, place_id, description, context)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [user_id, call_log_id, failure_type, sev,
             business_name, place_id, description, ctx],
        )
        return row_id
    except Exception:
        logger.exception("Failed to log failure: %s", failure_type)
        return 0
