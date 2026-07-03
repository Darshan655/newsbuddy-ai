from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import re

from app.models.database import get_db, User, CallLog, NewsCategory
from app.models.schemas import VAPICallEvent

router = APIRouter()

# Canonical topic taxonomy for the NEWS TYPE command -- mirrors NewsCategory
# so we don't invent a second list of topic names.
VALID_TOPICS = [c.value for c in NewsCategory]

# Language codes the LANGUAGE command accepts, mapped to display names.
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "ne": "Nepali"}


# ── WhatsApp Webhook ───────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    From: str = Form(...),
    Body: str = Form(...),
    To: str = Form(...),
    ProfileName: str = Form(default=""),
):
    """
    Handles incoming WhatsApp messages from Twilio.
    Manages the signup flow and reschedule requests.
    """
    phone = From.replace("whatsapp:", "")
    message = Body.strip()

    user = db.query(User).filter(User.phone_number == phone).first()

    # ── Reschedule intent ──────────────────────────────────────────────────────
    minutes = _parse_call_in_minutes(message)
    if minutes and user:
        new_time = datetime.utcnow() + timedelta(minutes=minutes)
        call = CallLog(user_id=user.id, scheduled_at=new_time, status="scheduled")
        db.add(call)
        db.commit()
        reply = f"✅ Got it, {user.name}! I'll call you in {minutes} minutes at {new_time.strftime('%I:%M %p')} IST."
        return _twilio_twiml_response(reply)

    # ── New user signup ────────────────────────────────────────────────────────
    if message.upper() in ("START", "HELLO", "HI", "NAMASTE", "नमस्ते") and not user:
        reply = (
            f"🙏 Namaste! Welcome to *NewsBuddy* — your daily local news by voice.\n\n"
            f"To get started, please reply with:\n"
            f"*SIGNUP Name | City | Language*\n\n"
            f"Example:\n"
            f"SIGNUP Rajesh Kumar | Gorakhpur | Hindi\n\n"
            f"Languages: Hindi, Nepali, English"
        )
        return _twilio_twiml_response(reply)

    # ── Parse SIGNUP command ───────────────────────────────────────────────────
    if message.upper().startswith("SIGNUP"):
        try:
            parts = message[6:].strip().split("|")
            name = parts[0].strip()
            city = parts[1].strip()
            lang_str = parts[2].strip().lower() if len(parts) > 2 else "hi"
            lang_map = {"hindi": "hi", "nepali": "ne", "english": "en", "hi": "hi", "ne": "ne", "en": "en"}
            language = lang_map.get(lang_str, "hi")

            if user:
                reply = f"✅ You're already registered, {user.name}! Reply *HELP* for options."
            else:
                new_user = User(
                    phone_number=phone,
                    whatsapp_number=phone,
                    name=name,
                    city=city,
                    language=language,
                    preferred_call_time="07:00",
                    topics=[],
                )
                db.add(new_user)
                db.commit()
                reply = (
                    f"🎉 Welcome, *{name}*! You're registered for NewsBuddy.\n\n"
                    f"📍 City: {city}\n"
                    f"🗣️ Language: {lang_str.title()}\n"
                    f"⏰ Daily call: 7:00 AM\n\n"
                    f"You'll get your first call tomorrow morning!\n"
                    f"Reply *TIME 7:00 AM* to change your call time.\n"
                    f"Reply *CITY Pokhara* to change your city.\n"
                    f"Reply *NEWS TYPE business, crime* to set your topics.\n"
                    f"Reply *LANGUAGE en* to change your language.\n"
                    f"Reply *HELP* for all options."
                )
        except (IndexError, ValueError):
            reply = (
                "❌ Format not recognised. Please try:\n"
                "*SIGNUP Name | City | Language*\n\n"
                "Example: SIGNUP Priya Singh | Kathmandu | Nepali"
            )
        return _twilio_twiml_response(reply)

    # ── View call time ─────────────────────────────────────────────────────────
    if message.upper() == "TIME" and user:
        current = user.preferred_call_time or "07:00"
        reply = f"⏰ Your daily call is currently set for {_format_time_12h(current)}."
        return _twilio_twiml_response(reply)

    # ── Set call time ──────────────────────────────────────────────────────────
    if message.upper().startswith("TIME ") and user:
        time_arg = message[5:].strip()
        parsed = _parse_time_string(time_arg)
        if not parsed:
            reply = (
                "❌ Couldn't understand that time. Try:\n"
                "*TIME 7:00 AM* or *TIME 19:30*"
            )
        else:
            user.preferred_call_time = parsed
            db.commit()
            reply = f"Got it! I'll send your news at {_format_time_12h(parsed)} daily."
        return _twilio_twiml_response(reply)

    # ── View news topics ───────────────────────────────────────────────────────
    if message.upper() == "NEWS TYPE" and user:
        if user.topics:
            reply = f"📰 Your current news topics: {', '.join(user.topics)}."
        else:
            reply = "📰 You haven't set specific topics yet — you're getting general local news."
        return _twilio_twiml_response(reply)

    # ── Set news topics ────────────────────────────────────────────────────────
    if message.upper().startswith("NEWS TYPE ") and user:
        raw_topics = message[len("NEWS TYPE "):].strip()
        requested = [t.strip().lower().replace(" ", "_") for t in raw_topics.split(",") if t.strip()]
        valid = [t for t in requested if t in VALID_TOPICS]
        invalid = [t for t in requested if t not in VALID_TOPICS]

        if not valid:
            reply = (
                "❌ I didn't recognise any of those topics. Choose from:\n"
                f"{', '.join(VALID_TOPICS)}"
            )
        else:
            user.topics = valid
            db.commit()
            reply = f"📰 Got it! You'll now hear news about: {', '.join(valid)}."
            if invalid:
                reply += f"\n(Skipped unrecognised: {', '.join(invalid)})"
        return _twilio_twiml_response(reply)

    # ── View city ──────────────────────────────────────────────────────────────
    if message.upper() == "CITY" and user:
        if user.city and user.city.strip():
            reply = f"📍 Your city is currently set to {user.city}."
        else:
            reply = "📍 You haven't set your city yet. Reply CITY Nepalgunj to set it."
        return _twilio_twiml_response(reply)

    # ── Set city ───────────────────────────────────────────────────────────────
    if message.upper().startswith("CITY ") and user:
        new_city = message[5:].strip()
        if not new_city:
            reply = "❌ Please include a city name, e.g. CITY Nepalgunj."
        else:
            user.city = new_city
            db.commit()
            reply = f"📍 Got it! You'll now get news for {new_city}."
        return _twilio_twiml_response(reply)

    # ── View language ──────────────────────────────────────────────────────────
    if message.upper() == "LANGUAGE" and user:
        current = LANGUAGE_NAMES.get(user.language, user.language or "English")
        reply = f"🗣️ Your current language: {current}."
        return _twilio_twiml_response(reply)

    # ── Set language ───────────────────────────────────────────────────────────
    if message.upper().startswith("LANGUAGE ") and user:
        lang_arg = message[len("LANGUAGE "):].strip().lower()
        if lang_arg not in LANGUAGE_NAMES:
            reply = (
                "❌ I don't recognise that. Choose from:\n"
                "en (English), hi (Hindi), ne (Nepali)"
            )
        else:
            user.language = lang_arg
            db.commit()
            reply = f"🗣️ Got it! Your news will now be in {LANGUAGE_NAMES[lang_arg]}."
            if lang_arg in ("hi", "ne"):
                reply += (
                    f"\n({LANGUAGE_NAMES[lang_arg]} is coming soon — you'll get "
                    f"English news for now, and we'll switch you over "
                    f"automatically once it's ready.)"
                )
        return _twilio_twiml_response(reply)

    # ── HELP ───────────────────────────────────────────────────────────────────
    if message.upper() == "HELP":
        reply = (
            "*NewsBuddy Commands:*\n\n"
            "📞 *CALL NOW* — Request a call right now\n"
            "⏰ *TIME* — See your daily call time\n"
            "⏰ *TIME 7:00 AM* — Change your daily call time\n"
            "🔄 *CALL IN 15* — Call me in 15 minutes\n"
            "📍 *CITY* — See your current city\n"
            "📍 *CITY Pokhara* — Change your city\n"
            "📰 *NEWS TYPE* — See your news topics\n"
            "📰 *NEWS TYPE business, crime* — Change your news topics\n"
            "🗣️ *LANGUAGE* — See your current language\n"
            "🗣️ *LANGUAGE hi* — Change your language (en / hi / ne)\n"
            "❌ *STOP* — Pause your subscription\n"
            "▶️ *START* — Resume your subscription"
        )
        return _twilio_twiml_response(reply)

    # ── STOP / UNSUBSCRIBE ─────────────────────────────────────────────────────
    if message.upper() in ("STOP", "UNSUBSCRIBE") and user:
        user.status = "inactive"
        db.commit()
        reply = "✅ You've been unsubscribed. Reply START to resume anytime."
        return _twilio_twiml_response(reply)

    # ── CALL NOW → on-demand WhatsApp voice note ───────────────────────────────
    if message.upper() in ("CALL NOW", "CALL", "CALL ME") and user:
        # Create the CallLog already claimed ('in_progress', not 'scheduled') so
        # the VAPI phone-call sweeper (process_pending_calls) never dials it —
        # CALL NOW is now voice-note delivery, owned by send_voice_note_now.
        call = CallLog(user_id=user.id, scheduled_at=datetime.utcnow(), status="in_progress")
        db.add(call)
        db.commit()

        try:
            from app.tasks.tasks import send_voice_note_now
            send_voice_note_now.delay(call.id)
            reply = (
                f"✅ Got it, {user.name}! Generating your news now — "
                f"it'll arrive as a voice note in a moment."
            )
        except Exception as e:
            # Broker down / enqueue failed: don't leave a false ack or a stuck row.
            call.status = "failed"
            call.error_message = f"Failed to enqueue voice-note task: {e}"
            db.commit()
            print(f"[Webhook] CALL NOW enqueue failed for user {user.id}: {e}")
            reply = "😕 Sorry, I'm having trouble right now — please try again in a moment."

        return _twilio_twiml_response(reply)

    # ── Fallback: unrecognised message ────────────────────────────────────────
    # Covers brand-new users (no SIGNUP yet) and existing users who typed
    # something that doesn't match any command above -- never fail silently.
    reply = "🙏 Namaste! 👋 Type *START* to get started, or *HELP* to see what I can do."
    return _twilio_twiml_response(reply)


# ── VAPI Webhook ───────────────────────────────────────────────────────────────

@router.post("/vapi")
async def vapi_webhook(event: VAPICallEvent, db: Session = Depends(get_db)):
    """
    Handles call lifecycle events from VAPI.
    Updates CallLog status in real time.
    """
    call_id = event.call_id

    if not call_id:
        return {"status": "ok"}

    call = db.query(CallLog).filter(CallLog.vapi_call_id == call_id).first()
    if not call:
        return {"status": "call not found"}

    if event.type == "call-started":
        call.status = "in_progress"
        call.started_at = datetime.utcnow()

    elif event.type == "call-ended":
        call.status = "completed"
        call.ended_at = datetime.utcnow()
        if event.duration:
            call.duration_seconds = event.duration
        # Rough cost: ₹2.5/min for VAPI
        if call.duration_seconds:
            call.cost_inr = round(call.duration_seconds / 60 * 2.5, 2)

        # Update user's last_call_at and weekly counter
        user = db.query(User).filter(User.id == call.user_id).first()
        if user:
            user.last_call_at = datetime.utcnow()
            user.calls_this_week = (user.calls_this_week or 0) + 1

    elif event.type == "call-failed":
        call.status = "failed"
        call.error_message = event.ended_reason or "Unknown error"

    elif event.type == "transcript":
        if event.transcript:
            existing = call.questions_asked or []
            existing.append({"transcript": event.transcript, "at": datetime.utcnow().isoformat()})
            call.questions_asked = existing

    db.commit()
    return {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_time_string(raw: str) -> Optional[str]:
    """
    Parse a user-supplied time (e.g. '7:00 AM', '07:00', '19:30') into
    24-hour 'HH:MM', or None if it can't be parsed.
    """
    cleaned = raw.strip().upper()
    if not cleaned:
        return None
    formats = ["%I:%M %p", "%I:%M%p", "%I %p", "%I%p", "%H:%M", "%H.%M"]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%H:%M")
        except ValueError:
            continue
    return None


def _format_time_12h(hhmm: str) -> str:
    """Format a stored 'HH:MM' (24-hour) time as e.g. '7:00 AM' for replies."""
    dt = datetime.strptime(hhmm, "%H:%M")
    return dt.strftime("%I:%M %p").lstrip("0")


def _parse_call_in_minutes(message: str) -> int | None:
    """
    Extract minutes from messages like:
    'call me in 15 minutes', 'call in 10', '15 minutes', 'CALL IN 15'
    """
    msg = message.lower()
    patterns = [
        r"call\s+(?:me\s+)?in\s+(\d+)",
        r"(\d+)\s+minutes?",
        r"call\s+after\s+(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, msg)
        if m:
            minutes = int(m.group(1))
            if 1 <= minutes <= 1440:  # 1 min to 24 hours
                return minutes
    return None


def _twilio_twiml_response(message: str):
    """Return a Twilio TwiML response for WhatsApp."""
    from fastapi.responses import Response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{message}</Message>
</Response>"""
    return Response(content=twiml, media_type="application/xml")
