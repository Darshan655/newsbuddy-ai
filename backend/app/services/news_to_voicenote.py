"""
news_to_voicenote.py

Top-level convenience layer: go straight from "location (+ topic)" to a spoken
.mp3 voice note, in one call. Stacks the two layers below it:

    news_to_script.get_news_script   -> fetch news + render a spoken script
    tts_service.text_to_speech       -> synthesize that script to an .mp3

This is the single entry point the call/WhatsApp layer can use to produce an
audio file to play or send.

Usage:
    from app.services.news_to_voicenote import generate_voice_note

    url = generate_voice_note("Uttarakhand", topic="accident", user_name="Darshan")
"""
import re
import sys
from pathlib import Path
from typing import Optional

import requests

# Make the backend root (…/backend) importable so this module works both as a
# package import (app.services.news_to_voicenote, e.g. from the API layer) and
# when run directly from the services folder (python news_to_voicenote.py).
# Unlike the sibling services, this file needs app.core.config (which has no
# bare-import equivalent), so we anchor sys.path instead of try/except imports.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import VOICENOTES_DIR, settings
from app.services.news_to_script import get_news_script
from app.services.tts_service import text_to_speech


def generate_voice_note(location: str, topic: Optional[str] = None,
                        user_name: str = "there", language: str = "en",
                        output_path: Optional[str] = None) -> str:
    """
    Build a spoken news voice note for a location and return its public URL.

    Args:
        location: place name, e.g. "Uttarakhand", "Nepalgunj".
        topic: optional narrowing keyword, e.g. "accident".
        user_name: name for the greeting/sign-off (first name is used).
        language: "en" and "hi" are live end-to-end ("hi" = Hindi script via
                  translate_service + gTTS Hindi voice). "ne" never raises:
                  Nepali translation is still stubbed, so it delivers the
                  English script in the Indian-English voice. If "hi"
                  translation fails, the English fallback script is spoken in
                  the normal Indian-English voice too: text_to_speech only
                  uses the Hindi voice when the text actually contains
                  Devanagari.
        output_path: where to write the .mp3. Defaults to
                     "<MEDIA_DIR>/voicenotes/<location>_<topic|general>.mp3",
                     anchored to settings.MEDIA_DIR (not the CWD) so it matches
                     the /voicenotes static mount. Parent dirs are auto-created.

    Returns:
        The public URL of the uploaded .mp3 (hosted on Supabase Storage).
    """
    if output_path is None:
        topic_part = _safe_filename_part(topic) if topic else "general"
        filename = f"{_safe_filename_part(location)}_{topic_part}.mp3"
        output_path = str(VOICENOTES_DIR / filename)

    script = get_news_script(location, topic, user_name, language)
    text_to_speech(script, output_path, language)

    # Host the .mp3 on Supabase Storage and return its public URL: the local file
    # under VOICENOTES_DIR is ephemeral on Railway and not publicly fetchable there
    # by Twilio. The bucket object name is the generated file's basename.
    return upload_to_supabase(output_path, Path(output_path).name)


def upload_to_supabase(file_path: str, filename: str) -> str:
    supabase_url = settings.SUPABASE_URL.rstrip("/")
    supabase_key = settings.SUPABASE_KEY

    upload_url = f"{supabase_url}/storage/v1/object/voicenotes/{filename}"
    public_url = f"{supabase_url}/storage/v1/object/public/voicenotes/{filename}"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "audio/mpeg",
        "x-upsert": "true"
    }

    print(f"[Supabase] Uploading {filename} to {upload_url}")
    response = requests.put(upload_url, data=file_bytes, headers=headers)
    print(f"[Supabase] Response: {response.status_code} — {response.text}")

    if response.status_code not in (200, 201):
        raise Exception(f"Supabase upload failed: {response.status_code} — {response.text}")

    return public_url


def _safe_filename_part(value: str) -> str:
    """Make a location/topic safe to drop into a filename: collapse whitespace
    to underscores and strip anything that isn't alphanumeric/dash/underscore
    (so a value like 'Jammu & Kashmir' or a stray '/' can't break the path)."""
    cleaned = re.sub(r"\s+", "_", (value or "").strip())
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return cleaned or "unknown"


if __name__ == "__main__":
    # Run from inside the services folder:
    #   python news_to_voicenote.py
    # Requires SUPABASE_URL / SUPABASE_KEY to be set: the .mp3 is uploaded and a
    # public Supabase Storage URL is returned (no local path).
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("End-to-end: generating a voice note for 'Uttarakhand' / 'accident'...")
    url = generate_voice_note("Uttarakhand", "accident", user_name="Darshan", language="en")
    print(f"Returned URL:  {url}")
    print(f"Public URL:    {url.startswith('https://')}")
