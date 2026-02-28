from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.services import auth


@pytest.fixture(autouse=True)
def patch_db(test_db):
    """Patch the global db instance to use our test database."""
    with patch.object(auth, "db", test_db):
        yield test_db


async def test_get_user_not_found(patch_db):
    result = await auth.get_user("+10000000000")
    assert result is None


async def test_create_and_get_user(patch_db):
    user = await auth.create_user(
        phone="+14155551234",
        name="Riley",
        email="riley@test.com",
        stripe_customer_id="cus_test123",
        subscription_status="active",
    )
    assert user["phone"] == "+14155551234"
    assert user["name"] == "Riley"
    assert user["subscription_status"] == "active"

    fetched = await auth.get_user("+14155551234")
    assert fetched is not None
    assert fetched["email"] == "riley@test.com"


async def test_is_user_active_active(patch_db):
    user = await auth.create_user(
        phone="+14155550001",
        name="Active",
        email="a@test.com",
        stripe_customer_id="cus_a",
        subscription_status="active",
    )
    assert auth.is_user_active(user) is True


async def test_is_user_active_canceled(patch_db):
    user = await auth.create_user(
        phone="+14155550002",
        name="Canceled",
        email="c@test.com",
        stripe_customer_id="cus_c",
        subscription_status="canceled",
    )
    assert auth.is_user_active(user) is False


async def test_is_user_active_trial_valid(patch_db):
    future = (datetime.now() + timedelta(days=3)).isoformat()
    user = await auth.create_user(
        phone="+14155550003",
        name="Trial",
        email="t@test.com",
        stripe_customer_id="cus_t",
        subscription_status="trial",
        trial_ends_at=future,
    )
    assert auth.is_user_active(user) is True


async def test_is_user_active_trial_expired(patch_db):
    past = (datetime.now() - timedelta(days=1)).isoformat()
    user = await auth.create_user(
        phone="+14155550004",
        name="Expired",
        email="e@test.com",
        stripe_customer_id="cus_e",
        subscription_status="trial",
        trial_ends_at=past,
    )
    assert auth.is_user_active(user) is False


async def test_is_user_active_allowlisted(patch_db):
    user = await auth.create_user(
        phone="+14155550005",
        name="Tester",
        email="tester@test.com",
        stripe_customer_id="cus_tester",
        subscription_status="canceled",
        allowlisted=True,
    )
    assert auth.is_user_active(user) is True


async def test_update_subscription_status(patch_db):
    await auth.create_user(
        phone="+14155550006",
        name="Updater",
        email="u@test.com",
        stripe_customer_id="cus_u",
        subscription_status="active",
    )
    await auth.update_subscription_status("+14155550006", "past_due")
    user = await auth.get_user("+14155550006")
    assert user is not None
    assert user["subscription_status"] == "past_due"


async def test_is_user_active_past_due(patch_db):
    user = await auth.create_user(
        phone="+14155550007",
        name="PastDue",
        email="pd@test.com",
        stripe_customer_id="cus_pd",
        subscription_status="past_due",
    )
    assert auth.is_user_active(user) is False
