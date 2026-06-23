"""
news_fetch_service.py

Fetches local news for any location + topic combination using Google News RSS
as the discovery source (free, no API key, works for any place name).

Returns each article's headline, source, publish time, and a cleaned snippet
(HTML stripped down to plain prose) ready to pass straight to an AI summarizer.
Snippet-only by design for the MVP: we don't fetch full article bodies, because
Google News article links resolve client-side (no real URL in the page) and
aren't worth the latency/fragility right now.

Usage:
    from news_fetch_service import fetch_news

    articles = fetch_news(location="Uttarakhand", topic="accident", max_results=5)
"""

import re
import urllib.parse
import logging
from dataclasses import dataclass
from html import unescape
from typing import Optional

import feedparser
import requests

logger = logging.getLogger(__name__)

# Looking like a normal browser avoids being blocked by Google or news sites.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT_SECONDS = 8


@dataclass
class NewsArticle:
    title: str
    link: str
    source: str
    published: Optional[str] = None
    snippet: str = ""

    @property
    def best_available_text(self) -> str:
        """The title + snippet (already HTML-cleaned) that RSS gave us.
        This is what should get passed to the AI summarizer."""
        return f"{self.title}. {self.snippet}".strip()


def _strip_html(raw_html: str) -> str:
    """Crudely turn an HTML fragment into plain text: decode HTML entities,
    drop <script>/<style> blocks, strip remaining tags, and collapse
    whitespace. Used to clean the HTML Google News puts in RSS snippets so
    they're always clean prose, never markup."""
    text = unescape(raw_html)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_rss_url(location: str, topic: Optional[str] = None,
                    country_code: str = "IN", lang_code: str = "en") -> str:
    """Builds a Google News RSS search URL for a location, optionally
    narrowed by topic. country_code/lang_code control regional relevance
    (e.g. IN for India editions, NP doesn't exist in Google News editions,
    so Nepal queries should still use IN or a neutral edition)."""
    query = location if not topic else f"{location} {topic}"
    encoded_query = urllib.parse.quote(query)
    return (
        f"https://news.google.com/rss/search?q={encoded_query}"
        f"&hl={lang_code}-{country_code}&gl={country_code}&ceid={country_code}:{lang_code}"
    )


def fetch_news(location: str, topic: Optional[str] = None, max_results: int = 5,
               country_code: str = "IN", lang_code: str = "en") -> list[NewsArticle]:
    """
    Main entry point. Fetches recent news for a location (+ optional topic).

    Args:
        location: any place name, e.g. "Uttarakhand", "Nepalgunj", "Gorakhpur"
        topic: optional narrowing keyword, e.g. "accident", "mandi prices"
        max_results: how many articles to return total
        country_code: Google News edition, e.g. "IN" for India
        lang_code: language code, e.g. "en" or "hi"

    Returns:
        List of NewsArticle, ordered as returned by Google News (most
        relevant/recent first). Empty list if nothing found or fetch fails
        entirely -- callers should handle the empty-list case (e.g. "no
        news found for this area today").
    """
    rss_url = _build_rss_url(location, topic, country_code, lang_code)

    try:
        resp = requests.get(rss_url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"RSS fetch failed for location='{location}' topic='{topic}': {exc}")
        return []

    feed = feedparser.parse(resp.text)
    if not feed.entries:
        logger.info(f"No news found for location='{location}' topic='{topic}'")
        return []

    articles: list[NewsArticle] = []
    for entry in feed.entries[:max_results]:
        source_name = entry.source.title if hasattr(entry, "source") else "Unknown source"
        articles.append(NewsArticle(
            title=entry.get("title", "").strip(),
            link=entry.get("link", ""),
            source=source_name,
            published=entry.get("published"),
            snippet=_strip_html(entry.get("summary", "")),
        ))

    return articles


if __name__ == "__main__":
    # Quick manual test when run directly: python news_fetch_service.py
    import sys
    logging.basicConfig(level=logging.INFO)

    test_location = sys.argv[1] if len(sys.argv) > 1 else "Uttarakhand"
    test_topic = sys.argv[2] if len(sys.argv) > 2 else "accident"

    print(f"Fetching news for location='{test_location}' topic='{test_topic}'...\n")
    results = fetch_news(test_location, test_topic, max_results=5)

    if not results:
        print("No results found.")
    for i, art in enumerate(results, 1):
        print(f"{i}. {art.title}")
        print(f"   Source: {art.source} | Published: {art.published}")
        print(f"   Link: {art.link}")
        print(f"   Snippet: {art.snippet[:200]}")
        print(f"   Text preview: {art.best_available_text[:200]}...")
        print()
