"""Test business matching and formatting for the resolution ladder.

When test mode is enabled, these functions insert at Step 0 of the
resolution ladder -- before the fact cache or Google Places.

Usage in the orchestrator's search_places tool handler:
    if settings.enable_test_businesses:
        test_biz = match_test_business(query)
        if test_biz:
            return format_as_places_result(test_biz)

Usage in the pre_call_check:
    if settings.enable_test_businesses and place_id.startswith("test_"):
        return {"ok": True, "issues": []}
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.settings import settings
from app.config.test_businesses import TEST_BUSINESSES

logger = logging.getLogger(__name__)


def match_test_business(query: str) -> dict[str, Any] | None:
    """Fuzzy-match a query against the test business registry.

    Returns the test business dict if matched, None otherwise.
    Matching is case-insensitive and checks if the query contains
    the business name or vice versa.
    """
    if not settings.enable_test_businesses:
        return None

    query_lower = query.lower().strip()

    for key, biz in TEST_BUSINESSES.items():
        # Check if query contains the registry key or the business name
        name_lower = biz["name"].lower()
        if key in query_lower or name_lower in query_lower or query_lower in name_lower:
            if settings.test_mode_log_verbose:
                logger.info(
                    "Test business matched: query=%r -> %s", query, biz["name"]
                )
            return biz

    return None


def get_cached_fact(business: dict[str, Any], fact_type: str) -> str | None:
    """Check a test business's cached_facts for a pre-loaded answer.

    Returns the cached answer string if available, None otherwise.
    """
    return business.get("cached_facts", {}).get(fact_type)


def format_as_places_result(business: dict[str, Any]) -> dict[str, Any]:
    """Format a test business to look like a Google Places API result.

    This lets downstream code handle test businesses and real businesses
    identically.
    """
    return {
        "place_id": business["place_id"],
        "name": business["name"],
        "formatted_address": business["address"],
        "formatted_phone_number": business["phone"],
        "types": [business.get("category", "establishment")],
        "opening_hours": {
            "open_now": business.get("open_now", True),
            "weekday_text": [business.get("hours", "Hours not available")],
        },
        "business_status": "OPERATIONAL",
        "attributes": business.get("attributes", {}),
        "_test_business": True,
    }


def is_test_business(place_id: str | None) -> bool:
    """Check if a place_id belongs to a test business."""
    if not place_id:
        return False
    return place_id.startswith("test_")


def skip_pre_call_checks(place_id: str | None) -> bool:
    """Whether to skip pre-call checks for this business.

    Test businesses always pass pre-call checks (skip open_now and
    phone score validation).
    """
    return settings.enable_test_businesses and is_test_business(place_id)
