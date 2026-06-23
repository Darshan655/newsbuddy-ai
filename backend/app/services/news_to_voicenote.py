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

    path = generate_voice_note("Uttarakhand", topic="accident", user_name="Darshan")
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

from app.core.config import VOICENOTES_DIR
from app.services.news_to_script import get_news_script
from app.services.tts_service import text_to_speech


def generate_voice_note(location: str, topic: Optional[str] = None,
                        user_name: str = "there", language: str = "en",
                        output_path: Optional[str] = None) -> str:
    """
    Build a spoken news voice note for a location and return the .mp3 path.

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
        The path to the written .mp3 file.
    """
    if output_path is None:
        topic_part = _safe_filename_part(topic) if topic else "general"
        filename = f"{_safe_filename_part(location)}_{topic_part}.mp3"
        output_path = str(VOICENOTES_DIR / filename)

    script = get_news_script(location, topic, user_name, language)
    text_to_speech(script, output_path, language)
    return output_path


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
    import os
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("End-to-end: generating a voice note for 'Uttarakhand' / 'accident'...")
    path = generate_voice_note("Uttarakhand", "accident", user_name="Darshan", language="en")
    print(f"Returned path: {path}\n")

    # Re-verify it's a real, playable MP3 (size + magic bytes), as before.
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(4)
    is_id3 = head[:3] == b"ID3"
    is_frame = head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    kind = "ID3 tag" if is_id3 else "MPEG frame sync" if is_frame else "UNKNOWN"

    print(f"File size:     {size:,} bytes ({size / 1024:.1f} KB)")
    print(f"First 4 bytes: {head.hex()}")
    print(f"Valid MP3:     {is_id3 or is_frame}  ({kind})")
