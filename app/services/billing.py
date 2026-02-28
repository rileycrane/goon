"""Stripe subscription management."""


async def create_customer(user_id: str, email: str) -> str:
    """Create a Stripe customer. Returns customer ID."""
    # TODO: implement Stripe customer creation
    raise NotImplementedError


async def handle_subscription_event(event: dict) -> None:
    """Process a Stripe subscription lifecycle event."""
    # TODO: update user subscription_status based on event type
    raise NotImplementedError
