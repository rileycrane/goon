"""Google Places API v2 — business search, details, hours."""
from __future__ import annotations


async def search_places(query: str, location: str | None = None) -> list[dict]:
    """Search for businesses via Google Places API."""
    # TODO: implement Places API v2 text search
    raise NotImplementedError


async def get_place_details(place_id: str) -> dict | None:
    """Get full details for a place by ID."""
    # TODO: implement Places API v2 place details
    raise NotImplementedError
