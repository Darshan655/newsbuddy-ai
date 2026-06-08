"""
WhatsApp service — sends messages via Twilio WhatsApp Business API.
Used for: post-call summaries, breaking news alerts, signup confirmations.
Cost: ~₹0.67 per message (Meta Business API via Twilio).
"""
from twilio.rest import Client
from typing import Optional

from app.core.config import settings


def send_message(to_number: str, message: str) -> Optional[str]:
    """
    Send a WhatsApp message to a user.

    Args:
        to_number: Phone in E.164, e.g. +919876543210 (without 'whatsapp:' prefix)
        message: Text to send (supports *bold* and emoji)

    Returns:
        Twilio message SID if successful, None on failure
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_number}",
            body=message,
        )
        return msg.sid
    except Exception as e:
        print(f"[WhatsApp] Failed to send to {to_number}: {e}")
        return None


def send_post_call_summary(
    to_number: str,
    user_name: str,
    summary: str,
    source_links: Optional[list] = None,
) -> Optional[str]:
    """
    Send a formatted post-call summary with news summary and source links.
    Called after a VAPI call completes.
    """
    links_section = ""
    if source_links:
        links_section = "\n\n🔗 *Sources:*\n" + "\n".join(f"• {url}" for url in source_links[:3])

    message = (
        f"📰 *NewsBuddy — आज की खबरें*\n"
        f"_({user_name} के लिए)_\n\n"
        f"{summary}"
        f"{links_section}\n\n"
        f"─────────────────\n"
        f"_Reply *HELP* for options | Reply *CALL NOW* for another call_"
    )
    return send_message(to_number, message)


def send_breaking_news_alert(
    to_number: str,
    user_name: str,
    headline: str,
    city: str,
    language: str = "hi",
) -> Optional[str]:
    """
    Send an urgent breaking news WhatsApp alert (Premium feature).
    """
    if language == "hi":
        message = (
            f"🚨 *ब्रेकिंग न्यूज़ — {city}*\n\n"
            f"{headline}\n\n"
            f"📞 Reply *CALL NOW* for full details on call\n"
            f"_NewsBuddy Premium Alert_"
        )
    elif language == "ne":
        message = (
            f"🚨 *ब्रेकिङ न्युज — {city}*\n\n"
            f"{headline}\n\n"
            f"📞 *CALL NOW* भन्नुहोस् विस्तृत जानकारीको लागि\n"
            f"_NewsBuddy Premium Alert_"
        )
    else:
        message = (
            f"🚨 *Breaking News — {city}*\n\n"
            f"{headline}\n\n"
            f"📞 Reply *CALL NOW* for full details\n"
            f"_NewsBuddy Premium Alert_"
        )
    return send_message(to_number, message)


def send_missed_call_notification(
    to_number: str,
    user_name: str,
    language: str = "hi",
) -> Optional[str]:
    """
    Notify user that we tried to call but couldn't reach them.
    Gives them option to reschedule.
    """
    first_name = user_name.split()[0]
    if language == "hi":
        message = (
            f"📞 {first_name} जी, हमने आपको call करने की कोशिश की लेकिन आप available नहीं थे।\n\n"
            f"Reply करें:\n"
            f"• *CALL NOW* — अभी call करें\n"
            f"• *CALL IN 15* — 15 मिनट में call करें\n"
            f"• *TIME 10:00* — daily call time बदलें"
        )
    elif language == "ne":
        message = (
            f"📞 {first_name} जी, हामीले तपाईंलाई call गर्ने प्रयास गर्यौं तर सम्पर्क हुन सकेन।\n\n"
            f"*CALL NOW* वा *CALL IN 15* भन्नुहोस्।"
        )
    else:
        message = (
            f"📞 Hi {first_name}! We tried to call but couldn't reach you.\n\n"
            f"Reply:\n"
            f"• *CALL NOW* — Call me now\n"
            f"• *CALL IN 15* — Call me in 15 minutes\n"
            f"• *TIME 10:00* — Change my daily call time"
        )
    return send_message(to_number, message)
