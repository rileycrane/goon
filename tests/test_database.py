"""Tests for DB schema and database wrapper."""

import pytest

from app.db.database import Database


@pytest.fixture
async def db(tmp_path):
    """Create a fresh in-memory-like DB for each test."""
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_schema_creates_all_tables(db):
    """All 8 tables should exist after schema init."""
    rows = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = {r["name"] for r in rows}
    expected = {
        "users", "message_log", "call_log", "business_facts",
        "phone_scores", "ivr_maps", "scheduled_tasks", "unregistered_attempts",
        "waitlist", "app_settings", "phone_start_attempts", "business_profiles",
        "failure_log", "sessions", "requests", "request_messages",
        "request_categories",
    }
    assert expected == tables


async def test_insert_and_fetch_user(db):
    """Can insert and retrieve a user."""
    await db.execute(
        "INSERT INTO users (id, phone, name) VALUES (?, ?, ?)",
        ["+14155551234", "+14155551234", "Riley"],
    )
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", ["+14155551234"])
    assert user is not None
    assert user["name"] == "Riley"
    assert user["subscription_status"] == "free"


async def test_business_facts_upsert(db):
    """Business facts should upsert on (place_id, fact_type) conflict."""
    params = ["place_1", "Test Biz", "hours", "when open?", "9-5",
              "google_places", "2026-01-01", "2026-02-01", 0.8]
    await db.execute(
        """INSERT INTO business_facts
           (place_id, business_name, fact_type, question, answer,
            source, verified_at, expires_at, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        params,
    )
    # Upsert with new answer
    params2 = ["place_1", "Test Biz", "hours", "when open?", "10-6",
               "phone_call", "2026-01-15", "2026-03-01", 1.0]
    await db.execute(
        """INSERT INTO business_facts
           (place_id, business_name, fact_type, question, answer,
            source, verified_at, expires_at, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(place_id, fact_type)
           DO UPDATE SET answer=excluded.answer, source=excluded.source,
              verified_at=excluded.verified_at, expires_at=excluded.expires_at,
              confidence=excluded.confidence""",
        params2,
    )
    row = await db.fetch_one(
        "SELECT * FROM business_facts WHERE place_id = ? AND fact_type = ?",
        ["place_1", "hours"],
    )
    assert row["answer"] == "10-6"
    assert row["source"] == "phone_call"
    assert row["confidence"] == 1.0


async def test_phone_scores_tracking(db):
    """Phone scores track call outcomes."""
    await db.execute(
        """INSERT INTO phone_scores (place_id, phone, call_count, success_count,
           last_outcome, last_attempt)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ["place_1", "+14155559999", 1, 1, "success", "2026-01-01"],
    )
    score = await db.fetch_one(
        "SELECT * FROM phone_scores WHERE place_id = ? AND phone = ?",
        ["place_1", "+14155559999"],
    )
    assert score["call_count"] == 1
    assert score["success_count"] == 1


async def test_indexes_exist(db):
    """Key indexes should exist."""
    rows = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    index_names = {r["name"] for r in rows}
    expected = {
        "idx_message_log_user", "idx_message_log_created",
        "idx_call_log_user", "idx_call_log_status",
        "idx_business_facts_lookup", "idx_business_facts_expiry",
        "idx_phone_scores_lookup", "idx_scheduled_tasks_due",
        "idx_unregistered_phone", "idx_unregistered_created",
        "idx_phone_start_phone", "idx_business_profiles_name",
        "idx_failure_log_type", "idx_failure_log_severity",
        "idx_failure_log_created", "idx_failure_log_resolved",
        "idx_call_log_place_id", "idx_call_log_business",
        "idx_sessions_user", "idx_sessions_user_business",
        "idx_requests_session", "idx_requests_session_status",
        "idx_requests_uncharged", "idx_request_messages_message",
        "idx_waitlist_email",
    }
    assert expected == index_names
