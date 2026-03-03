"""
Memory & Personal OS -- Component 6

Maintains a persistent, evolving profile for each user.
Every interaction makes Hold Plz smarter about that person.

Storage format:
  data/users/{phone}/
    USER.md          -- Who they are, preferences, patterns (LLM-readable/writable)
    MEMORY.md        -- Curated long-term memory (distilled from daily logs)
    memory/
      2026-03-03.md  -- Daily logs (append-only, one-line summaries)
    conversations.jsonl  -- Raw conversation log (append-only)
    tasks.json           -- Active/pending tasks + scheduled followups

Legacy migration: profile.md -> USER.md (auto-migrated on load)
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

MEMORY_CONTEXT_LIMIT = 5
MEMORY_RECENT_LIMIT = 20
USER_DATA_DIR = Path(settings.user_data_dir)


@dataclass
class UserMemory:
    """In-memory representation of a user's persistent state."""

    profile: str
    long_term_memory: str = ""
    recent: list[dict] = field(default_factory=list)
    active_tasks: list[dict] = field(default_factory=list)

    @property
    def long_term_memory_section(self) -> str:
        """Long-term memory section for LLM context injection."""
        if not self.long_term_memory:
            return ""
        return f"## Long-Term Memory\n{self.long_term_memory}"

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
    long_term = await _load_long_term_memory(user_dir)
    recent = await _load_conversations(user_dir)
    tasks = await _load_tasks(user_dir)

    return UserMemory(
        profile=profile,
        long_term_memory=long_term,
        recent=recent[-MEMORY_RECENT_LIMIT:],
        active_tasks=tasks,
    )


async def _load_profile(user_dir: Path, user_id: str) -> str:
    """Load USER.md (or legacy profile.md) or return a default for new users."""
    user_md_path = user_dir / "USER.md"
    legacy_path = user_dir / "profile.md"

    # Try USER.md first
    try:
        async with aiofiles.open(user_md_path, "r") as f:
            return await f.read()
    except FileNotFoundError:
        pass

    # Auto-migrate legacy profile.md -> USER.md
    try:
        async with aiofiles.open(legacy_path, "r") as f:
            content = await f.read()
        # Write to new location
        user_dir.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(user_md_path, "w") as f:
            await f.write(content)
        return content
    except FileNotFoundError:
        pass

    return f"# New User\nPhone: {user_id}\nNo profile yet."


async def _load_long_term_memory(user_dir: Path) -> str:
    """Load MEMORY.md if it exists."""
    memory_path = user_dir / "MEMORY.md"
    try:
        async with aiofiles.open(memory_path, "r") as f:
            return await f.read()
    except FileNotFoundError:
        return ""


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


async def append_daily_log(user_id: str, note: str) -> None:
    """Append a one-line summary to today's daily log. No LLM needed."""
    user_dir = _user_dir(user_id)
    memory_dir = user_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    log_path = memory_dir / f"{today}.md"

    timestamp = datetime.now().strftime("%H:%M")
    line = f"- [{timestamp}] {note}\n"

    try:
        async with aiofiles.open(log_path, "a") as f:
            await f.write(line)
    except Exception:
        logger.exception("Failed to append daily log for user %s", user_id)


async def distill_memory(user_id: str) -> None:
    """Periodic LLM pass: daily logs -> MEMORY.md.

    Reads all daily log files, distills into curated long-term memory.
    Called from proactive scheduler, not per-message.
    """
    import anthropic

    user_dir = _user_dir(user_id)
    memory_dir = user_dir / "memory"

    if not memory_dir.exists():
        return

    # Gather daily logs (last 7 days worth)
    log_files = sorted(memory_dir.glob("*.md"))[-7:]
    if not log_files:
        return

    logs_text = ""
    for log_file in log_files:
        try:
            async with aiofiles.open(log_file, "r") as f:
                content = await f.read()
            logs_text += f"\n### {log_file.stem}\n{content}"
        except Exception:
            continue

    if not logs_text.strip():
        return

    # Load existing MEMORY.md
    existing_memory = await _load_long_term_memory(user_dir)

    # Load profile for context
    profile = await _load_profile(user_dir, user_id)

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Distill these daily interaction logs into a curated long-term memory document.

Current MEMORY.md:
{existing_memory or "(empty)"}

User profile:
{profile[:500]}

Recent daily logs:
{logs_text}

Rules:
- Extract patterns, preferences, and important facts
- Remove one-off interactions that won't matter later
- Update existing entries if new info supersedes them
- Keep it concise -- bullet points, not prose
- Organize by category (preferences, routines, relationships, facts)
- This memory persists forever -- only include things worth remembering

Return ONLY the updated MEMORY.md content.""",
                }
            ],
        )
        updated = response.content[0].text.strip()
    except Exception:
        logger.exception("Failed to distill memory for user %s", user_id)
        return

    try:
        async with aiofiles.open(user_dir / "MEMORY.md", "w") as f:
            await f.write(updated)
    except Exception:
        logger.exception("Failed to write MEMORY.md for user %s", user_id)


async def update_memory(
    user_id: str,
    user_message: str,
    response_text: str,
    memory_updates: list[dict] | None = None,
) -> None:
    """Record a conversation exchange and apply any LLM-generated memory updates."""
    await append_conversation(user_id, "in", user_message)
    await append_conversation(user_id, "out", response_text)

    # Append a one-line daily log summary (no LLM)
    summary = user_message[:80]
    await append_daily_log(user_id, f"Asked: {summary}")

    if memory_updates:
        user_dir = _user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        await apply_profile_updates(user_dir, memory_updates)


async def apply_profile_updates(user_dir: Path, updates: list[dict]) -> None:
    """Merge new facts into the user's USER.md using an LLM."""
    import anthropic

    profile_path = user_dir / "USER.md"
    # Also check legacy path
    legacy_path = user_dir / "profile.md"
    try:
        async with aiofiles.open(profile_path, "r") as f:
            current = await f.read()
    except FileNotFoundError:
        try:
            async with aiofiles.open(legacy_path, "r") as f:
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

Apply these updates and return the complete updated USER.md:
{updates_text}

Rules:
- Preserve all existing info unless explicitly contradicted
- Add new info to the appropriate section
- If a pattern emerges (e.g. 3rd time asking about Italian), note it
- Keep markdown format consistent
- Be concise -- this is a reference doc, not prose

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
    """Directly write a USER.md for a user."""
    user_dir = _user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(user_dir / "USER.md", "w") as f:
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
