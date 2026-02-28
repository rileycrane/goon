"""Tests for the SMS webhook route (app/routes/sms.py)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.routes.sms import router, _log_message, _process_and_respond

# Minimal FastAPI app for testing just the SMS route
from fastapi import FastAPI

app = FastAPI()
app.include_router(router, prefix="/sms")

TWILIO_FORM = {
    "From": "+14155551234",
    "Body": "Does Delfina have a table for 2 tonight?",
    "MessageSid": "SM1234567890",
}


def _make_user(
    phone: str = "+14155551234",
    status: str = "active",
    allowlisted: bool = False,
    trial_ends_at: str | None = None,
) -> dict:
    return {
        "id": phone,
        "phone": phone,
        "name": "Riley",
        "subscription_status": status,
        "allowlisted": allowlisted,
        "trial_ends_at": trial_ends_at,
    }


@pytest.fixture
def mock_services():
    """Patch all external services the SMS webhook depends on."""
    with (
        patch("app.routes.sms.get_user", new_callable=AsyncMock) as mock_get_user,
        patch("app.routes.sms.is_user_active") as mock_is_active,
        patch("app.routes.sms.handle_unregistered", new_callable=AsyncMock) as mock_leads,
        patch("app.routes.sms.send_sms", new_callable=AsyncMock) as mock_send,
        patch("app.routes.sms.db") as mock_db,
    ):
        mock_db.execute = AsyncMock(return_value=1)
        yield {
            "get_user": mock_get_user,
            "is_user_active": mock_is_active,
            "handle_unregistered": mock_leads,
            "send_sms": mock_send,
            "db": mock_db,
        }


async def _post_sms(form_data: dict | None = None) -> tuple:
    """POST to the webhook and return (status_code, response_text)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sms/webhook", data=form_data or TWILIO_FORM)
    return resp.status_code, resp.text


async def test_unregistered_sender_routes_to_leads(mock_services):
    """Unregistered phone numbers should be routed to the leads funnel."""
    mock_services["get_user"].return_value = None

    status, body = await _post_sms()

    assert status == 200
    assert "<Response></Response>" in body
    mock_services["get_user"].assert_awaited_once_with("+14155551234")
    # handle_unregistered is called as a background task — give it a tick
    await asyncio.sleep(0.05)
    mock_services["handle_unregistered"].assert_awaited_once_with(
        "+14155551234", "Does Delfina have a table for 2 tonight?"
    )


async def test_inactive_user_gets_renewal_nudge(mock_services):
    """Inactive subscription should get a renewal SMS."""
    user = _make_user(status="canceled")
    mock_services["get_user"].return_value = user
    mock_services["is_user_active"].return_value = False

    status, body = await _post_sms()

    assert status == 200
    assert "<Response></Response>" in body
    await asyncio.sleep(0.05)
    mock_services["send_sms"].assert_awaited_once()
    msg = mock_services["send_sms"].call_args[0][1]
    assert "inactive" in msg.lower()
    assert "/billing" in msg


async def test_active_user_logs_and_dispatches(mock_services):
    """Active user: log inbound, dispatch to orchestrator, return TwiML."""
    user = _make_user(status="active")
    mock_services["get_user"].return_value = user
    mock_services["is_user_active"].return_value = True

    with patch("app.routes.sms._process_and_respond", new_callable=AsyncMock) as mock_process:
        status, body = await _post_sms()

        assert status == 200
        assert "<Response></Response>" in body

        # Inbound message should be logged
        mock_services["db"].execute.assert_awaited_once()
        call_args = mock_services["db"].execute.call_args
        assert "INSERT INTO message_log" in call_args[0][0]
        params = call_args[0][1]
        assert params[0] == "+14155551234"  # user_id
        assert params[1] == "in"  # direction
        assert params[2] == "Does Delfina have a table for 2 tonight?"

        # Orchestrator dispatched as background task
        await asyncio.sleep(0.05)
        mock_process.assert_awaited_once_with(
            "+14155551234",
            "+14155551234",
            "Does Delfina have a table for 2 tonight?",
        )


async def test_empty_body_returns_twiml(mock_services):
    """Missing Body field should return empty TwiML without processing."""
    status, body = await _post_sms({"From": "+14155551234", "Body": ""})

    assert status == 200
    assert "<Response></Response>" in body
    mock_services["get_user"].assert_not_awaited()


async def test_missing_from_returns_twiml(mock_services):
    """Missing From field should return empty TwiML without processing."""
    status, body = await _post_sms({"From": "", "Body": "hello"})

    assert status == 200
    assert "<Response></Response>" in body
    mock_services["get_user"].assert_not_awaited()


async def test_process_and_respond_sends_sms():
    """_process_and_respond should call orchestrator and send SMS."""
    with (
        patch(
            "app.routes.sms.send_sms", new_callable=AsyncMock
        ) as mock_send,
        patch("app.routes.sms.db") as mock_db,
        patch(
            "app.services.orchestrator.handle_message",
            new_callable=AsyncMock,
            return_value="Delfina is open til 10 tonight.",
        ),
    ):
        mock_db.execute = AsyncMock(return_value=1)
        await _process_and_respond("+14155551234", "+14155551234", "Is Delfina open?")

        mock_send.assert_awaited_once_with("+14155551234", "Delfina is open til 10 tonight.")


async def test_process_and_respond_handles_not_implemented():
    """When orchestrator raises NotImplementedError, send a graceful fallback."""
    with (
        patch(
            "app.routes.sms.send_sms", new_callable=AsyncMock
        ) as mock_send,
        patch("app.routes.sms.db") as mock_db,
        patch(
            "app.services.orchestrator.handle_message",
            new_callable=AsyncMock,
            side_effect=NotImplementedError,
        ),
    ):
        mock_db.execute = AsyncMock(return_value=1)
        await _process_and_respond("+14155551234", "+14155551234", "hello")

        mock_send.assert_awaited_once()
        msg = mock_send.call_args[0][1]
        assert "getting set up" in msg.lower()


async def test_process_and_respond_handles_error():
    """When orchestrator raises an unexpected error, send a graceful fallback."""
    with (
        patch(
            "app.routes.sms.send_sms", new_callable=AsyncMock
        ) as mock_send,
        patch("app.routes.sms.db") as mock_db,
        patch(
            "app.services.orchestrator.handle_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ),
    ):
        mock_db.execute = AsyncMock(return_value=1)
        await _process_and_respond("+14155551234", "+14155551234", "hello")

        mock_send.assert_awaited_once()
        msg = mock_send.call_args[0][1]
        assert "went wrong" in msg.lower()
