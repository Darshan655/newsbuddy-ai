"""
Quick smoke test — run this to check imports and basic logic
without needing real API keys or a database.

Usage:
    cd backend
    python test_smoke.py
"""
import sys
import os

# Make sure we can import app modules
sys.path.insert(0, os.path.dirname(__file__))

# Patch settings so we don't need a real .env
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("VAPI_API_KEY", "test")
os.environ.setdefault("VAPI_PHONE_NUMBER_ID", "test")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test")


def test_imports():
    print("Testing imports...")
    from app.core.config import settings
    assert settings.DEFAULT_LANGUAGE == "hi"
    print("  ✅ config")

    from app.models.schemas import UserCreate, NewsCreate, CallScheduleRequest
    print("  ✅ schemas")

    from app.services.openai_service import _format_news_items, _fallback_script
    print("  ✅ openai_service")

    from app.services.vapi_service import build_system_prompt, get_voice_config
    print("  ✅ vapi_service")

    from app.services.whatsapp_service import send_message
    print("  ✅ whatsapp_service")

    print("\nAll imports OK ✅")


def test_schema_validation():
    print("\nTesting schema validation...")
    from app.models.schemas import UserCreate
    from pydantic import ValidationError

    # Valid user
    u = UserCreate(phone_number="+919876543210", name="Rajesh Kumar", city="Gorakhpur")
    assert u.preferred_call_time == "07:00"
    print("  ✅ UserCreate valid")

    # Invalid phone
    try:
        UserCreate(phone_number="9876543210", name="Test", city="Delhi")
        assert False, "Should have raised"
    except ValidationError:
        print("  ✅ UserCreate rejects invalid phone")


def test_whatsapp_parser():
    print("\nTesting WhatsApp message parser...")
    import importlib
    import app.api.webhooks as wh

    assert wh._parse_call_in_minutes("call me in 15 minutes") == 15
    assert wh._parse_call_in_minutes("CALL IN 30") == 30
    assert wh._parse_call_in_minutes("10 minutes please") == 10
    assert wh._parse_call_in_minutes("hello how are you") is None
    print("  ✅ Reschedule parser works")

    # NEWS IN is the primary reschedule command; CALL IN stays a silent alias.
    assert wh._parse_call_in_minutes("NEWS IN 15") == 15
    assert wh._parse_call_in_minutes("news in 20") == 20
    assert wh._parse_call_in_minutes("news after 10") == 10
    assert wh._parse_call_in_minutes("NEWS NOW") is None  # instant, not a reschedule
    assert wh._parse_call_in_minutes("NEWS TYPE business") is None
    print("  ✅ NEWS IN parses like CALL IN")

    # NEWS NOW is the primary instant command; old CALL variants stay aliases.
    for cmd in ("NEWS NOW", "CALL NOW", "CALL", "CALL ME"):
        assert cmd in wh.NOW_COMMANDS, f"{cmd} missing from NOW_COMMANDS"
    print("  ✅ NOW_COMMANDS accepts new + legacy text")


def test_fallback_script():
    print("\nTesting fallback script generation...")
    from app.services.openai_service import _fallback_script
    script = _fallback_script("Rajesh Kumar", "Gorakhpur", "hi")
    assert "Rajesh" in script
    assert "Gorakhpur" in script
    print(f"  ✅ Hindi fallback: {script[:60]}...")

    script_en = _fallback_script("Priya Singh", "Kathmandu", "en")
    assert "Priya" in script_en
    print(f"  ✅ English fallback: {script_en[:60]}...")


if __name__ == "__main__":
    try:
        test_imports()
        test_schema_validation()
        test_whatsapp_parser()
        test_fallback_script()
        print("\n🎉 All smoke tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
