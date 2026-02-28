"""Tests for voice inbound webhook (Twilio -> Vapi routing)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from app.routes.voice import router, voice_webhook


@pytest.fixture
def voice_client():
    """Create a TestClient using only the voice router, avoiding full app import."""
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router, prefix="/voice")
    return TestClient(test_app)


@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_unauthorized_caller(mock_active, mock_get_user, voice_client):
    """Unregistered caller gets a rejection message."""
    mock_get_user.return_value = None

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA123"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "not registered" in resp.text
    assert "<Hangup/>" in resp.text


@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_inactive_subscriber(mock_active, mock_get_user, voice_client):
    """Registered but inactive user gets rejection."""
    mock_get_user.return_value = {"id": "+14155551234", "name": "Test"}
    mock_active.return_value = False

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA123"},
    )
    assert resp.status_code == 200
    assert "not registered" in resp.text
    assert "<Hangup/>" in resp.text


@patch("app.routes.voice.settings")
@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_no_assistant_id(mock_active, mock_get_user, mock_settings, voice_client):
    """If VAPI_ASSISTANT_ID not configured, return error TwiML."""
    mock_get_user.return_value = {"id": "+14155551234", "name": "Test"}
    mock_active.return_value = True
    mock_settings.vapi_assistant_id = ""
    mock_settings.base_url = "http://localhost:8000"
    mock_settings.vapi_server_url = ""

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA123"},
    )
    assert resp.status_code == 200
    assert "technical difficulties" in resp.text


@patch("app.routes.voice.settings")
@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_forwards_to_vapi(mock_active, mock_get_user, mock_settings, voice_client):
    """Authorized caller gets TwiML forwarding to Vapi SIP."""
    mock_get_user.return_value = {"id": "+14155551234", "name": "Alice"}
    mock_active.return_value = True
    mock_settings.vapi_assistant_id = "asst_123"
    mock_settings.base_url = "http://localhost:8000"
    mock_settings.vapi_server_url = ""

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA456"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "<Dial>" in body
    assert "<Sip>" in body
    assert "sip:asst_123@sip.vapi.ai" in body
    assert "X-Caller-Phone=+14155551234" in body


@patch("app.routes.voice.get_user", new_callable=AsyncMock)
def test_voice_webhook_empty_caller(mock_get_user, voice_client):
    """Call with no From field gets rejected."""
    mock_get_user.return_value = None

    resp = voice_client.post(
        "/voice/webhook",
        data={"CallSid": "CA789"},
    )
    assert resp.status_code == 200
    assert "not registered" in resp.text
