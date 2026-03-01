"""Twilio SMS sending — segment-aware, GSM 7-bit only."""

import re
from app.config import settings

GSM_PATTERN = re.compile(r'^[\x20-\x7E\n\r]*$')


def calculate_segments(body: str) -> int:
    """SMS segment math. Unicode (emoji) halves capacity."""
    is_gsm = GSM_PATTERN.match(body) is not None
    if is_gsm:
        return 1 if len(body) <= 160 else -(-len(body) // 153)
    else:
        return 1 if len(body) <= 70 else -(-len(body) // 67)


def strip_emoji(text: str) -> str:
    """Replace emoji with text equivalents, strip remaining non-GSM chars."""
    replacements = {
        '\U0001f4de': '[call]',
        '\u2705': '[done]',
        '\u274c': '[x]',
        '\U0001f551': '[time]',
    }
    for emoji, replacement in replacements.items():
        text = text.replace(emoji, replacement)
    if not GSM_PATTERN.match(text):
        text = text.encode('ascii', 'ignore').decode('ascii')
    return text


def split_at_sentences(text: str, max_chars: int = 460) -> list[str]:
    """Split text at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current.strip())
    return chunks


async def send_sms(to: str, body: str) -> None:
    """Send SMS, splitting if needed. Avoids emoji to stay in GSM encoding."""
    body = strip_emoji(body)

    if len(body) <= 480:
        await _send(to, body)
    else:
        chunks = split_at_sentences(body, max_chars=460)
        for chunk in chunks:
            await _send(to, chunk)


async def _send(to: str, body: str) -> None:
    """Send a single SMS via Twilio."""
    import logging

    try:
        from twilio.rest import Client
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(to=to, from_=settings.goon_number, body=body)
    except Exception:
        logging.getLogger(__name__).exception("Failed to send SMS to %s", to)
