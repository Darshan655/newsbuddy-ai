"""
translate_service.py

Renders the English template script in Hindi ("hi") with a single translation
call per script (full-context translation reads far more naturally than
translating phrase banks fragment-by-fragment).

Current backend: the free `deep-translator` library, which drives Google
Translate's public web endpoint. Chosen because it needs no API key and no
billing card — the official Google Cloud Translation API requires billing to
be enabled, and GOOGLE_TRANSLATE_API_KEY billing isn't set up yet. The
original Cloud Translation client is kept intact (unused) at the bottom of
this file so we can switch back once billing exists.

Nepali ("ne") is deliberately still a stub: it raises NotImplementedError,
which template_script_service catches like any other failure and serves the
English script instead.

This module never falls back silently: any failure (network error, rate
limit, blocked endpoint, malformed/empty response) raises so the caller
decides what to do -- template_script_service catches it and serves the
English script instead.

Usage:
    from app.services.translate_service import translate_text, TranslationError

    hindi = translate_text("Good morning, Darshan!", "hi")
"""
from __future__ import annotations

import html
import os

import requests

# Why deep-translator: free Google Translate via the public web endpoint — no
# API key, no billing card required. Known risk: it's an UNOFFICIAL endpoint,
# so Google may rate-limit or block it outright on cloud/datacenter IPs like
# Railway (the same failure pattern that broke edge-tts on June 28: worked
# locally, HTTP 403 in production). If that happens, every call below raises
# TranslationError and users transparently get the English script. Caveats:
# v1.11.4 sends the request with no timeout (a hung connection can block the
# worker), and the web endpoint caps requests at ~5000 chars (a NewsBuddy
# script is well under; an oversized one raises and falls back like any other
# failure).
from deep_translator import GoogleTranslator


class TranslationError(RuntimeError):
    """The translation backend could not return a usable translation."""


def translate_text(text: str, target_lang: str) -> str:
    """
    Translate English text to target_lang ("hi" or "ne") in one call.

    "hi" is translated with deep-translator's GoogleTranslator (free web
    endpoint). "ne" is a deliberate stub until a Nepali backend is wired up.

    Returns:
        The translated plain text.

    Raises:
        NotImplementedError: for "ne" — deliberate stub; the caller falls
            back to the English script.
        TranslationError: on any Hindi translation failure (network error,
            rate limit, blocked endpoint, empty/malformed response) or an
            unsupported language code. Never returns partial/bad data.
    """
    if target_lang == "ne":
        # Deliberate stub: Nepali stays on the English fallback until we pick
        # and verify a Nepali backend. template_script_service catches this
        # and serves the English script.
        raise NotImplementedError("Nepali translation is not implemented yet")
    if target_lang != "hi":
        raise TranslationError(f"Unsupported target language: {target_lang!r}")
    if not text.strip():
        return text  # nothing to translate; skip a pointless network call

    try:
        # One request for the whole assembled script (better grammar than
        # fragment-by-fragment). ANY failure — network error, rate limit,
        # endpoint change/block — is logged and re-raised so the caller falls
        # back to the English script, exactly like the old Cloud API path.
        translated = GoogleTranslator(source="en", target="hi").translate(text)
    except Exception as e:
        print(f"[Translate] ERROR: hi translation via deep-translator failed: {e}")
        raise TranslationError(f"deep-translator request failed: {e}") from e

    if not translated or not translated.strip():
        print("[Translate] ERROR: deep-translator returned an empty translation")
        raise TranslationError("deep-translator returned an empty translation")

    # Positive signal for production log checks (Railway): success is
    # otherwise silent, which makes "is Hindi actually working?" unanswerable
    # from logs alone.
    print(f"[Translate] OK: en->hi via deep-translator "
          f"({len(text)} -> {len(translated)} chars)")

    # Defensive: unescape so a stray HTML entity (&#39; etc.) can never reach
    # the TTS engine.
    return html.unescape(translated)


# ── UNUSED: original Google Cloud Translation API v2 client ─────────────────────
#
# Kept intact so we can switch back once GOOGLE_TRANSLATE_API_KEY billing is
# set up: point the "hi"/"ne" paths in translate_text at
# _translate_via_google_cloud_api and delete the deep-translator path. Auth is
# an API key sent in the X-goog-api-key header rather than the URL query
# string so it can never leak into exception messages or request logs.
# Not called anywhere as of 2026-07-04.

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
_TIMEOUT_SECONDS = 20


def _get_api_key() -> str:
    # Settings first (project convention; reads .env), plain env var as the
    # fallback so the module also works in standalone script runs where the
    # app package isn't importable.
    try:
        from app.core.config import settings
        key = settings.GOOGLE_TRANSLATE_API_KEY
    except ImportError:
        key = ""
    return key or os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")


def _translate_via_google_cloud_api(text: str, target_lang: str) -> str:
    """
    UNUSED — original paid path. Translate English text to target_lang ("hi"
    or "ne") via Google Cloud Translation v2 in one request.

    Returns:
        The translated plain text.

    Raises:
        TranslationError: on a missing API key, network failure, non-200
        API response, or a response without a usable translation. Never
        returns partial/bad data.
    """
    key = _get_api_key()
    if not key:
        raise TranslationError("GOOGLE_TRANSLATE_API_KEY is not set — cannot translate")
    if not text.strip():
        return text  # nothing to translate; skip a pointless billable call

    try:
        resp = requests.post(
            _TRANSLATE_URL,
            headers={"X-goog-api-key": key},
            data={
                "q": text,
                "source": "en",
                "target": target_lang,
                "format": "text",  # plain text in/out (no HTML entity escaping)
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise TranslationError(f"Translation request failed: {e}") from e

    if resp.status_code != 200:
        # Google puts a readable reason in the JSON error body -- surface it.
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise TranslationError(f"Translation API returned HTTP {resp.status_code}: {detail}")

    try:
        translated = resp.json()["data"]["translations"][0]["translatedText"]
    except (ValueError, KeyError, IndexError) as e:
        raise TranslationError(f"Unexpected translation response shape: {e}") from e

    if not translated.strip():
        raise TranslationError("Translation API returned an empty translation")

    # format=text responses are already plain text; unescape defensively so a
    # stray HTML entity (&#39; etc.) can never reach the TTS engine.
    return html.unescape(translated)


# ── Standalone test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run from inside the services folder (no API key needed):
    #   python translate_service.py
    sample = "Good morning, Darshan! This is NewsBuddy with your local news for Nepalgunj."
    print("--- hi (deep-translator) ---")
    print(translate_text(sample, "hi"))
    print("--- ne (stub) ---")
    try:
        translate_text(sample, "ne")
    except NotImplementedError as e:
        print(f"NotImplementedError as expected: {e}")
