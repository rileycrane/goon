"""Tests for voice inbound webhook (Twilio -> Vapi routing)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA123"},
    )
    assert resp.status_code == 200
    assert "technical difficulties" in resp.text


@patch("app.routes.voice.httpx.AsyncClient")
@patch("app.routes.voice.settings")
@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_forwards_to_vapi(mock_active, mock_get_user, mock_settings, mock_client_cls, voice_client):
    """Authorized caller gets TwiML from Vapi provider bypass."""
    mock_get_user.return_value = {"id": "+14155551234", "name": "Alice"}
    mock_active.return_value = True
    mock_settings.vapi_assistant_id = "asst_123"
    mock_settings.vapi_api_key = "test-key"
    mock_settings.vapi_phone_number_id = "pn_123"

    # Mock the Vapi API response
    vapi_twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect><Stream url=\"wss://phone.vapi.ai/ws\"/></Connect></Response>"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "phoneCallProviderDetails": {"twiml": vapi_twiml}
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.post.return_value = mock_resp
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client_instance

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA456"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<Response>" in resp.text

    # Verify Vapi was called with correct params
    call_args = mock_client_instance.post.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["assistantId"] == "asst_123"
    assert payload["phoneCallProviderBypassEnabled"] is True
    assert payload["customer"]["number"] == "+14155551234"


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


@patch("app.routes.voice.httpx.AsyncClient")
@patch("app.routes.voice.settings")
@patch("app.routes.voice.get_user", new_callable=AsyncMock)
@patch("app.routes.voice.is_user_active")
def test_voice_webhook_vapi_failure_returns_fallback(mock_active, mock_get_user, mock_settings, mock_client_cls, voice_client):
    """If Vapi API call fails, return fallback TwiML."""
    mock_get_user.return_value = {"id": "+14155551234", "name": "Test"}
    mock_active.return_value = True
    mock_settings.vapi_assistant_id = "asst_123"
    mock_settings.vapi_api_key = "test-key"
    mock_settings.vapi_phone_number_id = "pn_123"

    mock_client_instance = AsyncMock()
    mock_client_instance.post.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock(status_code=500)
    )
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client_instance

    resp = voice_client.post(
        "/voice/webhook",
        data={"From": "+14155551234", "CallSid": "CA999"},
    )
    assert resp.status_code == 200
    assert "technical difficulties" in resp.text
