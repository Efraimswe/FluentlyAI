"""
Synthesize a test phrase as raw 16 kHz 16-bit mono PCM for the Deepgram
streaming test.

Run with:
    cd backend && .venv/bin/python scripts/make_pcm.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.tts as t

t.OUTPUT_FORMAT = "raw-16khz-16bit-mono-pcm"

OUT_PATH = "/tmp/claude-1000/-home-skaylet/c613694d-ff1d-46c9-9903-297bd60b46e4/scratchpad/speech16k.pcm"


async def main():
    audio = await t.tts.synthesize(
        "Hey Charlie, I just got promoted at work and I want to celebrate this Friday.",
        "happy",
    )
    with open(OUT_PATH, "wb") as f:
        f.write(audio)
    print(f"{len(audio)} bytes")
    print(f"duration: {len(audio) / 32000:.2f} s")
    await t.tts.aclose()


if __name__ == "__main__":
    asyncio.run(main())
