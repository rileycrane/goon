from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    goon_number: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""  # $19.99/month price object

    # Database
    database_url: str = "sqlite+aiosqlite:///data/goon.db"

    # Server
    base_url: str = "https://getgoon.com"

    # Trial
    trial_days: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
