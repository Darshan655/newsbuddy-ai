from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import re

from app.models.database import get_db, User, CallLog
from app.models.schemas import VAPICallEvent

router = APIRouter()


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
                    f"Reply *TIME HH:MM* to change your call time.\n"
                    f"Reply *HELP* for all options."
                )
        except (IndexError, ValueError):
            reply = (
                "❌ Format not recognised. Please try:\n"
                "*SIGNUP Name | City | Language*\n\n"
                "Example: SIGNUP Priya Singh | Kathmandu | Nepali"
            )
        return _twilio_twiml_response(reply)

    # ── Change call time ───────────────────────────────────────────────────────
    if message.upper().startswith("TIME") and user:
        try:
            time_str = message[4:].strip()
            h, m = map(int, time_str.split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
            user.preferred_call_time = time_str
            db.commit()
            reply = f"⏰ Done! Your daily call is now set for {time_str} every morning."
        except Exception:
            reply = "❌ Invalid time. Try: TIME 08:30"
        return _twilio_twiml_response(reply)

    # ── HELP ───────────────────────────────────────────────────────────────────
    if message.upper() == "HELP":
        reply = (
            "*NewsBuddy Commands:*\n\n"
            "📞 *CALL NOW* — Request a call right now\n"
            "⏰ *TIME 08:30* — Change your daily call time\n"
            "🔄 *CALL IN 15* — Call me in 15 minutes\n"
            "📍 *CITY Pokhara* — Change your city\n"
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

    # ── CALL NOW ──────────────────────────────────────────────────────────────
    if message.upper() in ("CALL NOW", "CALL", "CALL ME") and user:
        call = CallLog(user_id=user.id, scheduled_at=datetime.utcnow(), status="scheduled")
        db.add(call)
        db.commit()
        reply = f"📞 Calling you in 1-2 minutes, {user.name}!"
        return _twilio_twiml_response(reply)

    # ── Default ────────────────────────────────────────────────────────────────
    if not user:
        reply = "👋 Reply *START* to sign up for NewsBuddy — daily local news by voice call!"
    else:
        reply = f"Hi {user.name}! Reply *HELP* to see available commands."

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
