"""Business fact cache service.

Resolution ladder: Cache -> Google Places -> Web Search -> Pre-Call -> Voice Call.
This module handles the cache layer — the cheapest step.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.db.database import db

# Expiry defaults keyed by (source, fact_type)
EXPIRY_DEFAULTS: dict[tuple[str, str], timedelta] = {
    ("google_places", "hours"): timedelta(days=7),
    ("google_places", "attributes"): timedelta(days=30),
    ("web_search", "menu"): timedelta(days=14),
    ("web_search", "pricing"): timedelta(days=14),
    ("phone_call", "hours"): timedelta(days=7),
    ("phone_call", "reservation_policy"): timedelta(days=30),
    ("phone_call", "general"): timedelta(days=30),
}

CONFIDENCE_BY_SOURCE: dict[str, float] = {
    "phone_call": 1.0,
    "google_places": 0.8,
    "web_search": 0.6,
}

DEFAULT_EXPIRY = timedelta(days=14)
DEFAULT_CONFIDENCE = 0.5


async def check_cache(business_name: str, fact_type: str) -> str | None:
    """Check for an unexpired cached fact. Returns answer string with metadata, or None."""
    row = await db.fetch_one(
        """
        SELECT answer, source, verified_at FROM business_facts
        WHERE business_name = ? AND fact_type = ?
        AND expires_at > ?
        ORDER BY confidence DESC, verified_at DESC
        LIMIT 1
        """,
        [business_name, fact_type, datetime.now().isoformat()],
    )
    if row:
        verified = datetime.fromisoformat(row["verified_at"])
        age = datetime.now() - verified
        return f"{row['answer']} (from {row['source']}, {age.days}d ago)"
    return None


async def store_fact(
    place_id: str,
    business_name: str,
    fact_type: str,
    question: str,
    answer: str,
    source: str,
) -> None:
    """Store or update a business fact. Uses UPSERT on (place_id, fact_type)."""
    expiry = EXPIRY_DEFAULTS.get((source, fact_type), DEFAULT_EXPIRY)
    now = datetime.now()
    expires_at = now + expiry
    confidence = CONFIDENCE_BY_SOURCE.get(source, DEFAULT_CONFIDENCE)

    # Ensure business profile exists and increment query count
    if place_id:
        try:
            from app.services.intelligence import ensure_business_profile, increment_business_queries
            await ensure_business_profile(place_id, business_name)
            await increment_business_queries(place_id)
        except Exception:
            pass  # non-critical

    await db.execute(
        """
        INSERT INTO business_facts
            (place_id, business_name, fact_type, question, answer,
             source, verified_at, expires_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(place_id, fact_type)
        DO UPDATE SET
            answer = excluded.answer,
            source = excluded.source,
            verified_at = excluded.verified_at,
            expires_at = excluded.expires_at,
            confidence = excluded.confidence
        """,
        [
            place_id, business_name, fact_type, question, answer,
            source, now.isoformat(), expires_at.isoformat(), confidence,
        ],
    )


async def update_phone_score(place_id: str, phone: str, outcome: dict) -> None:
    """Track phone number reliability. UPSERT on (place_id, phone).

    outcome should have keys: success (bool), reason (str).
    """
    success = 1 if outcome["success"] else 0
    now = datetime.now().isoformat()

    await db.execute(
        """
        INSERT INTO phone_scores
            (place_id, phone, call_count, success_count, last_outcome, last_attempt)
        VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(place_id, phone)
        DO UPDATE SET
            call_count = call_count + 1,
            success_count = success_count + excluded.success_count,
            last_outcome = excluded.last_outcome,
            last_attempt = excluded.last_attempt
        """,
        [place_id, phone, success, outcome["reason"], now],
    )


async def get_phone_score(place_id: str, phone: str) -> dict | None:
    """Fetch phone score record for pre-call check."""
    return await db.fetch_one(
        "SELECT * FROM phone_scores WHERE place_id = ? AND phone = ?",
        [place_id, phone],
    )


async def store_ivr_map(place_id: str, phone: str, menu_structure: dict) -> None:
    """Store or update an IVR navigation map for a phone number."""
    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO ivr_maps (place_id, phone, menu_structure, last_updated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(place_id, phone)
        DO UPDATE SET
            menu_structure = excluded.menu_structure,
            last_updated = excluded.last_updated
        """,
        [place_id, phone, json.dumps(menu_structure), now],
    )


async def get_ivr_map(place_id: str, phone: str) -> dict | None:
    """Fetch IVR map for a phone number. Returns dict with parsed menu_structure, or None."""
    row = await db.fetch_one(
        "SELECT * FROM ivr_maps WHERE place_id = ? AND phone = ?",
        [place_id, phone],
    )
    if row and row.get("menu_structure"):
        row["menu_structure"] = json.loads(row["menu_structure"])
    return row
