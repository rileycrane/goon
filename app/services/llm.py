"""LLM client with automatic model fallback.

When a model returns 529 (overloaded) or 5xx, tries the next model in the
fallback chain. This keeps the system running during partial Anthropic outages.

Future: stub for OpenAI/other provider fallback.
"""
from __future__ import annotations

import logging

import anthropic

logger = logging.getLogger(__name__)

# Fallback chains by tier
_STANDARD_CHAIN = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]

_PREMIUM_CHAIN = [
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]

# Re-export for direct use
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-5-20250929"

# Retryable error codes — model is temporarily unavailable
_RETRYABLE_STATUS = {529, 500, 502, 503}


async def create(
    *,
    messages: list[dict],
    system: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: dict | None = None,
    max_tokens: int = 1024,
    tier: str = "standard",
) -> anthropic.types.Message | None:
    """Call Anthropic with automatic model fallback.

    tier="standard" tries Haiku first (cheap), tier="premium" tries Sonnet first.
    Returns None if all models fail.
    """
    chain = _STANDARD_CHAIN if tier == "standard" else _PREMIUM_CHAIN
    client = anthropic.AsyncAnthropic()
    last_error = None

    for model in chain:
        try:
            kwargs: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system is not None:
                kwargs["system"] = system
            if tools is not None:
                kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice

            resp = await client.messages.create(**kwargs)
            return resp

        except anthropic.InternalServerError as e:
            last_error = e
            logger.warning("Model %s unavailable (529/5xx): %s — trying next", model, e)
            continue
        except anthropic.RateLimitError as e:
            last_error = e
            logger.warning("Model %s rate-limited: %s — trying next", model, e)
            continue
        except anthropic.APIStatusError as e:
            if e.status_code in _RETRYABLE_STATUS:
                last_error = e
                logger.warning("Model %s error %d — trying next", model, e.status_code)
                continue
            raise  # 4xx = real error, don't retry

    logger.error("All LLM models failed. Last error: %s", last_error)
    return None


def extract_text(response: anthropic.types.Message | None) -> str | None:
    """Extract text content from a response, or None if response is None."""
    if response is None:
        return None
    text_blocks = [b.text for b in response.content if b.type == "text"]
    return "\n".join(text_blocks) if text_blocks else None


def extract_tool_use(
    response: anthropic.types.Message | None, tool_name: str
) -> dict | None:
    """Extract a specific tool use result from a response."""
    if response is None:
        return None
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    return None


# ---- Future provider stubs ----

async def _openai_fallback(
    messages: list[dict],
    max_tokens: int = 1024,
    system: str | None = None,
) -> dict | None:
    """Placeholder for OpenAI fallback. Returns None (not implemented).

    To enable:
    1. pip install openai
    2. Set OPENAI_API_KEY in environment
    3. Implement message format conversion (Anthropic -> OpenAI)
    4. Add to the fallback chain in create()
    """
    # from openai import AsyncOpenAI
    # client = AsyncOpenAI()
    # oai_messages = _convert_messages_to_openai(messages, system)
    # response = await client.chat.completions.create(
    #     model="gpt-4o-mini",
    #     max_tokens=max_tokens,
    #     messages=oai_messages,
    # )
    # return _convert_openai_response(response)
    return None
