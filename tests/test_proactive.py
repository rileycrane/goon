"""Tests for proactive intelligence — trigger computation and message flow."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import pytest_asyncio

from app.db.database import Database
from app.services.proactive import (
    _check_profile_patterns,
    _mentioned_today,
    compose_proactive_message,
    compute_triggers,
    run_proactive_checks,
)


@pytest_asyncio.fixture
async def proactive_db(tmp_path):
    """Fresh database with a test user."""
    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).parent.parent / "app" / "db" / "schema.sql"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    schema = schema_path.read_text()
    await conn.executescript(schema)
    await conn.commit()

    test_database = Database()
    test_database._conn = conn

    # Insert test user
    await conn.execute(
        "INSERT INTO users (id, phone, subscription_status) VALUES (?, ?, ?)",
        ["+15551234567", "+15551234567", "active"],
    )
    await conn.commit()

    yield test_database

    await conn.close()


@pytest.fixture
def user_data_dir(tmp_path):
    """Set up a temp user data directory with profile."""
    user_dir = tmp_path / "users" / "+15551234567"
    user_dir.mkdir(parents=True)
    return user_dir


# --- _mentioned_today ---


def test_mentioned_today_finds_keyword():
    now = datetime(2026, 3, 1, 10, 0)
    recent = [
        {"timestamp": "2026-03-01T09:30:00", "text": "Can you book dinner tonight?"},
    ]
    assert _mentioned_today(recent, now, ["dinner"]) is True


def test_mentioned_today_ignores_yesterday():
    now = datetime(2026, 3, 1, 10, 0)
    recent = [
        {"timestamp": "2026-02-28T20:00:00", "text": "Thanks for the dinner reservation."},
    ]
    assert _mentioned_today(recent, now, ["dinner"]) is False


def test_mentioned_today_no_match():
    now = datetime(2026, 3, 1, 10, 0)
    recent = [
        {"timestamp": "2026-03-01T09:30:00", "text": "What's the weather?"},
    ]
    assert _mentioned_today(recent, now, ["dinner", "reservation"]) is False


# --- compute_triggers: scheduled_followup ---


@pytest.mark.asyncio
async def test_compute_triggers_scheduled_followup(proactive_db):
    """Due scheduled tasks become triggers and get marked as fired."""
    now = datetime.now()
    past = (now - timedelta(hours=1)).isoformat()

    await proactive_db.execute(
        """
        INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        ["+15551234567", "Confirm your reservation", "reservation_check", past],
    )

    with patch("app.services.proactive.db", proactive_db):
        triggers = await compute_triggers("+15551234567")

    assert len(triggers) == 1
    assert triggers[0]["type"] == "scheduled_followup"
    assert triggers[0]["message"] == "Confirm your reservation"

    # Verify task was marked fired
    task = await proactive_db.fetch_one(
        "SELECT status FROM scheduled_tasks WHERE user_id = ?",
        ["+15551234567"],
    )
    assert task["status"] == "fired"


@pytest.mark.asyncio
async def test_compute_triggers_skips_future_tasks(proactive_db):
    """Tasks due in the future should not trigger."""
    future = (datetime.now() + timedelta(hours=2)).isoformat()

    await proactive_db.execute(
        """
        INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        ["+15551234567", "Future task", "test", future],
    )

    with patch("app.services.proactive.db", proactive_db):
        triggers = await compute_triggers("+15551234567")

    assert len(triggers) == 0


@pytest.mark.asyncio
async def test_compute_triggers_skips_fired_tasks(proactive_db):
    """Already-fired tasks should not trigger again."""
    past = (datetime.now() - timedelta(hours=1)).isoformat()

    await proactive_db.execute(
        """
        INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
        VALUES (?, ?, ?, ?, 'fired')
        """,
        ["+15551234567", "Already sent", "test", past],
    )

    with patch("app.services.proactive.db", proactive_db):
        triggers = await compute_triggers("+15551234567")

    assert len(triggers) == 0


# --- compute_triggers: call_retry ---


@pytest.mark.asyncio
async def test_compute_triggers_call_retry(proactive_db):
    """Pending call retries that are due should trigger."""
    past = (datetime.now() - timedelta(minutes=5)).isoformat()

    await proactive_db.execute(
        """
        INSERT INTO call_log
            (user_id, business_name, business_phone, task, status, retry_count, retry_after)
        VALUES (?, ?, ?, ?, 'retry_pending', 1, ?)
        """,
        ["+15551234567", "Delfina", "+14155551234", "Make reservation", past],
    )

    with patch("app.services.proactive.db", proactive_db):
        triggers = await compute_triggers("+15551234567")

    retry_triggers = [t for t in triggers if t["type"] == "call_retry"]
    assert len(retry_triggers) == 1
    assert retry_triggers[0]["business_name"] == "Delfina"


# --- _check_profile_patterns ---


@pytest.mark.asyncio
async def test_profile_pattern_recurring_service(user_data_dir):
    """Recurring service due date triggers a nudge."""
    from app.services.memory import UserMemory

    # Set up profile with a service due today
    today = datetime.now()
    last_date = (today - timedelta(weeks=6)).strftime("%Y-%m-%d")
    profile_text = f"""# User Profile
## Regular Services
- haircut every 6 weeks, last: {last_date}
"""
    (user_data_dir / "profile.md").write_text(profile_text)

    memory = UserMemory(soul="", profile=profile_text, recent=[])

    with patch("app.services.proactive.load_memory", return_value=memory):
        triggers = await _check_profile_patterns("+15551234567", today)

    service_triggers = [t for t in triggers if t["type"] == "recurring_service_due"]
    assert len(service_triggers) == 1
    assert service_triggers[0]["service"] == "haircut"


@pytest.mark.asyncio
async def test_profile_pattern_friday_dinner():
    """Friday morning + dinner pattern in profile triggers a nudge."""
    from app.services.memory import UserMemory

    profile_text = """# User Profile
## Preferences
- Usually books dinner on Friday evenings
- Favorite: Delfina, Flour + Water
"""
    friday_9am = datetime(2026, 3, 6, 9, 0)  # March 6, 2026 is a Friday

    memory = UserMemory(soul="", profile=profile_text, recent=[])

    with patch("app.services.proactive.load_memory", return_value=memory):
        triggers = await _check_profile_patterns("+15551234567", friday_9am)

    pattern_triggers = [t for t in triggers if t["type"] == "pattern_match"]
    assert len(pattern_triggers) == 1
    assert pattern_triggers[0]["pattern"] == "friday_dinner"


@pytest.mark.asyncio
async def test_profile_pattern_friday_skips_if_already_mentioned():
    """Don't trigger Friday dinner if user already texted about dinner today."""
    from app.services.memory import UserMemory

    profile_text = "Usually books dinner on Friday evenings"
    friday_9am = datetime(2026, 3, 6, 9, 0)

    memory = UserMemory(
        soul="",
        profile=profile_text,
        recent=[
            {"timestamp": "2026-03-06T08:30:00", "text": "Book me dinner at Delfina"},
        ],
    )

    with patch("app.services.proactive.load_memory", return_value=memory):
        triggers = await _check_profile_patterns("+15551234567", friday_9am)

    assert len(triggers) == 0


# --- compose_proactive_message ---


@pytest.mark.asyncio
async def test_compose_returns_none_for_empty_triggers():
    result = await compose_proactive_message("+15551234567", [])
    assert result is None


@pytest.mark.asyncio
async def test_compose_calls_llm():
    """compose_proactive_message calls Claude and returns the text."""
    from app.services.memory import UserMemory

    memory = UserMemory(soul="", profile="# Test User", recent=[])

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text="Haircut is due! Want me to call Joe's?")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    triggers = [
        {"type": "recurring_service_due", "service": "haircut",
         "last_date": "2026-01-20", "next_due": "2026-03-03"},
    ]

    with patch("app.services.proactive.load_memory", return_value=memory), \
         patch("app.services.proactive.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await compose_proactive_message("+15551234567", triggers)

    assert result == "Haircut is due! Want me to call Joe's?"
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_compose_returns_none_on_skip():
    """If the LLM says SKIP, return None."""
    from app.services.memory import UserMemory

    memory = UserMemory(soul="", profile="# Test User", recent=[])

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text="SKIP")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    triggers = [{"type": "pattern_match", "pattern": "test", "detail": "test detail"}]

    with patch("app.services.proactive.load_memory", return_value=memory), \
         patch("app.services.proactive.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await compose_proactive_message("+15551234567", triggers)

    assert result is None


# --- run_proactive_checks ---


@pytest.mark.asyncio
async def test_run_proactive_checks_sends_messages(proactive_db):
    """Full flow: due task -> compose -> send SMS -> log."""
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    await proactive_db.execute(
        """
        INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        ["+15551234567", "Check on your reservation", "reservation", past],
    )

    mock_compose = AsyncMock(return_value="Hey, just checking on your reservation. All good?")
    mock_send = AsyncMock()
    mock_append = AsyncMock()

    with patch("app.services.proactive.db", proactive_db), \
         patch("app.services.proactive.compose_proactive_message", mock_compose), \
         patch("app.services.proactive.send_sms", mock_send), \
         patch("app.services.proactive.append_conversation", mock_append):
        sent = await run_proactive_checks()

    assert sent == 1
    mock_send.assert_called_once_with(
        "+15551234567", "Hey, just checking on your reservation. All good?"
    )
    mock_append.assert_called_once()


@pytest.mark.asyncio
async def test_run_proactive_checks_skips_no_triggers(proactive_db):
    """Users with no due triggers get skipped."""
    mock_send = AsyncMock()

    with patch("app.services.proactive.db", proactive_db), \
         patch("app.services.proactive.send_sms", mock_send):
        sent = await run_proactive_checks()

    assert sent == 0
    mock_send.assert_not_called()
