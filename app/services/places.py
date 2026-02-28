"""Google Places API v2 wrapper for business search and details."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

API_BASE = "https://places.googleapis.com/v1"

# Field masks by endpoint. Text Search prefixes with "places."
_SEARCH_FIELDS = ",".join(
    f"places.{f}"
    for f in [
        "id",
        "displayName",
        "formattedAddress",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "websiteUri",
        "rating",
        "userRatingCount",
        "regularOpeningHours",
        "currentOpeningHours",
        "businessStatus",
        "types",
        "primaryType",
        "priceLevel",
        "location",
    ]
)

_DETAIL_FIELDS = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "rating",
        "userRatingCount",
        "regularOpeningHours",
        "currentOpeningHours",
        "businessStatus",
        "types",
        "primaryType",
        "priceLevel",
        "location",
    ]
)


@dataclass
class PlaceResult:
    """Structured result from a Google Places lookup."""

    place_id: str
    name: str
    address: str
    phone: str | None = None
    phone_national: str | None = None
    website: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    price_level: str | None = None
    business_status: str | None = None
    types: list[str] = field(default_factory=list)
    primary_type: str | None = None
    open_now: bool | None = None
    hours: list[str] = field(default_factory=list)
    lat: float | None = None
    lng: float | None = None
    google_maps_url: str | None = None


def _parse_place(raw: dict[str, Any]) -> PlaceResult:
    """Parse a raw Places API v2 response into a PlaceResult."""
    display_name = raw.get("displayName", {})
    location = raw.get("location", {})

    current_hours = raw.get("currentOpeningHours") or raw.get("regularOpeningHours") or {}
    regular_hours = raw.get("regularOpeningHours") or {}

    return PlaceResult(
        place_id=raw.get("id", ""),
        name=display_name.get("text", ""),
        address=raw.get("formattedAddress", ""),
        phone=raw.get("internationalPhoneNumber"),
        phone_national=raw.get("nationalPhoneNumber"),
        website=raw.get("websiteUri"),
        rating=raw.get("rating"),
        rating_count=raw.get("userRatingCount"),
        price_level=raw.get("priceLevel"),
        business_status=raw.get("businessStatus"),
        types=raw.get("types", []),
        primary_type=raw.get("primaryType"),
        open_now=current_hours.get("openNow"),
        hours=regular_hours.get("weekdayDescriptions", []),
        lat=location.get("latitude"),
        lng=location.get("longitude"),
        google_maps_url=raw.get("googleMapsUri"),
    )


def _get_api_key() -> str:
    key = settings.google_places_api_key
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set")
    return key


def _headers(api_key: str, field_mask: str) -> dict[str, str]:
    return {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }


async def search_places(
    query: str,
    location: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_m: float = 10000.0,
    max_results: int = 5,
) -> list[PlaceResult]:
    """Search for businesses by text query."""
    api_key = _get_api_key()

    text_query = f"{query} {location}" if location and location.lower() not in query.lower() else query

    body: dict[str, Any] = {
        "textQuery": text_query,
        "pageSize": min(max_results, 20),
        "languageCode": "en",
    }

    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m,
            }
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{API_BASE}/places:searchText",
            headers=_headers(api_key, _SEARCH_FIELDS),
            json=body,
        )
        resp.raise_for_status()

    data = resp.json()
    places = data.get("places", [])
    return [_parse_place(p) for p in places]


async def get_place_details(place_id: str) -> PlaceResult | None:
    """Get detailed info for a single place by its place_id."""
    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{API_BASE}/places/{place_id}",
            headers=_headers(api_key, _DETAIL_FIELDS),
            params={"languageCode": "en"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

    return _parse_place(resp.json())


def format_place_for_llm(place: PlaceResult) -> str:
    """Format a PlaceResult as a concise string for the LLM to consume."""
    parts = [place.name]
    if place.address:
        parts.append(place.address)
    if place.phone:
        parts.append(f"Phone: {place.phone}")
    if place.website:
        parts.append(f"Web: {place.website}")
    if place.rating is not None:
        stars = f"{place.rating}/5"
        if place.rating_count:
            stars += f" ({place.rating_count} reviews)"
        parts.append(stars)
    if place.price_level:
        level_map = {
            "PRICE_LEVEL_FREE": "Free",
            "PRICE_LEVEL_INEXPENSIVE": "$",
            "PRICE_LEVEL_MODERATE": "$$",
            "PRICE_LEVEL_EXPENSIVE": "$$$",
            "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
        }
        parts.append(level_map.get(place.price_level, place.price_level))
    if place.open_now is not None:
        parts.append("Open now" if place.open_now else "Closed now")
    if place.hours:
        parts.append("Hours: " + " | ".join(place.hours))
    if place.business_status and place.business_status != "OPERATIONAL":
        parts.append(f"Status: {place.business_status}")
    return "\n".join(parts)


def is_chain_business(place: PlaceResult) -> bool:
    """Heuristic: detect if a place is likely a chain/franchise."""
    if place.rating_count and place.rating_count > 5000:
        return True
    chain_types = {"fast_food_restaurant", "supermarket", "department_store", "drugstore"}
    if chain_types & set(place.types):
        return True
    return False
