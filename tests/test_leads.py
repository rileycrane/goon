"""Tests for leads engine — Component 9."""

import pytest
import pytest_asyncio

from app.db.database import Database
from app.services import leads


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Create an in-memory test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.init_schema()
    # Patch the module-level db
    leads.db = db
    yield db
    await db.close()


@pytest.fixture
def mock_send_sms(monkeypatch):
    """Capture SMS sends instead of calling Twilio."""
    sent: list[dict] = []

    async def fake_send(to: str, body: str) -> None:
        sent.append({"to": to, "body": body})

    monkeypatch.setattr(leads, "send_sms", fake_send)
    return sent


@pytest.fixture
def mock_anthropic(monkeypatch):
    """Mock the Anthropic API for teaser generation."""

    class FakeTextBlock:
        def __init__(self, text: str):
            self.text = text

    class FakeResponse:
        def __init__(self, text: str):
            self.content = [FakeTextBlock(text)]

    class FakeMessages:
        async def create(self, **kwargs):
            return FakeResponse("Looks like you need a hand! Sign up: https://getgoon.com/signup")

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)


class TestHandleUnregistered:
    @pytest.mark.asyncio
    async def test_first_attempt_logs_and_sends_teaser(self, test_db, mock_send_sms, mock_anthropic):
        response = await leads.handle_unregistered("+15551234567", "What time does Delfina close?")

        # Verify attempt was logged
        count = await test_db.fetch_one(
            "SELECT COUNT(*) as n FROM unregistered_attempts WHERE phone = ?",
            ["+15551234567"],
        )
        assert count["n"] == 1

        # Verify SMS was sent
        assert len(mock_send_sms) == 1
        assert mock_send_sms[0]["to"] == "+15551234567"
        assert "getgoon.com" in mock_send_sms[0]["body"]

    @pytest.mark.asyncio
    async def test_repeat_attempts_escalate(self, test_db, mock_send_sms, mock_anthropic):
        phone = "+15559876543"

        # First attempt
        await leads.handle_unregistered(phone, "Hours for Joe's Pizza?")
        # Second attempt
        await leads.handle_unregistered(phone, "Is Joe's open on Sunday?")
        # Third attempt
        await leads.handle_unregistered(phone, "Does Joe's deliver?")

        count = await test_db.fetch_one(
            "SELECT COUNT(*) as n FROM unregistered_attempts WHERE phone = ?",
            [phone],
        )
        assert count["n"] == 3
        assert len(mock_send_sms) == 3

    @pytest.mark.asyncio
    async def test_persistent_texter_gets_direct_push(self, test_db, mock_send_sms, mock_anthropic):
        phone = "+15550001111"

        # 4+ attempts triggers direct push
        for i in range(4):
            await leads.handle_unregistered(phone, f"Question {i + 1}")

        # The 4th response should be the direct push (not LLM-composed)
        last_sms = mock_send_sms[-1]
        assert "You've texted 4 times" in last_sms["body"]
        assert "getgoon.com" in last_sms["body"]


class TestGetLeadStats:
    @pytest.mark.asyncio
    async def test_empty_stats(self, test_db):
        stats = await leads.get_lead_stats()
        assert stats["total_unique_leads"] == 0
        assert stats["repeat_leads"] == 0
        assert stats["converted"] == 0
        assert stats["recent_attempts"] == []

    @pytest.mark.asyncio
    async def test_stats_with_data(self, test_db, mock_send_sms, mock_anthropic):
        await leads.handle_unregistered("+15551111111", "Test 1")
        await leads.handle_unregistered("+15551111111", "Test 2")
        await leads.handle_unregistered("+15552222222", "Test 3")

        stats = await leads.get_lead_stats()
        assert stats["total_unique_leads"] == 2
        assert stats["repeat_leads"] == 1
        assert stats["converted"] == 0
        assert len(stats["recent_attempts"]) == 3


class TestRecentMessages:
    @pytest.mark.asyncio
    async def test_returns_recent_bodies(self, test_db, mock_send_sms, mock_anthropic):
        phone = "+15553334444"
        await leads.handle_unregistered(phone, "First question")
        await leads.handle_unregistered(phone, "Second question")

        recent = await leads._recent_messages(phone, limit=5)
        assert len(recent) == 2
        assert "Second question" in recent
        assert "First question" in recent
