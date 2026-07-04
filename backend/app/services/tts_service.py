"""
tts_service.py

Text-to-speech using gTTS (Google Text-to-Speech). Free, no API key, and -- unlike
edge-tts -- it works reliably from cloud servers: edge-tts's Microsoft endpoint
returns HTTP 403 from many cloud IPs (e.g. Railway), which broke audio generation
in production. We use it to turn a generated news script into an .mp3 the
call/WhatsApp layer can play or send.

"hi" scripts (real Hindi text since translate_service switched to
deep-translator) are synthesized with gTTS's Hindi voice. Everything else --
"en", and "ne" while Nepali translation is still stubbed to English text --
uses Google's `co.in` TLD so English is spoken with an Indian accent, which
fits a NewsBuddy serving India/Nepal far better than US English on local
place/person names.

Usage:
    from app.services.tts_service import text_to_speech

    path = text_to_speech("Good morning!", "out.mp3", language="en")
    path = text_to_speech("सुप्रभात!", "out.mp3", language="hi")
"""
import os

from gtts import gTTS


def text_to_speech(text: str, output_path: str, language: str = "en") -> str:
    """
    Convert text to an .mp3 audio file and return the output path.

    Args:
        text: the text to speak (e.g. a generated news script).
        output_path: where to write the .mp3 (parent directories are created).
        language: "hi" synthesizes with gTTS's Hindi voice. Everything else
                  ("en", plus "ne" and unknown codes) synthesizes Indian-accent
                  English (lang="en", tld="co.in"): Nepali scripts still fall
                  back to English text at the translation layer, so a Nepali
                  voice branch would have nothing to feed it yet.

    Returns:
        output_path -- the file that was written.

    Raises:
        ValueError: if text is empty or whitespace-only.
    """
    if not text or not text.strip():
        raise ValueError("text_to_speech: 'text' is empty; nothing to synthesize.")

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # gTTS is synchronous (no asyncio needed, unlike edge-tts).
    # Callers pass user.language, which may be a LanguageEnum member rather
    # than a plain string; it's a str subclass with value "hi"/"ne"/"en", so
    # this comparison matches both forms.
    if language == "hi":
        tts = gTTS(text=text, lang="hi")
    else:
        # tld="co.in" selects Google's Indian-English accent.
        tts = gTTS(text=text, lang="en", tld="co.in")
    tts.save(output_path)
    return output_path


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
    print(f"Converting to speech with gTTS -> {output_file} ...")
    text_to_speech(script, output_file, language="en")

    size = os.path.getsize(output_file)
    print(f"Done. Wrote {output_file} ({size:,} bytes, {size / 1024:.1f} KB).")
