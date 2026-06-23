"""
template_script_service.py

Builds a natural-sounding spoken news script from a list of NewsArticle objects
WITHOUT calling any AI API. Uses string templates plus randomized phrase
variation so repeated calls don't sound identical/robotic when read aloud by
VAPI/TTS.

This is the zero-cost, offline path (no OpenAI key required) -- useful for local
development, as an outage/rate-limit fallback, and for keeping per-call cost at
zero. For the AI-generated equivalent, see openai_service.generate_script.

Design note: we only ever speak what's already in each article's .snippet (or
.title as a fallback). The templates add conversational scaffolding -- greeting,
transitions, source attribution, sign-off -- but never invent news detail, since
these snippets are headline-grade and fabricated specifics would be inaccurate.

Usage:
    from app.services.template_script_service import generate_template_script

    script = generate_template_script(articles, "Darshan", "Uttarakhand", "en")
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import for type hints only; never executed at runtime
    from app.services.news_fetch_service import NewsArticle


# ── Phrase banks (randomized so repeat calls don't sound identical) ─────────────

_INTRO_TEMPLATES = [
    "{tod}, {name}! This is NewsBuddy with your local news for {location}.",
    "{tod}, {name}! Here's your news update for {location}.",
    "{tod}, {name}! Let's catch you up on what's happening around {location}.",
    "{tod}, {name}! NewsBuddy here with today's headlines from {location}.",
]

# Lead-in for the very first story (a transition like "In other news" would be
# wrong as an opener).
_FIRST_LEADS = [
    "Leading today's news,",
    "First up,",
    "Starting with the latest,",
    "Here's what's making news,",
    "Top of the headlines,",
]

# Transitions for every story after the first.
_TRANSITIONS = [
    "In other news,",
    "Meanwhile,",
    "Also today,",
    "Moving on,",
    "On another note,",
    "Turning to other headlines,",
    "Next up,",
]

# Source attribution, used either before the content ("according to X, ...") or
# after it ("..., X reports").
_SOURCE_PREFIXES = [
    "according to {source}",
    "as {source} reports",
    "per {source}",
]
_SOURCE_SUFFIXES = [
    "{source} reports",
    "according to {source}",
    "as reported by {source}",
    "{source} says",
]

_NO_NEWS_LINES = [
    "It's been quiet in {location} today, with no major news to report right now.",
    "There's nothing major to report for {location} today. It's been a calm news day.",
    "Looks like a slow news day in {location}, with no big headlines for you this time.",
]

_CLOSINGS = [
    "That's all for now, {name}. Thanks for listening, and have a great day!",
    "And that's your update, {name}. Thanks for tuning in. Take care!",
    "That wraps up today's headlines, {name}. Thanks for listening, and stay safe out there!",
    "That's the news for now, {name}. Thank you, and I'll talk to you next time!",
]

# Values news_fetch_service uses when it has no real source name.
_UNKNOWN_SOURCES = {"", "unknown source"}


# ── Public API ──────────────────────────────────────────────────────────────────

def generate_template_script(
    news_articles: list[NewsArticle],
    user_name: str,
    location: str,
    language: str = "en",
) -> str:
    """
    Build a spoken news script from NewsArticle objects using templates only
    (no AI call). Randomized phrasing keeps repeat calls from sounding identical.

    Args:
        news_articles: list of NewsArticle (needs .title, .source, .snippet);
                       may be empty.
        user_name: user's name; the first name is used for greeting/sign-off.
        location: place name spoken in the greeting and the no-news message.
        language: "en" is fully implemented. "hi" / "ne" are stubs for now.

    Returns:
        A ready-to-speak script string. If news_articles is empty, returns a
        friendly "no major news for <location> today" message (still greeted and
        signed off) rather than an empty/broken script.

    Raises:
        NotImplementedError: for language "hi" or "ne" (templates pending).
        ValueError: for any other unsupported language code.
    """
    if language == "en":
        return _generate_english(news_articles, user_name, location)
    if language in ("hi", "ne"):
        raise NotImplementedError(
            "Hindi/Nepali templates pending - see template_script_service.py"
        )
    raise ValueError(f"Unsupported language: {language!r}")


# ── English builder ─────────────────────────────────────────────────────────────

def _generate_english(news_articles: list[NewsArticle], user_name: str, location: str) -> str:
    intro = _intro_en(user_name, location)
    closing = _closing_en(user_name)

    if not news_articles:
        no_news = random.choice(_NO_NEWS_LINES).format(location=location)
        return f"{intro}\n\n{no_news}\n\n{closing}"

    blocks = [intro]
    for i, article in enumerate(news_articles):
        story = _render_story_en(article, is_first=(i == 0))
        if story:  # skip any article with no speakable text
            blocks.append(story)
    blocks.append(closing)
    return "\n\n".join(blocks)


def _intro_en(user_name: str, location: str) -> str:
    return random.choice(_INTRO_TEMPLATES).format(
        tod=_time_of_day_greeting(), name=_first_name(user_name), location=location
    )


def _closing_en(user_name: str) -> str:
    return random.choice(_CLOSINGS).format(name=_first_name(user_name))


def _render_story_en(article: NewsArticle, is_first: bool) -> str:
    source = (getattr(article, "source", "") or "").strip()
    has_source = source.lower() not in _UNKNOWN_SOURCES

    # Speak the snippet (headline-grade), falling back to the title if it's
    # empty. We never add detail beyond this -- only conversational framing.
    content = _clean_snippet(getattr(article, "snippet", ""), source)
    if not content:
        content = (getattr(article, "title", "") or "").strip().rstrip(" .")
    if not content:
        return ""  # nothing speakable; skip this article silently

    lead = random.choice(_FIRST_LEADS if is_first else _TRANSITIONS)

    if has_source and random.random() < 0.5:
        src = random.choice(_SOURCE_PREFIXES).format(source=source)
        body = f"{src}, {content}."
    elif has_source:
        src = random.choice(_SOURCE_SUFFIXES).format(source=source)
        body = f"{content}, {src}."
    else:
        body = f"{content}."

    return f"{lead} {body}"


# ── Small text helpers ──────────────────────────────────────────────────────────

def _first_name(user_name: str) -> str:
    name = (user_name or "").strip()
    return name.split()[0] if name else "there"


def _time_of_day_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Hello"


def _clean_snippet(snippet: str, source: str) -> str:
    """Google News snippets usually have the source name tacked on the end
    (e.g. '...Pithoragarh India Today'). Strip a trailing source mention so we
    don't say the source twice when we attribute the story. Returns plain text
    and adds nothing of its own."""
    text = (snippet or "").strip()
    if text and source and source.lower() not in _UNKNOWN_SOURCES:
        text = re.sub(
            r"\s*[-–—|:]?\s*" + re.escape(source) + r"\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
    return text.rstrip(" .")


# ── Standalone test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run from inside the services folder:
    #   python template_script_service.py
    from news_fetch_service import fetch_news

    test_location = "Uttarakhand"
    test_topic = "accident"

    print(f"Fetching real news for '{test_location}' / '{test_topic}'...\n")
    articles = fetch_news(test_location, test_topic, max_results=5)
    print(f"Fetched {len(articles)} article(s).\n")

    script = generate_template_script(
        articles, user_name="Darshan", location=test_location, language="en"
    )
    print("=" * 72)
    print(script)
    print("=" * 72)
