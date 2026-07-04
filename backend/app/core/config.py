from pathlib import Path

from pydantic_settings import BaseSettings
from typing import Optional


# Backend project root = the `backend/` directory (this file lives at
# backend/app/core/config.py). On-disk paths are anchored to this so they don't
# depend on whatever directory the process happens to start in.
BASE_DIR = Path(__file__).resolve().parents[2]


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

    # Media / static files
    # Absolute base dir for generated media (voice-note .mp3s, etc.). Anchored to
    # the backend root by default; override with MEDIA_DIR in .env for deploys.
    MEDIA_DIR: str = str(BASE_DIR / "media")
    # Public, internet-reachable origin the app is served at. Twilio fetches media
    # server-side, so media URLs must be public (NOT localhost) -- set this to your
    # ngrok/deployed origin, e.g. https://abc123.ngrok.io
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Google Cloud Translation (Hindi/Nepali script translation)
    GOOGLE_TRANSLATE_API_KEY: str = ""

    # Supabase Storage (voice-note hosting)
    # On Railway the local filesystem is ephemeral and the /voicenotes static mount
    # isn't a durable public host, so generated .mp3s are uploaded to a public
    # Supabase Storage bucket ("voicenotes") and that public URL is handed to Twilio.
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

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

# Where generated voice-note .mp3s are written AND served from (mounted at
# /voicenotes in main.py). Single source of truth shared by the producer
# (news_to_voicenote.generate_voice_note) and the server (static mount).
VOICENOTES_DIR = Path(settings.MEDIA_DIR) / "voicenotes"
