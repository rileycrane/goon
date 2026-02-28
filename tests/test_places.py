"""Tests for Google Places API v2 wrapper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.places import (
    PlaceResult,
    _parse_place,
    format_place_for_llm,
    get_place_details,
    is_chain_business,
    search_places,
)

# --- Fixtures: realistic API responses ---

SAMPLE_PLACE_RAW = {
    "id": "ChIJYwx1RuK6j4ARnl0t3PYkx1A",
    "displayName": {"text": "Pizzeria Delfina", "languageCode": "en"},
    "formattedAddress": "3611 18th St, San Francisco, CA 94110, USA",
    "internationalPhoneNumber": "+1 415-437-6800",
    "nationalPhoneNumber": "(415) 437-6800",
    "websiteUri": "https://www.pizzeriadelfina.com/",
    "rating": 4.5,
    "userRatingCount": 1823,
    "businessStatus": "OPERATIONAL",
    "types": ["italian_restaurant", "restaurant", "food", "establishment"],
    "primaryType": "italian_restaurant",
    "priceLevel": "PRICE_LEVEL_MODERATE",
    "location": {"latitude": 37.7617, "longitude": -122.4244},
    "regularOpeningHours": {
        "openNow": True,
        "weekdayDescriptions": [
            "Monday: 11:30 AM - 10:00 PM",
            "Tuesday: 11:30 AM - 10:00 PM",
            "Wednesday: 11:30 AM - 10:00 PM",
            "Thursday: 11:30 AM - 10:00 PM",
            "Friday: 11:30 AM - 11:00 PM",
            "Saturday: 11:30 AM - 11:00 PM",
            "Sunday: 11:30 AM - 10:00 PM",
        ],
        "periods": [],
    },
    "currentOpeningHours": {
        "openNow": True,
        "weekdayDescriptions": [
            "Monday: 11:30 AM - 10:00 PM",
            "Tuesday: 11:30 AM - 10:00 PM",
            "Wednesday: 11:30 AM - 10:00 PM",
            "Thursday: 11:30 AM - 10:00 PM",
            "Friday: 11:30 AM - 11:00 PM",
            "Saturday: 11:30 AM - 11:00 PM",
            "Sunday: 11:30 AM - 10:00 PM",
        ],
        "periods": [],
    },
}

SAMPLE_CHAIN_RAW = {
    "id": "ChIJabc123",
    "displayName": {"text": "McDonald's", "languageCode": "en"},
    "formattedAddress": "123 Main St, Palo Alto, CA",
    "rating": 3.8,
    "userRatingCount": 12000,
    "businessStatus": "OPERATIONAL",
    "types": ["fast_food_restaurant", "restaurant", "food", "establishment"],
    "primaryType": "fast_food_restaurant",
    "location": {"latitude": 37.44, "longitude": -122.16},
}

MINIMAL_PLACE_RAW = {
    "id": "ChIJminimal",
    "displayName": {"text": "Unknown Spot"},
    "formattedAddress": "456 Oak Ave",
}


class TestParsePlace:
    def test_full_place(self):
        result = _parse_place(SAMPLE_PLACE_RAW)
        assert result.place_id == "ChIJYwx1RuK6j4ARnl0t3PYkx1A"
        assert result.name == "Pizzeria Delfina"
        assert result.address == "3611 18th St, San Francisco, CA 94110, USA"
        assert result.phone == "+1 415-437-6800"
        assert result.phone_national == "(415) 437-6800"
        assert result.website == "https://www.pizzeriadelfina.com/"
        assert result.rating == 4.5
        assert result.rating_count == 1823
        assert result.price_level == "PRICE_LEVEL_MODERATE"
        assert result.business_status == "OPERATIONAL"
        assert "italian_restaurant" in result.types
        assert result.primary_type == "italian_restaurant"
        assert result.open_now is True
        assert len(result.hours) == 7
        assert result.lat == 37.7617
        assert result.lng == -122.4244

    def test_minimal_place(self):
        result = _parse_place(MINIMAL_PLACE_RAW)
        assert result.place_id == "ChIJminimal"
        assert result.name == "Unknown Spot"
        assert result.phone is None
        assert result.rating is None
        assert result.open_now is None
        assert result.hours == []
        assert result.types == []

    def test_current_hours_preferred_over_regular(self):
        raw = {
            **MINIMAL_PLACE_RAW,
            "regularOpeningHours": {"openNow": False},
            "currentOpeningHours": {"openNow": True},
        }
        result = _parse_place(raw)
        # open_now should come from currentOpeningHours
        assert result.open_now is True

    def test_falls_back_to_regular_hours(self):
        raw = {
            **MINIMAL_PLACE_RAW,
            "regularOpeningHours": {
                "openNow": False,
                "weekdayDescriptions": ["Monday: 9 AM - 5 PM"],
            },
        }
        result = _parse_place(raw)
        assert result.open_now is False
        assert result.hours == ["Monday: 9 AM - 5 PM"]


class TestFormatPlaceForLLM:
    def test_full_format(self):
        place = _parse_place(SAMPLE_PLACE_RAW)
        text = format_place_for_llm(place)
        assert "Pizzeria Delfina" in text
        assert "3611 18th St" in text
        assert "+1 415-437-6800" in text
        assert "pizzeriadelfina.com" in text
        assert "4.5/5" in text
        assert "1823 reviews" in text
        assert "$$" in text
        assert "Open now" in text
        assert "Monday:" in text

    def test_closed_place(self):
        place = PlaceResult(
            place_id="x", name="Closed Shop", address="1 St",
            open_now=False,
        )
        text = format_place_for_llm(place)
        assert "Closed now" in text

    def test_non_operational(self):
        place = PlaceResult(
            place_id="x", name="Gone", address="1 St",
            business_status="CLOSED_PERMANENTLY",
        )
        text = format_place_for_llm(place)
        assert "CLOSED_PERMANENTLY" in text

    def test_operational_status_hidden(self):
        place = PlaceResult(
            place_id="x", name="Open", address="1 St",
            business_status="OPERATIONAL",
        )
        text = format_place_for_llm(place)
        assert "OPERATIONAL" not in text

    def test_price_levels(self):
        for level, symbol in [
            ("PRICE_LEVEL_INEXPENSIVE", "$"),
            ("PRICE_LEVEL_EXPENSIVE", "$$$"),
        ]:
            place = PlaceResult(place_id="x", name="P", address="A", price_level=level)
            assert symbol in format_place_for_llm(place)


class TestIsChainBusiness:
    def test_high_review_count(self):
        place = _parse_place(SAMPLE_CHAIN_RAW)
        assert is_chain_business(place) is True

    def test_fast_food_type(self):
        place = PlaceResult(
            place_id="x", name="Wendy's", address="1 St",
            types=["fast_food_restaurant"], rating_count=100,
        )
        assert is_chain_business(place) is True

    def test_local_restaurant(self):
        place = _parse_place(SAMPLE_PLACE_RAW)
        assert is_chain_business(place) is False

    def test_supermarket_chain(self):
        place = PlaceResult(
            place_id="x", name="Safeway", address="1 St",
            types=["supermarket", "grocery_store"], rating_count=200,
        )
        assert is_chain_business(place) is True


class TestSearchPlaces:
    @pytest.mark.asyncio
    async def test_search_returns_parsed_results(self):
        mock_response = httpx.Response(
            200,
            json={"places": [SAMPLE_PLACE_RAW, MINIMAL_PLACE_RAW]},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                results = await search_places("Pizzeria Delfina", location="San Francisco")

        assert len(results) == 2
        assert results[0].name == "Pizzeria Delfina"
        assert results[1].name == "Unknown Spot"

    @pytest.mark.asyncio
    async def test_search_with_location_bias(self):
        mock_response = httpx.Response(
            200,
            json={"places": [SAMPLE_PLACE_RAW]},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
                await search_places("pizza", lat=37.44, lng=-122.16, radius_m=5000)

        # Verify locationBias was included in the request body
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "locationBias" in body
        assert body["locationBias"]["circle"]["center"]["latitude"] == 37.44

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        mock_response = httpx.Response(
            200,
            json={},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                results = await search_places("nonexistent place xyz")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_no_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="GOOGLE_PLACES_API_KEY"):
                await search_places("test")

    @pytest.mark.asyncio
    async def test_search_location_appended_to_query(self):
        mock_response = httpx.Response(
            200,
            json={"places": []},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
                await search_places("pizza", location="Palo Alto")

        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["textQuery"] == "pizza Palo Alto"

    @pytest.mark.asyncio
    async def test_search_location_not_duplicated(self):
        mock_response = httpx.Response(
            200,
            json={"places": []},
            request=httpx.Request("POST", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
                await search_places("pizza in Palo Alto", location="Palo Alto")

        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        # Should not duplicate "Palo Alto"
        assert body["textQuery"] == "pizza in Palo Alto"


class TestGetPlaceDetails:
    @pytest.mark.asyncio
    async def test_details_returns_parsed_result(self):
        mock_response = httpx.Response(
            200,
            json=SAMPLE_PLACE_RAW,
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
                result = await get_place_details("ChIJYwx1RuK6j4ARnl0t3PYkx1A")

        assert result is not None
        assert result.name == "Pizzeria Delfina"
        assert result.phone == "+1 415-437-6800"

    @pytest.mark.asyncio
    async def test_details_not_found(self):
        mock_response = httpx.Response(
            404,
            json={"error": {"message": "not found"}},
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
                result = await get_place_details("bad-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_details_api_error_raises(self):
        mock_response = httpx.Response(
            500,
            json={"error": {"message": "internal"}},
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
                with pytest.raises(httpx.HTTPStatusError):
                    await get_place_details("ChIJtest")
