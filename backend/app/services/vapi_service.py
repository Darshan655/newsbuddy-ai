"""
VAPI service — initiates and manages AI voice calls.
VAPI handles TTS, STT, and real-time conversation during the call.
Costs: ~₹2-3/minute. Average 5-min call = ~₹12.
"""
import httpx
from typing import Optional

from app.core.config import settings

VAPI_BASE_URL = "https://api.vapi.ai"


def create_call(
    phone_number: str,
    script: str,
    user_name: str,
    language: str = "hi",
    call_log_id: Optional[int] = None,
) -> dict:
    """
    Initiate an outbound AI voice call via VAPI.

    Args:
        phone_number: E.164 format, e.g. +919876543210
        script: The news script to read (from openai_service.generate_script)
        user_name: For personalised greeting
        language: 'hi' | 'ne' | 'en'
        call_log_id: Our internal CallLog ID — passed as metadata to VAPI

    Returns:
        dict with 'call_id' and 'status'
    """
    system_prompt = _build_system_prompt(script, user_name, language)
    voice_config = _get_voice_config(language)

    payload = {
        "phoneNumberId": settings.VAPI_PHONE_NUMBER_ID,
        "customer": {
            "number": phone_number,
            "name": user_name,
        },
        "assistant": {
            "model": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "systemPrompt": system_prompt,
            },
            "voice": voice_config,
            "firstMessage": _get_first_message(user_name, language),
            "endCallMessage": _get_end_message(language),
            "maxDurationSeconds": settings.MAX_CALL_DURATION_MINUTES * 60,
            "backgroundSound": "off",
            "silenceTimeoutSeconds": 30,
            "responseDelaySeconds": 0.5,
            "endCallPhrases": _get_end_phrases(language),
        },
        "metadata": {
            "call_log_id": str(call_log_id) if call_log_id else "",
            "language": language,
        },
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{VAPI_BASE_URL}/call",
            headers={
                "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return {"call_id": data.get("id"), "status": data.get("status", "queued")}


def get_call_details(vapi_call_id: str) -> dict:
    """Fetch call status and metadata from VAPI."""
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{VAPI_BASE_URL}/call/{vapi_call_id}",
            headers={"Authorization": f"Bearer {settings.VAPI_API_KEY}"},
        )
        response.raise_for_status()
        return response.json()


def end_call(vapi_call_id: str) -> bool:
    """Terminate an ongoing call."""
    try:
        with httpx.Client(timeout=15) as client:
            response = client.delete(
                f"{VAPI_BASE_URL}/call/{vapi_call_id}",
                headers={"Authorization": f"Bearer {settings.VAPI_API_KEY}"},
            )
            return response.status_code == 200
    except Exception as e:
        print(f"[VAPI] end_call failed: {e}")
        return False


def get_call_transcript(vapi_call_id: str) -> Optional[str]:
    """Get the full conversation transcript from VAPI."""
    try:
        data = get_call_details(vapi_call_id)
        return data.get("transcript")
    except Exception as e:
        print(f"[VAPI] get_transcript failed: {e}")
        return None


# ── Private helpers ────────────────────────────────────────────────────────────

def _build_system_prompt(script: str, user_name: str, language: str) -> str:
    first_name = user_name.split()[0]

    if language == "hi":
        return f"""आप NewsBuddy हैं — {first_name} जी के लिए एक friendly news assistant।

आज की खबरें:
{script}

नियम:
1. ऊपर दी गई खबरें क्रम से पढ़ें
2. हर खबर के बाद पूछें: "क्या आप इस बारे में और जानना चाहते हैं?"
3. अगर user सवाल पूछें, तो खबर की जानकारी से जवाब दें
4. अगर जानकारी नहीं है: "माफ करें, इस बारे में मुझे और जानकारी नहीं है"
5. दोस्त की तरह बात करें, छोटे वाक्यों में
6. सभी खबरें पढ़ने के बाद: "और कोई सवाल?" पूछें
7. User "नहीं" या "बस" कहे तो call खत्म करें

ज़रूरी: केवल दी गई खबरों पर बात करें। कोई खबर मत बनाएं।"""

    elif language == "ne":
        return f"""तपाईं NewsBuddy हुनुहुन्छ — {first_name} जीको लागि एक मित्रवत् news assistant।

आजका समाचार:
{script}

नियमहरू:
1. माथिका समाचारहरू क्रमशः पढ्नुहोस्
2. प्रत्येक समाचार पछि सोध्नुहोस्: "के थप जान्न चाहनुहुन्छ?"
3. प्रश्नको जवाफ समाचारको जानकारीबाट दिनुहोस्
4. अन्तमा "अरू कुनै प्रश्न?" सोध्नुहोस्
5. दिइएका समाचारमा मात्र कुरा गर्नुहोस्।"""

    else:
        return f"""You are NewsBuddy — a friendly news assistant calling {first_name}.

Today's news script:
{script}

Rules:
1. Read the news items in order
2. After each story, ask: "Would you like to know more about this?"
3. If the user asks a question, answer from the news context only
4. If you don't know: "Sorry, I don't have more details on that"
5. Speak naturally, like a friend
6. After all stories: "Any other questions?"
7. End the call politely when they say no or goodbye

Important: Only discuss the news provided. Do not make up any information."""


def _get_voice_config(language: str) -> dict:
    """Return ElevenLabs voice config based on language."""
    voice_map = {
        "hi": {
            "provider": "11labs",
            "voiceId": "pNInz6obpgDQGcFmaJgB",  # Adam - works well for Hindi
            "stability": 0.6,
            "similarityBoost": 0.8,
            "style": 0.2,
            "useSpeakerBoost": True,
        },
        "ne": {
            "provider": "11labs",
            "voiceId": "pNInz6obpgDQGcFmaJgB",
            "stability": 0.6,
            "similarityBoost": 0.8,
        },
        "en": {
            "provider": "11labs",
            "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel
            "stability": 0.7,
            "similarityBoost": 0.75,
        },
    }
    return voice_map.get(language, voice_map["en"])


def _get_first_message(user_name: str, language: str) -> str:
    first_name = user_name.split()[0]
    messages = {
        "hi": f"नमस्ते {first_name} जी! मैं NewsBuddy हूं। आज {first_name} जी के लिए {first_name} जी के शहर की खबरें लेकर आया हूं। क्या आप सुनने के लिए तैयार हैं?",
        "ne": f"नमस्ते {first_name} जी! म NewsBuddy हुँ। आज तपाईंको सहरका समाचार लिएर आएको छु। के तपाईं सुन्न तयार हुनुहुन्छ?",
        "en": f"Good morning {first_name}! This is NewsBuddy with your local news. Ready to hear what's happening in your city today?",
    }
    return messages.get(language, messages["en"])


def _get_end_message(language: str) -> str:
    messages = {
        "hi": "धन्यवाद! NewsBuddy से आपका दिन शुभ हो। नमस्ते!",
        "ne": "धन्यवाद! NewsBuddy बाट तपाईंको दिन शुभ होस्। नमस्ते!",
        "en": "Thank you for listening! Have a great day. Goodbye from NewsBuddy!",
    }
    return messages.get(language, messages["en"])


def _get_end_phrases(language: str) -> list:
    phrases = {
        "hi": ["धन्यवाद", "बस", "ठीक है", "अलविदा", "बाय"],
        "ne": ["धन्यवाद", "बस", "ठीक छ", "बाई"],
        "en": ["goodbye", "bye", "that's all", "thank you", "thanks"],
    }
    return phrases.get(language, phrases["en"])
