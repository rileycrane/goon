"""Twilio SMS sending — segment-aware, GSM 7-bit only."""

import re
from app.config import settings

GSM_PATTERN = re.compile(r'^[\x20-\x7E\n\r]*$')
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*')
_MD_ITALIC = re.compile(r'\*(.+?)\*')
_MD_HEADER = re.compile(r'^#{1,3}\s+', re.MULTILINE)
_MD_BULLET = re.compile(r'^[-*]\s+', re.MULTILINE)


def calculate_segments(body: str) -> int:
    """SMS segment math. Unicode (emoji) halves capacity."""
    is_gsm = GSM_PATTERN.match(body) is not None
    if is_gsm:
        return 1 if len(body) <= 160 else -(-len(body) // 153)
    else:
        return 1 if len(body) <= 70 else -(-len(body) // 67)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting that slips through the LLM. Safety net."""
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_ITALIC.sub(r'\1', text)
    text = _MD_HEADER.sub('', text)
    text = _MD_BULLET.sub('', text)
    return text


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
    """Send SMS, splitting if needed. Strips markdown and emoji to stay in GSM encoding.

    Also logs outbound messages to message_log so all SMS appear in admin dashboard.
    """
    body = strip_markdown(body)
    body = strip_emoji(body)

    if len(body) <= 480:
        await _send(to, body)
    else:
        chunks = split_at_sentences(body, max_chars=460)
        for chunk in chunks:
            await _send(to, chunk)

    # Log outbound message
    try:
        from app.db.database import db
        await db.execute(
            "INSERT INTO message_log (user_id, direction, body) VALUES (?, 'out', ?)",
            [to, body],
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to log outbound SMS to %s", to)


async def _send(to: str, body: str) -> None:
    """Send a single SMS via Twilio."""
    import logging

    try:
        from twilio.rest import Client
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(to=to, from_=settings.goon_number, body=body)
    except Exception:
        logging.getLogger(__name__).exception("Failed to send SMS to %s", to)
