"""Tests for the test business registry and matching logic."""

from __future__ import annotations

from unittest.mock import patch

from app.config.test_businesses import TEST_BUSINESSES
from app.services.test_businesses import (
    format_as_places_result,
    get_cached_fact,
    is_test_business,
    match_test_business,
    skip_pre_call_checks,
)


class TestMatchTestBusiness:
    """Tests for fuzzy matching against the test business registry."""

    @patch("app.services.test_businesses.settings")
    def test_exact_match(self, mock_settings):
        mock_settings.enable_test_businesses = True
        mock_settings.test_mode_log_verbose = False
        result = match_test_business("riley's pizza")
        assert result is not None
        assert result["name"] == "Riley's Pizza"

    @patch("app.services.test_businesses.settings")
    def test_case_insensitive(self, mock_settings):
        mock_settings.enable_test_businesses = True
        mock_settings.test_mode_log_verbose = False
        result = match_test_business("Riley's Pizza")
        assert result is not None
        assert result["name"] == "Riley's Pizza"

    @patch("app.services.test_businesses.settings")
    def test_query_contains_name(self, mock_settings):
        mock_settings.enable_test_businesses = True
        mock_settings.test_mode_log_verbose = False
        result = match_test_business("What time does Riley's Pizza close?")
        assert result is not None
        assert result["name"] == "Riley's Pizza"

    @patch("app.services.test_businesses.settings")
    def test_barbershop_match(self, mock_settings):
        mock_settings.enable_test_businesses = True
        mock_settings.test_mode_log_verbose = False
        result = match_test_business("test barbershop hours")
        assert result is not None
        assert result["name"] == "Test Barbershop"

    @patch("app.services.test_businesses.settings")
    def test_no_match(self, mock_settings):
        mock_settings.enable_test_businesses = True
        mock_settings.test_mode_log_verbose = False
        result = match_test_business("Whole Foods Middlefield")
        assert result is None

    @patch("app.services.test_businesses.settings")
    def test_disabled_returns_none(self, mock_settings):
        mock_settings.enable_test_businesses = False
        result = match_test_business("riley's pizza")
        assert result is None


class TestGetCachedFact:
    """Tests for looking up cached facts from a test business."""

    def test_hours_cached(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        assert get_cached_fact(biz, "hours") == "11am-10pm, 7 days a week"

    def test_menu_cached(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        fact = get_cached_fact(biz, "menu")
        assert "Margherita" in fact
        assert "$14" in fact

    def test_missing_fact(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        assert get_cached_fact(biz, "specials") is None


class TestFormatAsPlacesResult:
    """Tests for formatting test businesses as Google Places results."""

    def test_has_required_fields(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        result = format_as_places_result(biz)
        assert result["place_id"] == "test_rileys_pizza"
        assert result["name"] == "Riley's Pizza"
        assert result["formatted_address"] == "123 Test St, Palo Alto, CA"
        assert result["formatted_phone_number"] == biz["phone"]
        assert result["business_status"] == "OPERATIONAL"

    def test_opening_hours(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        result = format_as_places_result(biz)
        assert result["opening_hours"]["open_now"] is True

    def test_test_business_flag(self):
        biz = TEST_BUSINESSES["riley's pizza"]
        result = format_as_places_result(biz)
        assert result["_test_business"] is True


class TestIsTestBusiness:
    """Tests for identifying test businesses by place_id."""

    def test_test_prefix(self):
        assert is_test_business("test_rileys_pizza") is True
        assert is_test_business("test_barbershop") is True

    def test_real_business(self):
        assert is_test_business("ChIJN1t_tDeuEmsRUsoyG83frY4") is False

    def test_none(self):
        assert is_test_business(None) is False


class TestSkipPreCallChecks:
    """Tests for skipping pre-call checks on test businesses."""

    @patch("app.services.test_businesses.settings")
    def test_skip_when_enabled(self, mock_settings):
        mock_settings.enable_test_businesses = True
        assert skip_pre_call_checks("test_rileys_pizza") is True

    @patch("app.services.test_businesses.settings")
    def test_no_skip_when_disabled(self, mock_settings):
        mock_settings.enable_test_businesses = False
        assert skip_pre_call_checks("test_rileys_pizza") is False

    @patch("app.services.test_businesses.settings")
    def test_no_skip_real_business(self, mock_settings):
        mock_settings.enable_test_businesses = True
        assert skip_pre_call_checks("ChIJN1t_tDeuEmsRUsoyG83frY4") is False
