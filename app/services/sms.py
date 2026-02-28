"""SMS sending service (Twilio). Stub for now -- other components will flesh this out."""

import logging

logger = logging.getLogger(__name__)


async def send_sms(to: str, body: str) -> None:
    """Send an SMS message. Currently a stub that logs the message.

    Full implementation (Twilio integration, segment-aware splitting,
    GSM 7-bit enforcement) will be added by the SMS Gateway component.
    """
    logger.info("SMS -> %s: %s", to, body[:160])
