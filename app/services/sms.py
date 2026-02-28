"""Twilio SMS — segment-aware message sending."""


async def send_sms(to: str, body: str) -> str:
    """Send an SMS via Twilio. Returns message SID.

    Handles segment math: targets 160 chars (GSM 7-bit).
    No emoji — forces unicode, halves segment capacity.
    Splits at sentence boundaries if over 160 chars.
    """
    # TODO: implement Twilio SMS sending with segment awareness
    raise NotImplementedError
