"""Tests for outbound call service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.calls import (
    build_call_prompt,
    build_first_message,
    pre_call_check,
)


class TestBuildCallPrompt:
    """Test voice agent prompt generation."""

    def test_basic_prompt_includes_business(self):
        prompt = build_call_prompt(
            business_name="Joe's Pizza",
            task="What are your hours today?",
            task_type="info",
            user_name="Alice",
            details={},
        )
        assert "Joe's Pizza" in prompt
        assert "What are your hours today?" in prompt
        assert "Alice" in prompt
        assert "on behalf of" in prompt  # The rule about NOT saying it

    def test_prompt_no_ai_disclosure(self):
        prompt = build_call_prompt(
            business_name="Test Biz",
            task="Do you take reservations?",
            task_type="info",
            user_name="Bob",
            details={},
        )
        assert "Do NOT say" in prompt
        assert "I'm an AI" in prompt

    def test_reservation_prompt(self):
        prompt = build_call_prompt(
            business_name="Fancy Restaurant",
            task="Make a reservation",
            task_type="reservation",
            user_name="Carol",
            details={"party_size": "4", "date": "Friday", "time": "7pm"},
        )
        assert "Reservation-Specific" in prompt
        assert "4" in prompt
        assert "Friday" in prompt
        assert "7pm" in prompt

    def test_appointment_prompt(self):
        prompt = build_call_prompt(
            business_name="Dr. Smith",
            task="Schedule a dental cleaning",
            task_type="appointment",
            user_name="Dave",
            details={"service": "cleaning", "date": "next week"},
        )
        assert "Appointment-Specific" in prompt
        assert "cleaning" in prompt


class TestBuildFirstMessage:
    """Test voice agent opening lines."""

    def test_reservation_opening(self):
        msg = build_first_message(
            "Make a reservation",
            "reservation",
            {"party_size": "4", "date": "Friday", "time": "7pm"},
        )
        assert "reservation" in msg
        assert "4" in msg
        assert "Friday" in msg

    def test_appointment_opening(self):
        msg = build_first_message(
            "Schedule a dental cleaning",
            "appointment",
            {},
        )
        assert "appointment" in msg
        assert "dental cleaning" in msg

    def test_availability_check_opening(self):
        msg = build_first_message(
            "are you open on Sundays",
            "availability_check",
            {},
        )
        assert "quick question" in msg
        assert "open on Sundays" in msg

    def test_generic_opening(self):
        msg = build_first_message(
            "do you have gluten free options",
            "info",
            {},
        )
        assert msg.startswith("Hi,")
        assert "gluten free" in msg


class TestPreCallCheck:
    """Test pre-call validation logic."""

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_no_phone_number(self, mock_score):
        result = await pre_call_check("Test Biz", "", place_id=None)
        assert result["ok"] is False
        assert "No phone number" in result["reason"]

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_good_phone(self, mock_score):
        mock_score.return_value = {
            "call_count": 3,
            "success_count": 2,
            "last_outcome": "success",
        }
        result = await pre_call_check("Test Biz", "+14155551234", place_id="place_1")
        assert result["ok"] is True

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_repeated_failures(self, mock_score):
        mock_score.return_value = {
            "call_count": 3,
            "success_count": 0,
            "last_outcome": "no-answer",
        }
        result = await pre_call_check("Test Biz", "+14155551234", place_id="place_1")
        assert result["ok"] is False
        assert "failed 3 times" in result["reason"]

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_wrong_number_blocked(self, mock_score):
        mock_score.return_value = {
            "call_count": 1,
            "success_count": 0,
            "last_outcome": "wrong_number",
        }
        result = await pre_call_check("Test Biz", "+14155551234", place_id="place_1")
        assert result["ok"] is False
        assert "wrong_number" in result["reason"]

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_voicemail_warning(self, mock_score):
        mock_score.return_value = {
            "call_count": 1,
            "success_count": 0,
            "last_outcome": "voicemail",
        }
        result = await pre_call_check("Test Biz", "+14155551234", place_id="place_1")
        assert result["ok"] is True
        assert "voicemail" in result["warnings"][0]

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_no_place_id_skips_score(self, mock_score):
        result = await pre_call_check("Test Biz", "+14155551234", place_id=None)
        assert result["ok"] is True
        mock_score.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.calls.get_phone_score", new_callable=AsyncMock)
    async def test_no_prior_score(self, mock_score):
        mock_score.return_value = None
        result = await pre_call_check("Test Biz", "+14155551234", place_id="place_1")
        assert result["ok"] is True
