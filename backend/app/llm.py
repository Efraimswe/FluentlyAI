import os, re, json, time, asyncio
from typing import AsyncIterator, Optional
import httpx
from . import config  # noqa: F401  (ensures load_dotenv() has run)

EMOTIONS = {"calm", "happy", "angry", "offended", "sad", "flirty", "ashamed"}
DEFAULT_EMOTION = "calm"
_TAG_RE = re.compile(r"^\s*\[(\w+)\]\s*")
_SENTENCE_END_RE = re.compile(r'[.!?…]+["\')\]]*\s')
_FIRST_CUT_RE = re.compile(r'[,;—]\s*$|\s-\s*$')


class LLMProvider:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = (base_url or os.getenv("DASHSCOPE_BASE_URL", "")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "qwen3.5-27b")
        self.last_usage: Optional[dict] = None  # {"tokens_in": int, "tokens_out": int} after a stream finishes
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=60),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def stream_raw(self, messages: list[dict], temperature: float = 0.85, max_tokens: int = 200) -> AsyncIterator[str]:
        """POST {base_url}/chat/completions with stream=True, yield content deltas (non-empty strings)."""
        self.last_usage = None
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "enable_thinking": False,
            "stream_options": {"include_usage": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        client = self._get_client()
        async with client.stream(
            "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"LLM HTTP {resp.status_code}: {body[:300]}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                if not data:
                    continue
                chunk = json.loads(data)
                usage = chunk.get("usage")
                if usage is not None:
                    self.last_usage = {
                        "tokens_in": usage.get("prompt_tokens", 0),
                        "tokens_out": usage.get("completion_tokens", 0),
                    }
                choices = chunk.get("choices")
                if choices:
                    content = choices[0].get("delta", {}).get("content")
                    if content:
                        yield content

    async def stream_turn(self, messages: list[dict], **kw) -> AsyncIterator[tuple[str, str]]:
        """Yield ("emotion", <name>) exactly once first, then ("text", <delta>) for the rest."""
        buffer = ""
        emitted_emotion = False

        def resolve(buf: str):
            m = _TAG_RE.match(buf)
            if m:
                name = m.group(1).lower()
                if name in EMOTIONS:
                    return name, buf[m.end():]
                return DEFAULT_EMOTION, buf[m.end():]
            return DEFAULT_EMOTION, buf

        async for delta in self.stream_raw(messages, **kw):
            if emitted_emotion:
                yield ("text", delta)
                continue

            buffer += delta
            stripped = buffer.lstrip()
            ready = ("]" in buffer) or (stripped and not stripped.startswith("[")) or (len(buffer) > 40)
            if ready:
                emotion, remaining = resolve(buffer)
                emitted_emotion = True
                yield ("emotion", emotion)
                if remaining:
                    yield ("text", remaining)

        if not emitted_emotion:
            emotion, remaining = resolve(buffer)
            yield ("emotion", emotion)
            if remaining:
                yield ("text", remaining)


async def split_sentences(deltas: AsyncIterator[str], first_cut_words: int = 5) -> AsyncIterator[str]:
    """Module-level async generator: consume text deltas, yield complete sentences.

    For the very first emitted chunk only, also cut on a natural comma-style
    pause (`,` `;` `—` or ` - `) once the buffer has at least `first_cut_words`
    words, so TTS can start speaking before the whole sentence has arrived.
    After the first chunk, only the normal sentence-end / long-comma rules apply.
    """
    buffer = ""
    first_chunk_emitted = False
    async for delta in deltas:
        buffer += delta
        while True:
            m = _SENTENCE_END_RE.search(buffer)
            if m:
                sentence = buffer[:m.end()].strip()
                buffer = buffer[m.end():]
                if sentence:
                    first_chunk_emitted = True
                    yield sentence
                continue
            if len(buffer.split()) >= 12 and buffer.rstrip().endswith(","):
                first_chunk_emitted = True
                yield buffer.strip()
                buffer = ""
                continue
            if (
                not first_chunk_emitted
                and len(buffer.split()) >= first_cut_words
                and _FIRST_CUT_RE.search(buffer)
            ):
                first_chunk_emitted = True
                yield buffer.strip()
                buffer = ""
                continue
            break
    if buffer.strip():
        yield buffer.strip()


llm = LLMProvider()


if __name__ == "__main__":
    import sys

    SYSTEM_PROMPT = (
        "You are Charlie, a 27-year-old bartender and musician from Austin. "
        "You are talking with a friend on a phone call. Answer in 1-2 short "
        "spoken sentences, casual English, no emojis, no markdown. ALWAYS "
        "start your reply with exactly one emotion tag from this list, in "
        "square brackets: [calm] [happy] [angry] [offended] [sad] [flirty] "
        "[ashamed]. Example: \"[happy] Dude, finally! I've been waiting for "
        "your call all day.\""
    )

    async def main():
        user_text = sys.argv[1] if len(sys.argv) > 1 else "Hey Charlie, what's up?"
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
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    print(f"emotion={value}  (first token at {elapsed_ms:.0f} ms)")
                else:
                    yield value

        async for sentence in split_sentences(text_only()):
            print(f"> {sentence}")

        total_ms = (time.perf_counter() - start) * 1000
        print(f"usage={llm.last_usage}")
        print(f"total elapsed: {total_ms:.0f} ms")

    asyncio.run(main())
