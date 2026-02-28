"""Tests for the business fact cache service."""

import pytest
import pytest_asyncio

from app.db import database as db
from app.services.cache import (
    check_cache,
    get_ivr_map,
    get_phone_score,
    store_fact,
    store_ivr_map,
    update_phone_score,
)


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Initialize an in-memory database for each test."""
    db_path = str(tmp_path / "test.db")
    await db.init(db_path)
    yield
    await db.close()


@pytest.mark.asyncio
async def test_store_and_check_cache(setup_db):
    await store_fact(
        place_id="place_1",
        business_name="Joe's Pizza",
        fact_type="hours",
        question="What are your hours?",
        answer="Mon-Fri 9am-10pm",
        source="google_places",
    )
    result = await check_cache("Joe's Pizza", "hours")
    assert result is not None
    assert "Mon-Fri 9am-10pm" in result
    assert "google_places" in result


@pytest.mark.asyncio
async def test_cache_miss(setup_db):
    result = await check_cache("Nonexistent Place", "hours")
    assert result is None


@pytest.mark.asyncio
async def test_upsert_overwrites(setup_db):
    await store_fact("p1", "Biz", "hours", "hours?", "9-5", "web_search")
    await store_fact("p1", "Biz", "hours", "hours?", "10-6", "phone_call")
    result = await check_cache("Biz", "hours")
    assert result is not None
    assert "10-6" in result
    assert "phone_call" in result


@pytest.mark.asyncio
async def test_phone_score_tracking(setup_db):
    await update_phone_score("p1", "+15551234567", {"success": True, "reason": "success"})
    score = await get_phone_score("p1", "+15551234567")
    assert score is not None
    assert score["call_count"] == 1
    assert score["success_count"] == 1
    assert score["last_outcome"] == "success"

    await update_phone_score("p1", "+15551234567", {"success": False, "reason": "voicemail"})
    score = await get_phone_score("p1", "+15551234567")
    assert score["call_count"] == 2
    assert score["success_count"] == 1
    assert score["last_outcome"] == "voicemail"


@pytest.mark.asyncio
async def test_phone_score_miss(setup_db):
    score = await get_phone_score("nonexistent", "+10000000000")
    assert score is None


@pytest.mark.asyncio
async def test_ivr_map_store_and_get(setup_db):
    menu = {"1": "hours", "2": "reservations", "0": "operator"}
    await store_ivr_map("p1", "+15551234567", menu)
    result = await get_ivr_map("p1", "+15551234567")
    assert result is not None
    assert result["menu_structure"] == menu
    assert result["place_id"] == "p1"

    updated_menu = {"1": "hours", "2": "reservations", "3": "catering", "0": "operator"}
    await store_ivr_map("p1", "+15551234567", updated_menu)
    result = await get_ivr_map("p1", "+15551234567")
    assert result["menu_structure"] == updated_menu
