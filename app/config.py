"""Settings from environment variables."""

import os
from pathlib import Path


# Twilio
TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
GOON_NUMBER: str = os.environ.get("GOON_NUMBER", "")

# Anthropic
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

# Database
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///data/goon.db")
DATABASE_PATH: Path = Path(
    DATABASE_URL.replace("sqlite:///", "") if DATABASE_URL.startswith("sqlite:///") else "data/goon.db"
)

# User data
USER_DATA_DIR: Path = Path(os.environ.get("USER_DATA_DIR", "data/users"))

# App
BASE_URL: str = os.environ.get("BASE_URL", "https://getgoon.com")
SIGNUP_URL: str = f"{BASE_URL}/signup" if BASE_URL else "https://getgoon.com/signup"
