"""Business intelligence extraction — builds world model from call transcripts."""
from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from app.config.settings import settings
from app.db.database import db
from app.services.cache import store_ivr_map

logger = logging.getLogger(__name__)


async def extract_call_intelligence(
    transcript: str,
    business_name: str,
    place_id: str | None,
) -> dict:
    """Extract structured intelligence from a call transcript.

    Runs as a background task after successful calls.
    Updates business_profiles and ivr_maps tables.

    Returns extracted data dict.
    """
    if not transcript or not place_id:
        return {}

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": f"""Extract structured intelligence from this phone call transcript.
Return ONLY valid JSON with these fields (omit any that aren't applicable):

{{
  "contacts": [{{"name": "string", "role": "string"}}],
  "hold_time_seconds": number or null,
  "ivr_detected": boolean,
  "ivr_structure": {{"key": "label"}} or null,
  "busy_indicator": "quiet" | "moderate" | "busy" | null,
  "notes": "brief insight about this business"
}}

Transcript:
{transcript[:3000]}""",
                }
            ],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)
    except (json.JSONDecodeError, Exception):
        logger.exception("Failed to extract intelligence for %s", business_name)
        return {}

    # Update business_profiles
    try:
        updates = []
        params = []

        if data.get("contacts"):
            updates.append("known_contacts = ?")
            params.append(json.dumps(data["contacts"]))

        if data.get("busy_indicator"):
            updates.append("busy_patterns = ?")
            params.append(json.dumps({"last_call": data["busy_indicator"]}))

        if data.get("notes"):
            updates.append("notes = ?")
            params.append(data["notes"])

        if data.get("hold_time_seconds") is not None:
            updates.append(
                "avg_hold_time_seconds = CASE "
                "WHEN avg_hold_time_seconds IS NULL THEN ? "
                "ELSE (avg_hold_time_seconds + ?) / 2 END"
            )
            params.extend([data["hold_time_seconds"], data["hold_time_seconds"]])

        updates.append("last_updated = ?")
        params.append(datetime.now().isoformat())
        params.append(place_id)

        if updates:
            await db.execute(
                f"UPDATE business_profiles SET {', '.join(updates)} WHERE place_id = ?",
                params,
            )
    except Exception:
        logger.exception("Failed to update business_profiles for %s", business_name)

    # Store IVR map if detected
    if data.get("ivr_detected") and data.get("ivr_structure") and place_id:
        try:
            # Need a phone number — fetch from business_profiles
            profile = await db.fetch_one(
                "SELECT phone FROM business_profiles WHERE place_id = ?",
                [place_id],
            )
            if profile and profile.get("phone"):
                await store_ivr_map(place_id, profile["phone"], data["ivr_structure"])
        except Exception:
            logger.exception("Failed to store IVR map for %s", business_name)

    return data


async def ensure_business_profile(
    place_id: str,
    business_name: str,
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
    phone: str | None = None,
) -> None:
    """Ensure a business_profiles row exists, creating if needed."""
    existing = await db.fetch_one(
        "SELECT place_id FROM business_profiles WHERE place_id = ?",
        [place_id],
    )
    if existing:
        # Update location data if we have it and it's missing
        updates = []
        params = []
        if lat is not None:
            updates.append("lat = COALESCE(lat, ?)")
            params.append(lat)
        if lng is not None:
            updates.append("lng = COALESCE(lng, ?)")
            params.append(lng)
        if address:
            updates.append("address = COALESCE(address, ?)")
            params.append(address)
        if phone:
            updates.append("phone = COALESCE(phone, ?)")
            params.append(phone)
        if updates:
            params.append(place_id)
            await db.execute(
                f"UPDATE business_profiles SET {', '.join(updates)} WHERE place_id = ?",
                params,
            )
    else:
        await db.execute(
            """INSERT INTO business_profiles
               (place_id, business_name, lat, lng, address, phone)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [place_id, business_name, lat, lng, address, phone],
        )


async def increment_business_calls(
    place_id: str, success: bool, duration_seconds: int | None = None
) -> None:
    """Increment call counters on a business profile."""
    success_inc = 1 if success else 0
    try:
        if duration_seconds is not None:
            await db.execute(
                """UPDATE business_profiles SET
                     total_calls = total_calls + 1,
                     successful_calls = successful_calls + ?,
                     avg_call_duration_seconds = CASE
                       WHEN avg_call_duration_seconds IS NULL THEN ?
                       ELSE (avg_call_duration_seconds + ?) / 2 END,
                     last_updated = ?
                   WHERE place_id = ?""",
                [success_inc, duration_seconds, duration_seconds,
                 datetime.now().isoformat(), place_id],
            )
        else:
            await db.execute(
                """UPDATE business_profiles SET
                     total_calls = total_calls + 1,
                     successful_calls = successful_calls + ?,
                     last_updated = ?
                   WHERE place_id = ?""",
                [success_inc, datetime.now().isoformat(), place_id],
            )
    except Exception:
        logger.exception("Failed to increment business call counters for %s", place_id)


async def increment_business_queries(place_id: str) -> None:
    """Increment the query counter on a business profile."""
    try:
        await db.execute(
            "UPDATE business_profiles SET total_queries = total_queries + 1, last_updated = ? WHERE place_id = ?",
            [datetime.now().isoformat(), place_id],
        )
    except Exception:
        logger.exception("Failed to increment business queries for %s", place_id)


def build_business_context(profile: dict) -> str:
    """Build a context string for the agent from a business profile."""
    parts = []
    if profile.get("known_contacts"):
        try:
            contacts = json.loads(profile["known_contacts"])
            names = [f"{c.get('name', '?')} ({c.get('role', '?')})" for c in contacts]
            parts.append(f"Known contacts: {', '.join(names)}")
        except (json.JSONDecodeError, TypeError):
            pass

    if profile.get("avg_hold_time_seconds"):
        parts.append(f"Avg hold time: ~{int(profile['avg_hold_time_seconds'])}s")

    if profile.get("busy_patterns"):
        try:
            bp = json.loads(profile["busy_patterns"])
            if bp.get("last_call"):
                parts.append(f"Last observed: {bp['last_call']}")
        except (json.JSONDecodeError, TypeError):
            pass

    if profile.get("notes"):
        parts.append(f"Notes: {profile['notes']}")

    return " | ".join(parts) if parts else ""
