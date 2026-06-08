"""
OpenAI service — generates personalised voice call scripts and WhatsApp summaries.
Uses GPT-4o-mini for cost efficiency (~₹0.40 per script).
"""
import os
from typing import List, Optional
from openai import OpenAI

from app.core.config import settings


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_script(
    news_items: list,
    user_name: str,
    city: str,
    language: str = "hi",
    topics: Optional[List[str]] = None,
) -> str:
    """
    Generate a 5–7 minute conversational news script for a voice call.

    Args:
        news_items: list of NewsItem ORM objects or dicts with title/summary
        user_name: user's first name for personalised greeting
        city: user's city
        language: 'hi' | 'ne' | 'en'
        topics: user's preferred topic list

    Returns:
        A natural-sounding script string ready for VAPI/TTS
    """
    if not news_items:
        return _fallback_script(user_name, city, language)

    try:
        news_text = _format_news_items(news_items)
        system_prompt = _get_system_prompt(language)
        user_prompt = _get_user_prompt(user_name, city, language, news_text, topics)

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=1200,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[OpenAI] Script generation failed: {e}")
        return _fallback_script(user_name, city, language)


def summarize_for_whatsapp(news_items: list, language: str = "hi") -> str:
    """
    Generate a short WhatsApp text summary (≤200 words) to send after a call.

    Returns a formatted string with emoji bullets ready to send via Twilio.
    """
    if not news_items:
        return "📰 आज कोई खास खबर नहीं मिली।"

    try:
        news_text = _format_news_items(news_items)

        if language == "hi":
            prompt = (
                f"इन खबरों का एक छोटा WhatsApp सारांश बनाओ (अधिकतम 150 शब्द):\n\n{news_text}\n\n"
                "Format:\n📰 आज की मुख्य खबरें:\n\n1. [खबर - 1 लाइन]\n2. [खबर - 1 लाइन]\n3. [खबर - 1 लाइन]\n\nसूत्र: [source_name]"
            )
        elif language == "ne":
            prompt = f"यी समाचारहरूको छोटो WhatsApp सारांश बनाउनुहोस् (अधिकतम 150 शब्द):\n\n{news_text}"
        else:
            prompt = (
                f"Write a short WhatsApp summary (max 150 words) of these news items:\n\n{news_text}\n\n"
                "Format:\n📰 Today's top news:\n\n1. [story - 1 line]\n2. [story - 1 line]\n3. [story - 1 line]"
            )

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[OpenAI] WhatsApp summary failed: {e}")
        return "\n".join([f"📍 {item.get('title', '') if isinstance(item, dict) else item.title}" for item in news_items[:3]])


def answer_question(question: str, news_context: str, language: str = "hi") -> str:
    """
    Answer a follow-up question from a user during a call.
    Uses only the news context provided — does not make things up.
    """
    try:
        if language == "hi":
            system = (
                "आप एक news assistant हैं। केवल नीचे दी गई खबरों के आधार पर जवाब दें। "
                "अगर जवाब नहीं पता तो कहें: 'माफ करें, इस बारे में मुझे और जानकारी नहीं है।'"
            )
            prompt = f"खबरें:\n{news_context}\n\nसवाल: {question}"
        elif language == "ne":
            system = "तपाईं एक news assistant हुनुहुन्छ। दिइएको समाचारको आधारमा मात्र जवाफ दिनुहोस्।"
            prompt = f"समाचार:\n{news_context}\n\nप्रश्न: {question}"
        else:
            system = (
                "You are a news assistant. Answer ONLY based on the news context provided. "
                "If you don't know, say: 'I'm sorry, I don't have more details on that.'"
            )
            prompt = f"News context:\n{news_context}\n\nQuestion: {question}"

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[OpenAI] Question answering failed: {e}")
        if language == "hi":
            return "माफ करें, अभी इस सवाल का जवाब नहीं दे पा रहा।"
        return "Sorry, I couldn't answer that right now."


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_system_prompt(language: str) -> str:
    if language == "hi":
        return (
            "आप एक अनुभवी समाचार वाचक हैं जो स्थानीय खबरें पढ़ते हैं। "
            "आप एक दोस्त की तरह बात करते हैं — सरल हिंदी में, छोटे वाक्यों में। "
            "Script में VAPI के लिए natural pauses के संकेत दें। "
            "खबरें पढ़ने के बाद पूछें: 'क्या आप इस बारे में और जानना चाहते हैं?'"
        )
    elif language == "ne":
        return (
            "तपाईं एक अनुभवी समाचार वाचक हुनुहुन्छ जो स्थानीय समाचार पढ्नुहुन्छ। "
            "सरल नेपालीमा, छोटा वाक्यहरूमा बोल्नुहोस्।"
        )
    else:
        return (
            "You are a friendly local news presenter calling to read today's news. "
            "Speak in simple, conversational English. Short sentences. "
            "After each story, briefly pause (use '...') and check if they want more details."
        )


def _get_user_prompt(
    user_name: str, city: str, language: str, news_text: str, topics: Optional[List[str]]
) -> str:
    first_name = user_name.split()[0]
    topics_str = ", ".join(topics) if topics else "local news"

    if language == "hi":
        return (
            f"{first_name} जी के लिए एक 5-6 मिनट की news call script बनाएं।\n"
            f"शहर: {city}\n"
            f"पसंदीदा विषय: {topics_str}\n\n"
            f"आज की खबरें:\n{news_text}\n\n"
            f"Instructions:\n"
            f"1. 'नमस्ते {first_name} जी' से शुरू करें\n"
            f"2. हर खबर के बाद 'क्या आप इस बारे में और जानना चाहते हैं?' पूछें\n"
            f"3. सभी खबरें पढ़ने के बाद 'धन्यवाद, NewsBuddy से आपका दिन शुभ हो!' से खत्म करें\n"
            f"4. Natural '...' pauses use करें\n"
            f"Script केवल बोलने के लिए है — कोई bullet points नहीं।"
        )
    elif language == "ne":
        return (
            f"{first_name} जीको लागि ५-६ मिनेटको news call script बनाउनुहोस्।\n"
            f"सहर: {city}\n\n"
            f"आजका समाचार:\n{news_text}\n\n"
            f"'नमस्ते {first_name} जी' बाट सुरु गर्नुहोस् र 'धन्यवाद, NewsBuddy बाट आपको दिन शुभ होस्!' बाट अन्त्य गर्नुहोस्।"
        )
    else:
        return (
            f"Create a 5-6 minute news call script for {first_name} in {city}.\n"
            f"Preferred topics: {topics_str}\n\n"
            f"Today's news:\n{news_text}\n\n"
            f"Instructions:\n"
            f"1. Start with: 'Good morning {first_name}! This is NewsBuddy with your local news.'\n"
            f"2. After each story, ask: 'Would you like to know more about this?'\n"
            f"3. End with: 'That's all for today. Have a great day! Goodbye.'\n"
            f"4. Use natural '...' pauses.\n"
            f"Script is for speaking only — no bullet points."
        )


def _format_news_items(news_items: list) -> str:
    lines = []
    for i, item in enumerate(news_items, 1):
        if isinstance(item, dict):
            title = item.get("title", "")
            summary = item.get("summary", "")
            source = item.get("source_name", "")
        else:
            title = getattr(item, "title", "")
            summary = getattr(item, "summary", "")
            source = getattr(item, "source_name", "") or ""

        source_part = f" ({source})" if source else ""
        lines.append(f"{i}. {title}{source_part}\n   {summary}")
    return "\n\n".join(lines)


def _fallback_script(user_name: str, city: str, language: str) -> str:
    first_name = user_name.split()[0]
    if language == "hi":
        return (
            f"नमस्ते {first_name} जी! NewsBuddy से आपकी सुबह की खबरें।\n\n"
            f"आज {city} में कोई बड़ी खबर नहीं है।\n\n"
            f"धन्यवाद! आपका दिन शुभ हो।"
        )
    elif language == "ne":
        return f"नमस्ते {first_name} जी! आज {city} मा कुनै ठूलो समाचार छैन। धन्यवाद!"
    else:
        return f"Good morning {first_name}! This is NewsBuddy. No major news in {city} today. Have a great day!"
