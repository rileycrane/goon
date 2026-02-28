import os
from pathlib import Path

# User data directory — contains per-user profile.md, conversations.jsonl, etc.
USER_DATA_DIR = Path(os.getenv("USER_DATA_DIR", "data/users"))

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

# How many recent messages to keep in memory (loaded from JSONL)
MEMORY_RECENT_LIMIT = 20

# How many recent messages to include in LLM context
MEMORY_CONTEXT_LIMIT = 5
