"""Outbound call management — Vapi calls, retries, outcome classification."""
from __future__ import annotations


async def initiate_outbound_call(
    business_name: str,
    business_phone: str,
    task: str,
    user_id: str,
    place_id: str | None = None,
) -> dict:
    """Initiate an outbound AI voice call to a business via Vapi."""
    # TODO: create Vapi call, log to call_log, return call info
    raise NotImplementedError


async def pre_call_check(
    business_name: str,
    business_phone: str,
    place_id: str | None = None,
) -> dict:
    """Run all checks before committing to a phone call."""
    # TODO: check open_now, phone score, chain detection
    raise NotImplementedError
