from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    goon_number: str = ""  # deprecated, use holdplz_number

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # Vapi
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""

    # Google Places
    google_places_api_key: str = ""

    # Tavily (web search)
    tavily_api_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_payment_link_url: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///data/goon.db"
    database_path: str = "data/goon.db"

    # Server
    base_url: str = "https://holdplz.ai"

    # User data
    user_data_dir: str = "data/users"

    # Trial
    trial_days: int = 7

    # Free tier
    free_message_limit: int = 10
    signups_enabled: bool = True
    monthly_call_quota: int = 20

    # Hold Plz number (display format)
    holdplz_number: str = ""
    holdplz_number_display: str = "(555) 555-HOLD"

    # Admin
    admin_password: str = ""

    # Test mode
    enable_test_businesses: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
