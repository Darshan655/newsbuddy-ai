"""
news_to_script.py

Thin orchestration layer: fetch live local news for a location (+ optional
topic) and turn it straight into a ready-to-speak script, with no AI call.

Wires together the two building blocks:
    news_fetch_service.fetch_news        -> discovers articles (Google News RSS)
    template_script_service.generate_template_script -> renders a spoken script

This is the single entry point the call/API layer can use to go from
"location + topic" to "script string" in one call.

Usage:
    from app.services.news_to_script import get_news_script

    script = get_news_script("Uttarakhand", topic="accident", user_name="Darshan")
"""
from typing import Optional

# Works both as a package import (app.services.news_to_script, e.g. from the API
# layer) and as a script run directly from inside the services folder.
try:
    from app.services.news_fetch_service import fetch_news
    from app.services.template_script_service import generate_template_script
except ImportError:  # running standalone: python news_to_script.py
    from news_fetch_service import fetch_news
    from template_script_service import generate_template_script


def get_news_script(location: str, topic: Optional[str] = None,
                    user_name: str = "there", language: str = "en") -> str:
    """
    Fetch news for a location and return a spoken-news script string.

    Args:
        location: place name, e.g. "Uttarakhand", "Nepalgunj".
        topic: optional narrowing keyword, e.g. "accident".
        user_name: name for the greeting/sign-off (first name is used).
        language: "en" and "hi" are live ("hi" translates the assembled script
                  in one call via translate_service). "ne" falls back to the
                  English script (Nepali translation is still stubbed) rather
                  than raising.

    Returns:
        A ready-to-speak script string. fetch_news never raises (it returns []
        on any failure), generate_template_script renders a friendly
        "no major news" script for an empty list, and hi/ne fall back to the
        English script if translation is unavailable -- so this always returns
        a usable script, never an empty string or an exception, for
        "en"/"hi"/"ne".
    """
    articles = fetch_news(location, topic)
    return generate_template_script(articles, user_name, location, language)


if __name__ == "__main__":
    # Run from inside the services folder:
    #   python news_to_script.py
    import sys

    # Windows consoles often default to a non-UTF-8 code page, but regional news
    # (Hindi/Nepali text, place/person names, em-dashes, the rupee sign) is full
    # of non-ASCII. Make stdout UTF-8 so the printed script renders correctly.
    # Display-only: the returned string is already correct Unicode either way.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    # Two real locations: one with a topic, one without (and likely thinner
    # coverage) to see how the empty/thin-news path behaves against live data.
    demos = [
        ("Uttarakhand", "accident"),
        ("Nepalgunj", None),
    ]

    for location, topic in demos:
        topic_label = f"topic='{topic}'" if topic else "no topic"
        print("#" * 72)
        print(f"# {location}  ({topic_label})")
        print("#" * 72)
        script = get_news_script(location, topic, user_name="Darshan", language="en")
        print(script)
        print()
