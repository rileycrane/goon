"""Tests for the memory service (Component 6)."""

import json
from pathlib import Path

import pytest
import pytest_asyncio

from app.services.memory import (
    UserMemory,
    add_task,
    append_conversation,
    complete_task,
    get_business_conversations,
    load_memory,
    save_profile,
    save_tasks,
    update_memory,
)


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Point USER_DATA_DIR to a temp directory for test isolation."""
    monkeypatch.setattr("app.services.memory.USER_DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def user_id():
    return "+14155551234"


@pytest.fixture
def user_dir(tmp_data_dir, user_id):
    d = tmp_data_dir / user_id
    d.mkdir(parents=True)
    return d


# --- UserMemory dataclass ---


class TestUserMemory:
    def test_formatted_recent_empty(self):
        mem = UserMemory(soul="", profile="", recent=[])
        assert mem.formatted_recent == ""

    def test_formatted_recent_respects_limit(self):
        messages = [
            {"timestamp": f"2026-02-28T10:0{i}:00", "direction": "in", "text": f"msg {i}"}
            for i in range(10)
        ]
        mem = UserMemory(soul="", profile="", recent=messages)
        lines = mem.formatted_recent.strip().split("\n")
        # Default MEMORY_CONTEXT_LIMIT is 5
        assert len(lines) == 5

    def test_formatted_recent_direction_labels(self):
        mem = UserMemory(
            soul="",
            profile="",
            recent=[
                {"timestamp": "2026-02-28T10:00:00", "direction": "in", "text": "hello"},
                {"timestamp": "2026-02-28T10:01:00", "direction": "out", "text": "hi there"},
            ],
        )
        result = mem.formatted_recent
        assert "User: hello" in result
        assert "You: hi there" in result

    def test_formatted_tasks_empty(self):
        mem = UserMemory(soul="", profile="", active_tasks=[])
        assert mem.formatted_tasks == "(no active tasks)"

    def test_formatted_tasks_with_items(self):
        mem = UserMemory(
            soul="",
            profile="",
            active_tasks=[
                {"status": "pending", "description": "Call Delfina"},
                {"status": "completed", "description": "Check hours"},
            ],
        )
        result = mem.formatted_tasks
        assert "[pending] Call Delfina" in result
        assert "[completed] Check hours" in result


# --- load_memory ---


class TestLoadMemory:
    @pytest.mark.asyncio
    async def test_new_user_gets_defaults(self, tmp_data_dir, user_id):
        mem = await load_memory(user_id)
        assert "New User" in mem.profile
        assert user_id in mem.profile
        assert mem.recent == []
        assert mem.active_tasks == []

    @pytest.mark.asyncio
    async def test_loads_existing_profile(self, user_dir, user_id):
        (user_dir / "profile.md").write_text("# Riley\nLikes pizza")
        mem = await load_memory(user_id)
        assert "Riley" in mem.profile
        assert "pizza" in mem.profile

    @pytest.mark.asyncio
    async def test_loads_conversations(self, user_dir, user_id):
        entries = [
            {"timestamp": "2026-02-28T10:00:00", "direction": "in", "text": "hello"},
            {"timestamp": "2026-02-28T10:01:00", "direction": "out", "text": "hi"},
        ]
        with open(user_dir / "conversations.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        mem = await load_memory(user_id)
        assert len(mem.recent) == 2
        assert mem.recent[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_loads_tasks(self, user_dir, user_id):
        tasks = [{"id": 1, "description": "Call barbershop", "status": "pending"}]
        (user_dir / "tasks.json").write_text(json.dumps(tasks))

        mem = await load_memory(user_id)
        assert len(mem.active_tasks) == 1
        assert mem.active_tasks[0]["description"] == "Call barbershop"

    @pytest.mark.asyncio
    async def test_handles_corrupt_jsonl(self, user_dir, user_id):
        with open(user_dir / "conversations.jsonl", "w") as f:
            f.write('{"valid": true}\n')
            f.write("NOT JSON\n")
            f.write('{"also_valid": true}\n')

        mem = await load_memory(user_id)
        assert len(mem.recent) == 2  # Skips the corrupt line

    @pytest.mark.asyncio
    async def test_recent_limit(self, user_dir, user_id):
        with open(user_dir / "conversations.jsonl", "w") as f:
            for i in range(50):
                f.write(json.dumps({"timestamp": f"T{i}", "direction": "in", "text": f"msg{i}"}) + "\n")

        mem = await load_memory(user_id)
        assert len(mem.recent) == 20  # MEMORY_RECENT_LIMIT


# --- append_conversation ---


class TestAppendConversation:
    @pytest.mark.asyncio
    async def test_creates_directory_and_file(self, tmp_data_dir, user_id):
        await append_conversation(user_id, "in", "hello world")

        convos_path = tmp_data_dir / user_id / "conversations.jsonl"
        assert convos_path.exists()
        lines = convos_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["direction"] == "in"
        assert entry["text"] == "hello world"
        assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_appends_to_existing(self, user_dir, user_id):
        (user_dir / "conversations.jsonl").write_text(
            json.dumps({"timestamp": "T0", "direction": "in", "text": "first"}) + "\n"
        )

        await append_conversation(user_id, "out", "second")

        lines = (user_dir / "conversations.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_includes_metadata(self, tmp_data_dir, user_id):
        await append_conversation(user_id, "in", "hey", metadata={"message_sid": "SM123"})

        convos_path = tmp_data_dir / user_id / "conversations.jsonl"
        entry = json.loads(convos_path.read_text().strip())
        assert entry["message_sid"] == "SM123"


# --- update_memory ---


class TestUpdateMemory:
    @pytest.mark.asyncio
    async def test_records_both_sides(self, tmp_data_dir, user_id):
        await update_memory(user_id, "what time does Delfina close?", "They close at 10pm.")

        convos_path = tmp_data_dir / user_id / "conversations.jsonl"
        lines = convos_path.read_text().strip().split("\n")
        assert len(lines) == 2

        inbound = json.loads(lines[0])
        assert inbound["direction"] == "in"
        assert "Delfina" in inbound["text"]

        outbound = json.loads(lines[1])
        assert outbound["direction"] == "out"
        assert "10pm" in outbound["text"]


# --- save_profile / save_tasks ---


class TestProfileAndTasks:
    @pytest.mark.asyncio
    async def test_save_and_load_profile(self, tmp_data_dir, user_id):
        await save_profile(user_id, "# Test User\nLikes tacos")
        mem = await load_memory(user_id)
        assert "tacos" in mem.profile

    @pytest.mark.asyncio
    async def test_save_and_load_tasks(self, tmp_data_dir, user_id):
        tasks = [{"id": 1, "description": "Book dinner", "status": "pending"}]
        await save_tasks(user_id, tasks)
        mem = await load_memory(user_id)
        assert len(mem.active_tasks) == 1


# --- add_task / complete_task ---


class TestTaskManagement:
    @pytest.mark.asyncio
    async def test_add_task(self, tmp_data_dir, user_id):
        task = await add_task(user_id, "Call Delfina", trigger="user_request")
        assert task["id"] == 1
        assert task["status"] == "pending"
        assert task["description"] == "Call Delfina"

        mem = await load_memory(user_id)
        assert len(mem.active_tasks) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_tasks(self, tmp_data_dir, user_id):
        await add_task(user_id, "Task 1")
        await add_task(user_id, "Task 2")
        mem = await load_memory(user_id)
        assert len(mem.active_tasks) == 2
        assert mem.active_tasks[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_complete_task(self, tmp_data_dir, user_id):
        await add_task(user_id, "Book dinner")
        result = await complete_task(user_id, 1)
        assert result is True

        mem = await load_memory(user_id)
        assert mem.active_tasks[0]["status"] == "completed"
        assert "completed_at" in mem.active_tasks[0]

    @pytest.mark.asyncio
    async def test_complete_nonexistent_task(self, tmp_data_dir, user_id):
        await add_task(user_id, "Book dinner")
        result = await complete_task(user_id, 999)
        assert result is False


# --- get_business_conversations ---


class TestBusinessConversations:
    @pytest.mark.asyncio
    async def test_filters_by_business(self, user_dir, user_id):
        entries = [
            {"timestamp": "T1", "direction": "in", "text": "What time does Delfina close?"},
            {"timestamp": "T2", "direction": "out", "text": "Delfina closes at 10pm"},
            {"timestamp": "T3", "direction": "in", "text": "How about Whole Foods?"},
            {"timestamp": "T4", "direction": "out", "text": "Whole Foods closes at 9pm"},
            {"timestamp": "T5", "direction": "in", "text": "Book Delfina for Friday"},
        ]
        with open(user_dir / "conversations.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        results = await get_business_conversations(user_id, "Delfina")
        assert len(results) == 3
        assert all("delfina" in r["text"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_case_insensitive(self, user_dir, user_id):
        entries = [
            {"timestamp": "T1", "direction": "in", "text": "DELFINA table please"},
        ]
        with open(user_dir / "conversations.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        results = await get_business_conversations(user_id, "delfina")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_respects_limit(self, user_dir, user_id):
        entries = [
            {"timestamp": f"T{i}", "direction": "in", "text": f"Delfina msg {i}"}
            for i in range(20)
        ]
        with open(user_dir / "conversations.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        results = await get_business_conversations(user_id, "Delfina", limit=3)
        assert len(results) == 3
        # Should be the LAST 3
        assert results[0]["text"] == "Delfina msg 17"

    @pytest.mark.asyncio
    async def test_no_matches(self, user_dir, user_id):
        entries = [
            {"timestamp": "T1", "direction": "in", "text": "hello"},
        ]
        with open(user_dir / "conversations.jsonl", "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        results = await get_business_conversations(user_id, "Delfina")
        assert results == []
