"""Tests for Vapi event webhook handler."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.routes.vapi_events import classify_call_outcome


class TestClassifyCallOutcome:
    """Test call outcome classification logic."""

    def test_assistant_ended_with_transcript(self):
        result = classify_call_outcome(
            "assistant-ended-call",
            "Hi, what are your hours? We're open 9 to 5 Monday through Friday.",
        )
        assert result["success"] is True

    def test_assistant_ended_no_transcript(self):
        result = classify_call_outcome("assistant-ended-call", "Hi")
        assert result["success"] is False
        assert result["reason"] == "no_useful_info"
        assert result["retry"] is True

    def test_customer_ended_with_long_transcript(self):
        transcript = "x" * 150
        result = classify_call_outcome("customer-ended-call", transcript)
        assert result["success"] is True

    def test_customer_ended_short_transcript(self):
        result = classify_call_outcome("customer-ended-call", "Hello?")
        assert result["success"] is False
        assert result["reason"] == "hung_up"
        assert result["retry"] is True

    def test_no_answer(self):
        result = classify_call_outcome("no-answer", "")
        assert result["success"] is False
        assert result["reason"] == "no-answer"
        assert result["retry"] is True
        assert result["retry_delay_minutes"] == 10

    def test_busy(self):
        result = classify_call_outcome("busy", "")
        assert result["success"] is False
        assert result["reason"] == "busy"
        assert result["retry"] is True

    def test_voicemail(self):
        result = classify_call_outcome("voicemail", "")
        assert result["success"] is False
        assert result["reason"] == "voicemail"
        assert result["retry"] is True
        assert result["retry_delay_minutes"] == 30

    def test_max_duration(self):
        result = classify_call_outcome("max-duration-reached", "")
        assert result["success"] is False
        assert result["reason"] == "timeout"
        assert result["retry"] is False

    def test_unknown_reason(self):
        result = classify_call_outcome("some-new-reason", "")
        assert result["success"] is False
        assert result["reason"] == "some-new-reason"
