"""Load and serve sections from the soul document."""
from __future__ import annotations

import re
from pathlib import Path

_SOUL_PATH = Path(__file__).parent / "soul.md"
_soul_text: str | None = None


def _load() -> str:
    global _soul_text
    if _soul_text is None:
        _soul_text = _SOUL_PATH.read_text()
    return _soul_text


def _extract_sections(text: str, headings: list[str]) -> str:
    """Extract named ## sections from the soul document."""
    parts: list[str] = []
    for heading in headings:
        pattern = rf"(## {re.escape(heading)}\n.*?)(?=\n## |\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            parts.append(match.group(1).strip())
    return "\n\n".join(parts)


def get_voice_soul() -> str:
    """Return soul sections relevant to the voice agent."""
    text = _load()
    return _extract_sections(text, [
        "Who You Are",
        "Personality",
        "Values",
        "Voice Agent — Tone by Scenario",
    ])


def get_sms_soul() -> str:
    """Return soul sections relevant to the SMS orchestrator."""
    text = _load()
    return _extract_sections(text, [
        "Who You Are",
        "Personality",
        "Values",
        "Boundaries",
        "SMS — Tone Guidelines",
    ])
