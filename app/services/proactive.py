"""Proactive intelligence — trigger-based outreach, scheduled tasks."""
from __future__ import annotations


async def compute_triggers(user_id: str) -> list[dict]:
    """Check for actionable triggers for a user (deterministic, no LLM)."""
    # TODO: check scheduled_tasks, recurring patterns, overdue services
    raise NotImplementedError


async def compose_proactive_message(user_id: str, trigger: dict) -> str:
    """Generate a proactive message for a triggered event (uses LLM)."""
    # TODO: use Claude to compose a natural message from trigger data
    raise NotImplementedError
