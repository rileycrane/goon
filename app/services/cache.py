"""Business fact cache — store and retrieve cached business answers."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.db.database import db

EXPIRY_DEFAULTS = {
    ("google_places", "hours"): timedelta(days=7),
    ("google_places", "attributes"): timedelta(days=30),
    ("web_search", "menu"): timedelta(days=14),
    ("web_search", "pricing"): timedelta(days=14),
    ("phone_call", "hours"): timedelta(days=7),
    ("phone_call", "reservation_policy"): timedelta(days=30),
    ("phone_call", "general"): timedelta(days=30),
}


async def check_cache(business_name: str, fact_type: str) -> str | None:
    """Check for unexpired cached fact."""
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
        return row["answer"]
    return None


async def store_fact(
    place_id: str,
    business_name: str,
    fact_type: str,
    question: str,
    answer: str,
    source: str,
) -> None:
    """Store or update a business fact."""
    expiry = EXPIRY_DEFAULTS.get((source, fact_type), timedelta(days=14))
    expires_at = datetime.now() + expiry
    confidence = {"phone_call": 1.0, "google_places": 0.8, "web_search": 0.6}.get(
        source, 0.5
    )
    now = datetime.now().isoformat()

    await db.execute(
        """
        INSERT INTO business_facts
            (place_id, business_name, fact_type, question, answer,
             source, verified_at, expires_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(place_id, fact_type)
        DO UPDATE SET
            answer=excluded.answer, source=excluded.source,
            verified_at=excluded.verified_at, expires_at=excluded.expires_at,
            confidence=excluded.confidence
        """,
        [
            place_id, business_name, fact_type, question, answer,
            source, now, expires_at.isoformat(), confidence,
        ],
    )
