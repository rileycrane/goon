"""Application settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    holdplz_number: str = os.getenv("HOLDPLZ_NUMBER", os.getenv("GOON_NUMBER", ""))
    holdplz_number_display: str = os.getenv("HOLDPLZ_NUMBER_DISPLAY", "(555) 555-HOLD")
    # Backward compat
    goon_number: str = os.getenv("HOLDPLZ_NUMBER", os.getenv("GOON_NUMBER", ""))

    # Vapi
    vapi_api_key: str = os.getenv("VAPI_API_KEY", "")
    vapi_phone_number_id: str = os.getenv("VAPI_PHONE_NUMBER_ID", "")
    vapi_assistant_id: str = os.getenv("VAPI_ASSISTANT_ID", "")
    vapi_server_url: str = os.getenv("VAPI_SERVER_URL", "")

    # LLM
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

    # Business data
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Stripe
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_id: str = os.getenv("STRIPE_PRICE_ID", "")
    stripe_payment_link_url: str = os.getenv("STRIPE_PAYMENT_LINK_URL", "")

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/goon.db")
    user_data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("USER_DATA_DIR", "data/users"))
    )

    # Server
    base_url: str = os.getenv("BASE_URL", "https://holdplz.ai")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    # Free tier
    free_message_limit: int = int(os.getenv("FREE_MESSAGE_LIMIT", "10"))
    signups_enabled: bool = os.getenv("SIGNUPS_ENABLED", "true").lower() == "true"
    monthly_call_quota: int = int(os.getenv("MONTHLY_CALL_QUOTA", "20"))

    # Call recording (two-party consent compliance)
    enable_call_recording: bool = (
        os.getenv("ENABLE_CALL_RECORDING", "true").lower() == "true"
    )

    # Test mode
    enable_test_businesses: bool = (
        os.getenv("ENABLE_TEST_BUSINESSES", "false").lower() == "true"
    )
    test_business_phone: str = os.getenv("TEST_BUSINESS_PHONE", "+13308868676")
    test_mode_log_verbose: bool = (
        os.getenv("TEST_MODE_LOG_VERBOSE", "false").lower() == "true"
    )


settings = Settings()
