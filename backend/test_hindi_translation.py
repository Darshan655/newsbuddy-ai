"""
Visual + audio check for the Hindi pipeline (translate_service + tts_service).

1. Translates realistic NewsBuddy-style sentences and one full assembled
   script to Hindi and prints English/Hindi pairs for human verification.
2. Feeds the full Hindi script to text_to_speech(language="hi") and checks the
   resulting .mp3 is real audio (MPEG/ID3 header, non-trivial size). Listen to
   test_hindi_output.mp3 afterwards to judge the Hindi voice (gitignored).
3. Confirms the Nepali stub still raises NotImplementedError (→ English
   fallback in template_script_service).

No API key needed.

Usage:
    cd backend
    python test_hindi_translation.py
"""
import os
import sys

# Make sure we can import app modules
sys.path.insert(0, os.path.dirname(__file__))

from app.services.translate_service import translate_text
from app.services.tts_service import text_to_speech

# Realistic samples in the exact shape template_script_service produces.
SAMPLES = [
    # Single story line, source attributed up front
    "Leading today's news, according to India Today, heavy rainfall has "
    "disrupted traffic on the Nainital highway, and travellers are advised "
    "to take alternate routes.",
    # Single story line, source attributed at the end
    "In other news, the municipal corporation has approved a new drinking "
    "water project for Nepalgunj, Kathmandu Post reports.",
    # Full assembled script — the real production case: greeting, one story,
    # sign-off, translated as ONE block.
    (
        "Good morning, Darshan! This is NewsBuddy with your local news for "
        "Uttarakhand.\n\n"
        "First up, according to Hindustan Times, the state government has "
        "announced free bus travel for women on all state-run buses starting "
        "next month.\n\n"
        "That's all for now, Darshan. Thanks for listening, and have a great day!"
    ),
]


def main() -> None:
    # Windows consoles sometimes default to a legacy code page that can't
    # print Devanagari; force UTF-8 output so the Hindi is visible.
    sys.stdout.reconfigure(encoding="utf-8")

    translations = []
    for i, english in enumerate(SAMPLES, start=1):
        print("=" * 72)
        print(f"SAMPLE {i} — ENGLISH")
        print(english)
        print(f"\nSAMPLE {i} — HINDI")
        hindi = translate_text(english, "hi")
        translations.append(hindi)
        print(hindi)
        print()

    print("=" * 72)
    print("GTTS AUDIO CHECK — full Hindi script -> MP3")
    full_hindi_script = translations[-1]  # SAMPLES[-1] is the assembled script
    mp3_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "test_hindi_output.mp3")
    text_to_speech(full_hindi_script, mp3_path, language="hi")

    size = os.path.getsize(mp3_path)
    with open(mp3_path, "rb") as f:
        head = f.read(3)
    # Real MP3s start with an ID3v2 tag or an MPEG frame sync (0xFF, then the
    # top 3 bits of the next byte set).
    is_mp3 = head[:3] == b"ID3" or (
        len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    )
    if not is_mp3:
        print(f"FAIL: {mp3_path} does not start with an MPEG/ID3 header: {head!r}")
        sys.exit(1)
    if size < 10_000:
        print(f"FAIL: {mp3_path} is suspiciously small ({size} bytes) — "
              f"probably not a full spoken script")
        sys.exit(1)
    print(f"OK: wrote {mp3_path}")
    print(f"OK: valid MPEG audio (header {head!r}), {size:,} bytes")
    print("--> Listen to it to verify the Hindi pronunciation.")
    print()

    print("=" * 72)
    print("NEPALI STUB CHECK")
    try:
        translate_text("Good morning!", "ne")
        print("UNEXPECTED: 'ne' did not raise — stub is broken!")
    except NotImplementedError as e:
        print(f"OK: 'ne' raised NotImplementedError as expected ({e})")


if __name__ == "__main__":
    main()
