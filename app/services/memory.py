"""
Memory & Personal OS — Component 6

Maintains a persistent, evolving profile for each user.
Every interaction makes Goon smarter about that person.

Storage format:
  data/users/{phone}/
    profile.md          — Who they are, preferences, patterns (LLM-readable/writable)
    conversations.jsonl  — Raw conversation log (append-only)
    tasks.json           — Active/pending tasks + scheduled followups
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)

MEMORY_CONTEXT_LIMIT = 20
MEMORY_RECENT_LIMIT = 50
USER_DATA_DIR = Path(settings.user_data_dir)


@dataclass
class UserMemory:
    """In-memory representation of a user's persistent state."""

    profile: str
    recent: list[dict] = field(default_factory=list)
    active_tasks: list[dict] = field(default_factory=list)

    @property
    def formatted_recent(self) -> str:
        """Last N messages formatted for LLM context injection."""
        lines = []
        for m in self.recent[-MEMORY_CONTEXT_LIMIT:]:
            direction = "You" if m.get("direction") == "out" else "User"
            ts = m.get("timestamp", "")[:16]
            text = m.get("text", "")[:200]
            lines.append(f"[{ts}] {direction}: {text}")
        return "\n".join(lines)

    @property
    def formatted_tasks(self) -> str:
        """Active tasks formatted for LLM context injection."""
        if not self.active_tasks:
            return "(no active tasks)"
        lines = []
        for t in self.active_tasks:
            status = t.get("status", "pending")
            desc = t.get("description", "")
            lines.append(f"- [{status}] {desc}")
        return "\n".join(lines)


def _user_dir(user_id: str) -> Path:
    """Get the data directory for a user. user_id is typically a phone number."""
    return USER_DATA_DIR / user_id


async def load_memory(user_id: str) -> UserMemory:
    """Load a user's full memory state from disk."""
    user_dir = _user_dir(user_id)

    profile = await _load_profile(user_dir, user_id)
    recent = await _load_conversations(user_dir)
    tasks = await _load_tasks(user_dir)

    return UserMemory(
        profile=profile,
        recent=recent[-MEMORY_RECENT_LIMIT:],
        active_tasks=tasks,
    )


async def _load_profile(user_dir: Path, user_id: str) -> str:
    """Load profile.md or return a default for new users."""
    profile_path = user_dir / "profile.md"
    try:
        async with aiofiles.open(profile_path, "r") as f:
            return await f.read()
    except FileNotFoundError:
        return f"# New User\nPhone: {user_id}\nNo profile yet."


async def _load_conversations(user_dir: Path) -> list[dict]:
    """Load conversation history from JSONL."""
    convos_path = user_dir / "conversations.jsonl"
    messages: list[dict] = []
    try:
        async with aiofiles.open(convos_path, "r") as f:
            content = await f.read()
            for line in content.strip().split("\n"):
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return messages


async def _load_tasks(user_dir: Path) -> list[dict]:
    """Load active tasks from tasks.json."""
    tasks_path = user_dir / "tasks.json"
    try:
        async with aiofiles.open(tasks_path, "r") as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


async def append_conversation(
    user_id: str, direction: str, text: str, metadata: dict | None = None
) -> None:
    """Append a single message to the conversation log."""
    user_dir = _user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "direction": direction,
        "text": text,
    }
    if metadata:
        entry.update(metadata)

    try:
        async with aiofiles.open(user_dir / "conversations.jsonl", "a") as f:
            await f.write(json.dumps(entry) + "\n")
    except Exception:
        logger.exception("Failed to append conversation for user %s", user_id)


async def update_memory(
    user_id: str,
    user_message: str,
    response_text: str,
    memory_updates: list[dict] | None = None,
) -> None:
    """Record a conversation exchange and apply any LLM-generated memory updates."""
    await append_conversation(user_id, "in", user_message)
    await append_conversation(user_id, "out", response_text)

    if memory_updates:
        user_dir = _user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        await apply_profile_updates(user_dir, memory_updates)


async def apply_profile_updates(user_dir: Path, updates: list[dict]) -> None:
    """Merge new facts into the user's profile.md using an LLM."""
    import anthropic

    profile_path = user_dir / "profile.md"
    try:
        async with aiofiles.open(profile_path, "r") as f:
            current = await f.read()
    except FileNotFoundError:
        current = ""

    updates_text = "\n".join(
        f'- [{u.get("category", "general")}] {u.get("content", "")}' for u in updates
    )

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Current profile:

{current}

Apply these updates and return the complete updated profile.md:
{updates_text}

Rules:
- Preserve all existing info unless explicitly contradicted
- Add new info to the appropriate section
- If a pattern emerges (e.g. 3rd time asking about Italian), note it
- Keep markdown format consistent
- Be concise — this is a reference doc, not prose

Return ONLY the updated markdown.""",
                }
            ],
        )
        updated_profile = response.content[0].text
    except Exception:
        logger.exception("Failed to generate profile update via LLM")
        return

    try:
        async with aiofiles.open(profile_path, "w") as f:
            await f.write(updated_profile)
    except Exception:
        logger.exception("Failed to write updated profile for %s", user_dir)


async def save_profile(user_id: str, profile_text: str) -> None:
    """Directly write a profile.md for a user."""
    user_dir = _user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(user_dir / "profile.md", "w") as f:
        await f.write(profile_text)


async def save_tasks(user_id: str, tasks: list[dict]) -> None:
    """Write the tasks.json for a user."""
    user_dir = _user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(user_dir / "tasks.json", "w") as f:
        await f.write(json.dumps(tasks, indent=2))


async def add_task(user_id: str, description: str, trigger: str = "") -> dict:
    """Add a task to the user's task list."""
    tasks = await _load_tasks(_user_dir(user_id))
    task = {
        "id": len(tasks) + 1,
        "description": description,
        "trigger": trigger,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    tasks.append(task)
    await save_tasks(user_id, tasks)
    return task


async def complete_task(user_id: str, task_id: int) -> bool:
    """Mark a task as completed."""
    tasks = await _load_tasks(_user_dir(user_id))
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            await save_tasks(user_id, tasks)
            return True
    return False


async def get_business_conversations(
    user_id: str, business_name: str, limit: int = 5
) -> list[dict]:
    """Get recent conversations mentioning a specific business."""
    all_convos = await _load_conversations(_user_dir(user_id))
    business_lower = business_name.lower()
    matching = [
        m for m in all_convos if business_lower in m.get("text", "").lower()
    ]
    return matching[-limit:]
