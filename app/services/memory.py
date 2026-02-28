"""User memory — persistent profiles, conversation logs, preference tracking."""

from pathlib import Path


async def load_memory(user_id: str) -> dict:
    """Load user profile and recent conversation history."""
    # TODO: read profile.md + recent conversations.jsonl
    raise NotImplementedError


async def update_memory(user_id: str, updates: dict) -> None:
    """Update user profile with new information."""
    # TODO: merge updates into profile.md
    raise NotImplementedError
