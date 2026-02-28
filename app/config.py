"""Application settings loaded from environment variables."""

import os


class Settings:
    """Central configuration from env vars."""

    # Twilio
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")

    # Vapi
    VAPI_API_KEY: str = os.getenv("VAPI_API_KEY", "")
    VAPI_ASSISTANT_ID: str = os.getenv("VAPI_ASSISTANT_ID", "")

    # Google Places
    GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

    # Tavily (web search)
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID: str = os.getenv("STRIPE_PRICE_ID", "")

    # App
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/goon.db")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # Test mode
    ENABLE_TEST_BUSINESSES: bool = os.getenv("ENABLE_TEST_BUSINESSES", "false").lower() == "true"


settings = Settings()
