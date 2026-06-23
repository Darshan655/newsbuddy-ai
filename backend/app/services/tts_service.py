"""
tts_service.py

Text-to-speech using edge-tts -- Microsoft Edge's online neural TTS engine.
Free, no API key, good-quality natural voices. We use it to turn a generated
news script into an .mp3 the call layer can play (e.g. via VAPI/Twilio).

edge-tts is async under the hood (it streams audio over a WebSocket); the public
text_to_speech() wraps that in asyncio.run so callers get a simple synchronous
function that returns the output path.

Usage:
    from app.services.tts_service import text_to_speech

    path = text_to_speech("Good morning!", "out.mp3", language="en")
"""
import asyncio
import os

import edge_tts


# A natural Indian-English voice -- fits a NewsBuddy serving India/Nepal far
# better than US English on local place/person names. edge-tts ships many
# alternatives (e.g. en-US-AriaNeural, en-IN-PrabhatNeural) if you want to change it.
_DEFAULT_VOICE = "en-IN-NeerjaNeural"

# Voice per language. Hindi/Nepali are placeholders pointing at the English
# voice for now; real voices (e.g. hi-IN-SwaraNeural, ne-NP-HemkalaNeural) come
# later, once script phrasing is tuned per language.
_VOICE_BY_LANGUAGE = {
    "en": _DEFAULT_VOICE,
    "hi": _DEFAULT_VOICE,  # placeholder until a Hindi voice is chosen
    "ne": _DEFAULT_VOICE,  # placeholder until a Nepali voice is chosen
}


def text_to_speech(text: str, output_path: str, language: str = "en") -> str:
    """
    Convert text to an .mp3 audio file and return the output path.

    Args:
        text: the text to speak (e.g. a generated news script).
        output_path: where to write the .mp3 (parent directories are created).
        language: "en" uses a natural English voice. "hi"/"ne" are stubbed to
                  the same English voice for now (placeholder).

    Returns:
        output_path -- the file that was written.

    Raises:
        ValueError: if text is empty or whitespace-only.
    """
    if not text or not text.strip():
        raise ValueError("text_to_speech: 'text' is empty; nothing to synthesize.")

    voice = _VOICE_BY_LANGUAGE.get(language, _DEFAULT_VOICE)

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    asyncio.run(_synthesize_to_file(text, output_path, voice))
    return output_path


async def _synthesize_to_file(text: str, output_path: str, voice: str) -> None:
    """Stream edge-tts audio for `text` in `voice` and save it to `output_path`.
    Kept separate so it can also be awaited directly from async code later."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


if __name__ == "__main__":
    # Run from inside the services folder:
    #   python tts_service.py
    import sys

    # UTF-8 stdout so non-ASCII in the script (names, dashes, future hi/ne text)
    # prints correctly on Windows consoles.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    from news_to_script import get_news_script

    print("Generating script for 'Uttarakhand' / 'accident'...\n")
    script = get_news_script("Uttarakhand", "accident", user_name="Darshan", language="en")
    print(script)
    print(f"\n[script: {len(script)} characters]\n")

    output_file = "test_output.mp3"
    print(f"Converting to speech with edge-tts -> {output_file} ...")
    text_to_speech(script, output_file, language="en")

    size = os.path.getsize(output_file)
    print(f"Done. Wrote {output_file} ({size:,} bytes, {size / 1024:.1f} KB).")
