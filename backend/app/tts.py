import os, asyncio, base64
from typing import AsyncIterator, Optional
from xml.sax.saxutils import escape
import httpx
from . import config  # noqa: F401  (ensures load_dotenv() has run)

# emotion -> (azure style, styledegree)
EMOTION_STYLES: dict[str, tuple[Optional[str], float]] = {
    "calm":     (None, 1.0),          # default voice, no express-as
    "happy":    ("cheerful", 1.3),
    "angry":    ("angry", 1.5),
    "offended": ("unfriendly", 1.2),
    "sad":      ("sad", 1.2),
    "flirty":   ("friendly", 1.3),
    "ashamed":  ("embarrassed", 1.0),
}
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MIME = "audio/mpeg"


def to_b64(audio: bytes) -> str:
    return base64.b64encode(audio).decode("utf-8")


class TTSProvider:
    def __init__(self, key: Optional[str] = None, region: Optional[str] = None, voice: Optional[str] = None):
        self.key = key or os.getenv("AZURE_SPEECH_KEY", "")
        self.region = region or os.getenv("AZURE_SPEECH_REGION", "")
        self.voice = voice or os.getenv("AZURE_TTS_VOICE", "en-US-DavisNeural")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def endpoint(self) -> str:
        return f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def build_ssml(self, text: str, emotion: str) -> str:
        style, degree = EMOTION_STYLES.get(emotion, (None, 1.0))
        escaped = escape(text)
        if style is None:
            voice_content = escaped
        else:
            voice_content = (
                f'<mstts:express-as style="{style}" styledegree="{degree}">'
                f"{escaped}</mstts:express-as>"
            )
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
            f'<voice name="{self.voice}">{voice_content}</voice></speak>'
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def synthesize(self, text: str, emotion: str = "calm") -> bytes:
        client = self._get_client()
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "charlie-calls",
        }
        body = self.build_ssml(text, emotion).encode("utf-8")
        resp = await client.post(self.endpoint, headers=headers, content=body)
        if resp.status_code != 200:
            raise RuntimeError(f"TTS HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.content

    async def synthesize_stream(
        self, sentences: AsyncIterator[str], emotion: str = "calm", lookahead: int = 2
    ) -> AsyncIterator[tuple[int, str, bytes]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=lookahead + 1)
        error: list[BaseException] = []

        async def _produce():
            seq = 0
            try:
                async for text in sentences:
                    seq += 1
                    task = asyncio.create_task(self.synthesize(text, emotion))
                    await queue.put((seq, text, task))
            except BaseException as exc:
                error.append(exc)
            finally:
                await queue.put(None)

        producer = asyncio.create_task(_produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    if error:
                        raise error[0]
                    break
                s, t, tsk = item
                audio = await tsk
                yield (s, t, audio)
        finally:
            if not producer.done():
                producer.cancel()
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item is None:
                    continue
                _, _, tsk = item
                if not tsk.done():
                    tsk.cancel()


tts = TTSProvider()


if __name__ == "__main__":
    import sys
    import time

    SYSTEM_PROMPT = (
        "You are Charlie, a 27-year-old bartender and musician from Austin. "
        "You are talking with a friend on a phone call. Answer in 1-2 short "
        "spoken sentences, casual English, no emojis, no markdown. ALWAYS "
        "start your reply with exactly one emotion tag from this list, in "
        "square brackets: [calm] [happy] [angry] [offended] [sad] [flirty] "
        "[ashamed]. Example: \"[happy] Dude, finally! I've been waiting for "
        "your call all day.\""
    )

    SCRATCH_DIR = "/tmp/claude-1000/-home-skaylet/c613694d-ff1d-46c9-9903-297bd60b46e4/scratchpad"

    async def run_all_emotions():
        os.makedirs(SCRATCH_DIR, exist_ok=True)
        text = "Dude, you seriously forgot my gig last night?"
        for emotion in EMOTION_STYLES:
            start = time.perf_counter()
            try:
                audio = await tts.synthesize(text, emotion)
            except RuntimeError as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"{emotion}  {elapsed_ms:.0f} ms  ERROR: {e}")
                continue
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"{emotion}  {elapsed_ms:.0f} ms  {len(audio)} bytes")
            with open(os.path.join(SCRATCH_DIR, f"tts_emotion_{emotion}.mp3"), "wb") as f:
                f.write(audio)
        await tts.aclose()

    async def run_default(user_text: str):
        from .llm import llm, split_sentences

        os.makedirs(SCRATCH_DIR, exist_ok=True)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        start = time.perf_counter()
        emotion_holder: dict = {}

        async def text_only():
            async for kind, value in llm.stream_turn(messages):
                if kind == "emotion":
                    emotion_holder["emotion"] = value
                else:
                    yield value

        async def sentences():
            async for sentence in split_sentences(text_only()):
                yield sentence

        chars_sent = 0
        full_audio = b""
        printed_emotion = False
        async for seq, text, audio in tts.synthesize_stream(sentences(), emotion="calm", lookahead=2):
            if not printed_emotion and "emotion" in emotion_holder:
                print(f"emotion={emotion_holder['emotion']}")
                printed_emotion = True
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"seq={seq}  {elapsed_ms:.0f} ms  {len(audio)} bytes  {text}")
            chars_sent += len(text)
            full_audio += audio
            with open(os.path.join(SCRATCH_DIR, f"tts_{seq}.mp3"), "wb") as f:
                f.write(audio)

        if not printed_emotion:
            print(f"emotion={emotion_holder.get('emotion', 'calm')}")

        with open(os.path.join(SCRATCH_DIR, "tts_full.mp3"), "wb") as f:
            f.write(full_audio)

        total_ms = (time.perf_counter() - start) * 1000
        print(f"total elapsed: {total_ms:.0f} ms")
        print(f"total chars sent to TTS: {chars_sent}")

        await tts.aclose()

    async def main():
        user_text = sys.argv[1] if len(sys.argv) > 1 else "Hey Charlie, what's up?"
        all_emotions = len(sys.argv) > 2 and sys.argv[2] == "--all-emotions"
        if all_emotions:
            await run_all_emotions()
        else:
            await run_default(user_text)

    asyncio.run(main())
