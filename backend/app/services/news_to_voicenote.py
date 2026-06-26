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
        language: "en" is implemented; "hi"/"ne" raise NotImplementedError.
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
    """
    Upload a generated .mp3 to the public "voicenotes" Supabase Storage bucket and
    return its public URL.

    Reads the file at `file_path` as bytes and uploads it as `filename` with upsert
    enabled, so a retried or re-run delivery overwrites the existing object instead
    of failing on a duplicate. Credentials come from settings.SUPABASE_URL and
    settings.SUPABASE_KEY.

    Returns:
        The object's public URL, e.g.
        "https://<project>.supabase.co/storage/v1/object/public/voicenotes/<filename>".
    """
    # Imported lazily so importing this module from the API/worker layers doesn't
    # hard-require the supabase package until an upload actually runs.
    from supabase import create_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise RuntimeError(
            "Supabase storage is not configured: set SUPABASE_URL and SUPABASE_KEY."
        )

    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    bucket = client.storage.from_("voicenotes")
    # file_options values must be strings; "x-upsert" overwrites on name conflict.
    bucket.upload(
        path=filename,
        file=audio_bytes,
        file_options={"content-type": "audio/mpeg", "x-upsert": "true"},
    )

    # storage3's get_public_url appends a trailing "?" (empty query); strip it so
    # the URL handed to Twilio is clean.
    return bucket.get_public_url(filename).rstrip("?")


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
