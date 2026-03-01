"""Tests for outbound call management."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.db.database import Database
from app.routes.vapi_events import classify_call_outcome, summarize_call_result
from app.services.calls import (
    build_call_prompt,
    build_first_message,
    handle_call_failure,
    pre_call_check,
    process_retries,
    schedule_retry,
)


@pytest_asyncio.fixture
async def call_db(tmp_path):
    """Fresh database for call tests."""
    from pathlib import Path

    import aiosqlite

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

    yield test_database

    await conn.close()


# --- classify_call_outcome tests ---


class TestClassifyCallOutcome:
    def test_assistant_ended_with_transcript(self):
        outcome = classify_call_outcome(
            "assistant-ended-call",
            "Agent: Hi, do you have a table? Host: Yes, 7pm works. Agent: Great, thanks!",
        )
        assert outcome["success"] is True

    def test_assistant_ended_short_transcript(self):
        outcome = classify_call_outcome("assistant-ended-call", "Hello?")
        assert outcome["success"] is False
        assert outcome["reason"] == "no_useful_info"
        assert outcome["retry"] is True

    def test_customer_ended_with_transcript(self):
        outcome = classify_call_outcome(
            "customer-ended-call",
            "A" * 150,  # Long enough transcript suggests info was exchanged
        )
        assert outcome["success"] is True

    def test_customer_ended_short(self):
        outcome = classify_call_outcome("customer-ended-call", "Hello?")
        assert outcome["success"] is False
        assert outcome["reason"] == "hung_up"
        assert outcome["retry"] is True

    def test_no_answer(self):
        outcome = classify_call_outcome("no-answer", "")
        assert outcome["success"] is False
        assert outcome["reason"] == "no-answer"
        assert outcome["retry"] is True
        assert outcome["retry_delay_minutes"] == 10

    def test_busy(self):
        outcome = classify_call_outcome("busy", "")
        assert outcome["success"] is False
        assert outcome["reason"] == "busy"
        assert outcome["retry"] is True
        assert outcome["retry_delay_minutes"] == 5

    def test_voicemail(self):
        outcome = classify_call_outcome("voicemail", "")
        assert outcome["success"] is False
        assert outcome["reason"] == "voicemail"
        assert outcome["retry"] is True
        assert outcome["retry_delay_minutes"] == 30

    def test_max_duration(self):
        outcome = classify_call_outcome("max-duration-reached", "hold music...")
        assert outcome["success"] is False
        assert outcome["reason"] == "timeout"
        assert outcome["retry"] is False

    def test_unknown(self):
        outcome = classify_call_outcome("unknown", "")
        assert outcome["success"] is False


# --- build_call_prompt tests ---


class TestBuildCallPrompt:
    def test_basic_prompt(self):
        prompt = build_call_prompt(
            task="What time do you close?",
            task_type="info_query",
            business_name="Pizza Palace",
            user_name="Riley",
        )
        assert "Pizza Palace" in prompt
        assert "What time do you close?" in prompt
        assert "Riley" in prompt
        assert "Do NOT" in prompt

    def test_reservation_prompt(self):
        prompt = build_call_prompt(
            task="Make a reservation",
            task_type="reservation",
            business_name="Delfina",
            user_name="Riley",
            details={"party_size": "4", "date": "Friday", "time": "7pm"},
        )
        assert "Reservation-Specific" in prompt
        assert "4" in prompt
        assert "Friday" in prompt

    def test_appointment_prompt(self):
        prompt = build_call_prompt(
            task="Schedule a haircut",
            task_type="appointment",
            business_name="Salon",
            user_name="Riley",
            details={"service": "haircut", "date": "tomorrow"},
        )
        assert "Appointment-Specific" in prompt
        assert "haircut" in prompt

    def test_ivr_map_included(self):
        prompt = build_call_prompt(
            task="Check hours",
            task_type="info_query",
            business_name="BigCo",
            user_name="Riley",
            ivr_map={"menu_structure": {"1": "hours", "2": "reservations", "0": "operator"}},
        )
        assert "Known IVR Menu" in prompt
        assert "Press 1: hours" in prompt
        assert "Press 0: operator" in prompt


# --- build_first_message tests ---


class TestBuildFirstMessage:
    def test_reservation(self):
        msg = build_first_message(
            "Make a reservation",
            "reservation",
            {"party_size": "2", "date": "tonight", "time": "7"},
        )
        assert "reservation" in msg.lower()
        assert "2" in msg

    def test_appointment(self):
        msg = build_first_message("Schedule a haircut", "appointment")
        assert "appointment" in msg.lower()

    def test_availability(self):
        msg = build_first_message("Do you have the new iPhone in stock?", "availability_check")
        assert "quick question" in msg.lower()

    def test_generic(self):
        msg = build_first_message("What are your hours?", "info_query")
        assert "Hi" in msg
        assert "hours" in msg


# --- handle_call_failure tests ---


async def _insert_test_user(db: Database, phone: str = "+15551234567") -> None:
    """Insert a test user to satisfy foreign key constraints."""
    await db.execute(
        "INSERT OR IGNORE INTO users (id, phone, subscription_status) VALUES (?, ?, 'active')",
        [phone, phone],
    )


async def _insert_call_log(db: Database, vapi_call_id: str = "call_123") -> None:
    """Insert a test call_log record."""
    await _insert_test_user(db)
    await db.execute(
        """INSERT INTO call_log
           (user_id, vapi_call_id, business_name, business_phone, place_id, task, status)
           VALUES (?, ?, ?, ?, ?, ?, 'in_progress')""",
        ["+15551234567", vapi_call_id, "Test Biz", "+15559876543", "place_abc", "test"],
    )


class TestHandleCallFailure:
    @pytest.fixture
    def mock_record(self):
        return {
            "user_id": "+15551234567",
            "business_name": "Test Biz",
            "business_phone": "+15559876543",
            "vapi_call_id": "call_123",
            "place_id": "place_abc",
            "retry_count": 0,
        }

    @pytest.mark.asyncio
    async def test_busy_sends_sms_and_retries(self, call_db, mock_record):
        with patch("app.services.calls.db", call_db), \
             patch("app.services.calls.send_sms", new_callable=AsyncMock) as mock_sms, \
             patch("app.services.calls.schedule_retry", new_callable=AsyncMock) as mock_retry:

            await _insert_call_log(call_db)
            await handle_call_failure(mock_record, {"reason": "busy", "success": False})

            mock_sms.assert_called_once()
            assert "busy" in mock_sms.call_args[0][1].lower()
            mock_retry.assert_called_once_with(mock_record, delay_minutes=5)

    @pytest.mark.asyncio
    async def test_voicemail_sends_sms_and_retries(self, call_db, mock_record):
        with patch("app.services.calls.db", call_db), \
             patch("app.services.calls.send_sms", new_callable=AsyncMock) as mock_sms, \
             patch("app.services.calls.schedule_retry", new_callable=AsyncMock) as mock_retry:

            await _insert_call_log(call_db)
            await handle_call_failure(mock_record, {"reason": "voicemail", "success": False})

            mock_sms.assert_called_once()
            assert "voicemail" in mock_sms.call_args[0][1].lower()
            mock_retry.assert_called_once_with(mock_record, delay_minutes=30)

    @pytest.mark.asyncio
    async def test_hung_up_first_time_retries(self, call_db, mock_record):
        with patch("app.services.calls.db", call_db), \
             patch("app.services.calls.send_sms", new_callable=AsyncMock) as mock_sms, \
             patch("app.services.calls.schedule_retry", new_callable=AsyncMock) as mock_retry:

            await _insert_call_log(call_db)
            await handle_call_failure(mock_record, {"reason": "hung_up", "success": False})

            mock_sms.assert_called_once()
            mock_retry.assert_called_once_with(mock_record, delay_minutes=15)

    @pytest.mark.asyncio
    async def test_hung_up_after_retry_gives_up(self, call_db, mock_record):
        mock_record["retry_count"] = 2
        with patch("app.services.calls.db", call_db), \
             patch("app.services.calls.send_sms", new_callable=AsyncMock) as mock_sms, \
             patch("app.services.calls.schedule_retry", new_callable=AsyncMock) as mock_retry:

            await _insert_call_log(call_db)
            await handle_call_failure(mock_record, {"reason": "hung_up", "success": False})

            mock_sms.assert_called_once()
            assert "call them directly" in mock_sms.call_args[0][1].lower()
            mock_retry.assert_not_called()


# --- schedule_retry tests ---


class TestScheduleRetry:
    @pytest.mark.asyncio
    async def test_schedules_retry_under_max(self, call_db):
        record = {
            "user_id": "+15551234567",
            "business_name": "Test Biz",
            "vapi_call_id": "call_123",
            "retry_count": 0,
            "business_phone": "+15559876543",
        }
        with patch("app.services.calls.db", call_db):
            await _insert_call_log(call_db)

            await schedule_retry(record, delay_minutes=10)

            row = await call_db.fetch_one(
                "SELECT * FROM call_log WHERE vapi_call_id = ?", ["call_123"],
            )
            assert row["status"] == "retry_pending"
            assert row["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_gives_up_at_max_retries(self, call_db):
        record = {
            "user_id": "+15551234567",
            "business_name": "Test Biz",
            "vapi_call_id": "call_456",
            "retry_count": 2,
            "business_phone": "+15559876543",
        }
        with patch("app.services.calls.db", call_db), \
             patch("app.services.calls.send_sms", new_callable=AsyncMock) as mock_sms:
            await schedule_retry(record, delay_minutes=10)

            mock_sms.assert_called_once()
            assert "giving up" in mock_sms.call_args[0][1].lower()


# --- process_retries tests ---


class TestProcessRetries:
    @pytest.mark.asyncio
    async def test_picks_up_due_retries(self, call_db):
        """process_retries should re-initiate calls that are past retry_after."""
        with patch("app.services.calls.db", call_db):
            await _insert_test_user(call_db)
            # Insert a call_log record with retry_pending status and past retry_after
            past = (datetime.now() - timedelta(minutes=1)).isoformat()
            await call_db.execute(
                """INSERT INTO call_log
                   (user_id, vapi_call_id, business_name, business_phone,
                    place_id, task, task_type, status, retry_count, retry_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'retry_pending', 1, ?)""",
                ["+15551234567", "call_retry_1", "Test Biz", "+15559876543",
                 "place_abc", "What are your hours?", "info_query", past],
            )

            with patch(
                "app.services.calls.initiate_outbound_call",
                new_callable=AsyncMock,
                return_value={"call_log_id": 99, "vapi_call_id": "new_call", "status": "in_progress"},
            ) as mock_initiate:
                count = await process_retries()

            assert count == 1
            mock_initiate.assert_called_once_with(
                business_name="Test Biz",
                business_phone="+15559876543",
                task="What are your hours?",
                user_id="+15551234567",
                task_type="info_query",
                place_id="place_abc",
            )

    @pytest.mark.asyncio
    async def test_ignores_future_retries(self, call_db):
        """process_retries should not pick up retries whose retry_after is in the future."""
        with patch("app.services.calls.db", call_db):
            await _insert_test_user(call_db)
            future = (datetime.now() + timedelta(minutes=10)).isoformat()
            await call_db.execute(
                """INSERT INTO call_log
                   (user_id, vapi_call_id, business_name, business_phone,
                    place_id, task, task_type, status, retry_count, retry_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'retry_pending', 1, ?)""",
                ["+15551234567", "call_future", "Test Biz", "+15559876543",
                 "place_abc", "Check hours", "info_query", future],
            )

            with patch(
                "app.services.calls.initiate_outbound_call",
                new_callable=AsyncMock,
            ) as mock_initiate:
                count = await process_retries()

            assert count == 0
            mock_initiate.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_call_failure_gracefully(self, call_db):
        """process_retries should continue processing if one retry fails."""
        with patch("app.services.calls.db", call_db):
            await _insert_test_user(call_db)
            past = (datetime.now() - timedelta(minutes=1)).isoformat()
            # Insert two retry_pending records
            for i, cid in enumerate(["call_fail", "call_ok"]):
                await call_db.execute(
                    """INSERT INTO call_log
                       (user_id, vapi_call_id, business_name, business_phone,
                        place_id, task, task_type, status, retry_count, retry_after)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'retry_pending', 1, ?)""",
                    ["+15551234567", cid, f"Biz {i}", "+15559876543",
                     "place_abc", "task", "info_query", past],
                )

            call_count = 0

            async def side_effect(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("Vapi API error")
                return {"call_log_id": 99, "vapi_call_id": "new", "status": "in_progress"}

            with patch(
                "app.services.calls.initiate_outbound_call",
                new_callable=AsyncMock,
                side_effect=side_effect,
            ):
                count = await process_retries()

            # Only the second one succeeded
            assert count == 1

    @pytest.mark.asyncio
    async def test_no_pending_retries(self, call_db):
        """process_retries returns 0 when nothing is pending."""
        with patch("app.services.calls.db", call_db):
            count = await process_retries()
        assert count == 0
