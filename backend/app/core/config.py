from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-this-in-production"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/newsbuddy"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # VAPI (Voice calling)
    VAPI_API_KEY: str = ""
    VAPI_PHONE_NUMBER_ID: str = ""

    # Twilio / WhatsApp
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"  # Twilio sandbox default

    # Exotel (India calling - as per business report)
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    EXOTEL_SID: str = ""
    EXOTEL_CALLER_ID: str = ""

    # Call settings
    MAX_CALL_DURATION_MINUTES: int = 10
    CALL_RETRY_ATTEMPTS: int = 2
    CALL_RETRY_DELAY_MINUTES: int = 5
    FREE_TIER_CALLS_PER_WEEK: int = 3

    # Defaults
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"
    DEFAULT_LANGUAGE: str = "hi"

    # Pricing (INR)
    BASIC_PLAN_PRICE: int = 149
    PREMIUM_PLAN_PRICE: int = 299

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
