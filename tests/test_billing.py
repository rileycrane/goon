from unittest.mock import patch

import pytest

from app.services import auth, billing


@pytest.fixture(autouse=True)
def patch_dbs(test_db):
    """Patch db in auth and billing modules, and mock stripe."""
    with (
        patch.object(auth, "db", test_db),
        patch.object(billing, "db", test_db),
        patch.object(billing, "stripe") as mock_stripe,
    ):
        mock_stripe.Customer.retrieve.return_value = {"email": "test@test.com"}
        yield mock_stripe


async def test_handle_checkout_completed_new_user(patch_dbs):
    """Checkout completed for a brand-new user creates a user record."""
    session = {
        "customer": "cus_new",
        "metadata": {
            "goon_phone": "+14155559999",
            "goon_name": "New User",
        },
    }
    user = await billing.handle_checkout_completed(session)

    assert user is not None
    assert user["phone"] == "+14155559999"
    assert user["name"] == "New User"
    assert user["subscription_status"] == "active"
    assert user["stripe_customer_id"] == "cus_new"


async def test_handle_checkout_completed_resubscribe(patch_dbs):
    """Checkout completed for an existing canceled user reactivates them."""
    await auth.create_user(
        phone="+14155558888",
        name="Returning",
        email="ret@test.com",
        stripe_customer_id="cus_old",
        subscription_status="canceled",
    )

    session = {
        "customer": "cus_renewed",
        "metadata": {
            "goon_phone": "+14155558888",
            "goon_name": "Returning",
        },
    }
    user = await billing.handle_checkout_completed(session)

    assert user is not None
    assert user["subscription_status"] == "active"
    assert user["stripe_customer_id"] == "cus_renewed"


async def test_handle_checkout_completed_no_phone(patch_dbs):
    """Checkout with no phone in metadata returns None."""
    session = {"customer": "cus_x", "metadata": {}}
    user = await billing.handle_checkout_completed(session)
    assert user is None


async def test_handle_subscription_updated(patch_dbs):
    """Subscription status change updates the user record."""
    await auth.create_user(
        phone="+14155557777",
        name="Subscriber",
        email="sub@test.com",
        stripe_customer_id="cus_sub",
        subscription_status="active",
    )

    subscription = {
        "customer": "cus_sub",
        "status": "past_due",
    }
    await billing.handle_subscription_updated(subscription)

    user = await auth.get_user("+14155557777")
    assert user is not None
    assert user["subscription_status"] == "past_due"


async def test_handle_subscription_deleted(patch_dbs):
    """Subscription deletion cancels the user."""
    await auth.create_user(
        phone="+14155556666",
        name="Canceler",
        email="cancel@test.com",
        stripe_customer_id="cus_cancel",
        subscription_status="active",
    )

    subscription = {"customer": "cus_cancel"}
    await billing.handle_subscription_deleted(subscription)

    user = await auth.get_user("+14155556666")
    assert user is not None
    assert user["subscription_status"] == "canceled"


async def test_handle_subscription_updated_maps_trialing(patch_dbs):
    """Stripe 'trialing' status maps to our 'trial' status."""
    await auth.create_user(
        phone="+14155555555",
        name="Trialer",
        email="trial@test.com",
        stripe_customer_id="cus_trial",
        subscription_status="active",
    )

    subscription = {"customer": "cus_trial", "status": "trialing"}
    await billing.handle_subscription_updated(subscription)

    user = await auth.get_user("+14155555555")
    assert user is not None
    assert user["subscription_status"] == "trial"
