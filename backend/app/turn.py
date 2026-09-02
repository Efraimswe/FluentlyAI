import asyncio, json, random, time
from pathlib import Path
from typing import AsyncIterator, Optional
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from .llm import llm, split_sentences, DEFAULT_EMOTION
from .tts import tts, to_b64, MIME
from .auth import get_user_id
from .state import CharlieState, load_state, load_memories, pick_day_event, start_mood, build_state_block
from .usage import record_turn
from .limits import check_rate, call_too_long, get_limit_info, increment_usage
from .db import db

router = APIRouter()

LLM_FIRST_TOKEN_TIMEOUT_S = 8.0
HISTORY_MAX = 16

_PROMPTS = Path(__file__).parent / "prompts"


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = _read("charlie_system.md")
_GREETING_TEMPLATE = _read("greeting.md")


def _load_day_events() -> list[tuple[str, str]]:
    out = []
    for line in _read("day_events.md").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        emotion, text = line.split("|", 1)
        out.append((emotion.strip(), text.strip()))
    return out


DAY_EVENTS = _load_day_events()


def greeting_instruction(day_event: Optional[str] = None) -> str:
    if day_event is None:
        day_event = random.choice(DAY_EVENTS)[1]
    return _GREETING_TEMPLATE.replace("{day_event}", day_event)

# 15 fallback phrases (text, emotion) — spoken when the LLM does not answer in time; each asks the user to repeat / stalls naturally
FALLBACK_PHRASES: list[tuple[str, str]] = [
    ("Hold on, the line just cut out for a sec. Say that again?", "calm"),
    ("Sorry man, you broke up there. What was that?", "calm"),
    ("Wait, I lost you for a second. Run that by me again?", "calm"),
    ("Ugh, my phone's acting up. What did you say?", "offended"),
    ("Hang on, someone's yelling at the bar. Okay, go on, what were you saying?", "calm"),
    ("Dude, this signal is garbage tonight. One more time?", "angry"),
    ("Hmm? Sorry, zoned out for a second. Say it again?", "ashamed"),
    ("Hold that thought, my speaker's glitching. Again?", "calm"),
    ("You're cutting out on me. What was the last part?", "calm"),
    ("Wait wait, missed that completely. Say again?", "happy"),
    ("Okay my phone hates me today. What'd you say?", "sad"),
    ("Sorry, some guy just dropped a whole tray of glasses. What were you saying?", "calm"),
    ("Damn, I didn't catch that. Once more?", "calm"),
    ("Hey, you still there? Say that again, it got weird for a sec.", "calm"),
    ("Line's being dumb. Repeat that for me?", "calm"),
]

# in-memory per-call history (level 3 only; Supabase comes in level 4)
_HISTORY: dict[str, list[dict]] = {}
# last assistant reply per call, as the list of sentences actually sent (for spoken_upto trimming)
_LAST_REPLY: dict[str, list[str]] = {}
# per-call state entry: {"user_id", "is_guest", "day_event", "state", "mood", "mood_level", "memories"}
_CALLS: dict[str, dict] = {}


async def prepare_call(call_id: str, user_id: Optional[str]) -> dict:
    is_guest = user_id is None
    try:
        if is_guest:
            state = CharlieState()
            memories: list[dict] = []
            day_event = await pick_day_event(None)
        else:
            state = await load_state(user_id)
            memories = await load_memories(user_id)
            day_event = await pick_day_event(user_id)
    except Exception as exc:
        print(f"[state] db unavailable: {exc!r}")
        state = CharlieState()
        memories = []
        emotion, text = random.choice(DAY_EVENTS)
        day_event = {"id": None, "text": text, "mood_effect": emotion}

    mood, mood_level = start_mood(state, day_event)
    entry = {
        "user_id": user_id,
        "is_guest": is_guest,
        "day_event": day_event,
        "state": state,
        "mood": mood,
        "mood_level": mood_level,
        "memories": memories,
        "started_at": time.time(),
    }
    _CALLS[call_id] = entry
    return entry


class TurnRequest(BaseModel):
    text: str = ""
    call_id: str = "local"
    spoken_upto: Optional[int] = None   # number of audio chunks (seq) that fully played before the user interrupted
    stt_sec: float = 0.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/turn")
async def turn(
    req: TurnRequest,
    authorization: Optional[str] = Header(default=None),
    x_fingerprint: Optional[str] = Header(default=None),
    x_timezone: Optional[str] = Header(default=None),
):
    call_id = req.call_id

    async def stream():
        # 1. spoken_upto trimming
        if req.spoken_upto is not None and _LAST_REPLY.get(call_id):
            last_reply = _LAST_REPLY[call_id]
            kept = last_reply[: req.spoken_upto]
            history = _HISTORY.get(call_id, [])
            # find the last assistant entry
            for i in range(len(history) - 1, -1, -1):
                if history[i]["role"] == "assistant":
                    if kept:
                        history[i]["content"] = " ".join(kept)
                    else:
                        del history[i]
                    break
            _LAST_REPLY.pop(call_id, None)

        # 2. build messages
        history = _HISTORY.setdefault(call_id, [])
        text = req.text.strip()
        is_greeting = not text
        system = {"role": "system", "content": SYSTEM_PROMPT}

        entry = _CALLS.get(call_id)
        if entry is None:
            user_id = await get_user_id(authorization)
            entry = await prepare_call(call_id, user_id)
            entry["fingerprint"] = x_fingerprint
            entry["tz"] = x_timezone

        if not is_greeting:
            history.append({"role": "user", "content": text})
            del history[:-HISTORY_MAX]

        # 2b. rate limit / call length / message limit checks
        if not check_rate(call_id):
            yield _sse("error", {"code": "rate_limit"})
            return

        def _pop_user_message() -> None:
            if not is_greeting and history and history[-1]["role"] == "user":
                history.pop()

        fallback_status = entry.get("status") or ("guest" if entry["is_guest"] else "registered")

        if call_too_long(entry["started_at"]):
            _pop_user_message()
            yield _sse("limit", {"left": 0, "status": fallback_status, "reason": "call_length"})
            yield _sse("done", {"usage": {"tokens_in": 0, "tokens_out": 0, "tts_chars": 0}})
            return

        is_last_reply = False
        extra_rules: Optional[list[str]] = None

        if not is_greeting:
            info = await get_limit_info(entry["user_id"], entry.get("fingerprint"), entry.get("tz"))
            entry["status"] = info.status
            if info.left <= 0:
                _pop_user_message()
                yield _sse("limit", {"left": 0, "status": info.status, "reason": info.reason or "limit"})
                yield _sse("done", {"usage": {"tokens_in": 0, "tokens_out": 0, "tts_chars": 0}})
                return
            if info.left == 1:
                extra_rules = ["guest_last_reply"] if entry["is_guest"] else ["limit_last_reply"]
                is_last_reply = True

        block = build_state_block(
            entry["state"], entry["memories"], entry["day_event"], entry["is_guest"],
            entry["mood"], entry["mood_level"], extra_rules,
        )
        state_msg = {"role": "system", "content": block}

        if is_greeting:
            messages = [system, state_msg, {"role": "user", "content": greeting_instruction(entry["day_event"]["text"])}]
        else:
            messages = [system] + history[:-1] + [state_msg] + [history[-1]]

        # 3. LLM with first-token timeout
        agen = llm.stream_turn(messages)
        try:
            kind, emotion = await asyncio.wait_for(agen.__anext__(), timeout=LLM_FIRST_TOKEN_TIMEOUT_S)
        except Exception as exc:
            print(f"[turn] LLM fallback: {exc!r}")
            async for chunk in _fallback(call_id, is_greeting):
                yield chunk
            return

        yield _sse("emotion", {"emotion": emotion})
        if is_last_reply:
            yield _sse("limit", {"left": 0, "status": entry["status"], "reason": "limit"})

        # 4. text + audio pipeline
        text_q: asyncio.Queue = asyncio.Queue()
        out: asyncio.Queue = asyncio.Queue()
        sentences: list[str] = []
        tts_chars = 0
        pump_llm_error: list[BaseException] = []
        pump_tts_error: list[BaseException] = []

        async def pump_llm():
            try:
                async for kind2, delta in agen:
                    await text_q.put(delta)
                    await out.put(_sse("text", {"delta": delta}))
            except BaseException as exc:
                pump_llm_error.append(exc)
            finally:
                await text_q.put(None)

        async def deltas_from_queue():
            while True:
                item = await text_q.get()
                if item is None:
                    break
                yield item

        async def pump_tts():
            try:
                async for seq, sent_text, audio in tts.synthesize_stream(
                    split_sentences(deltas_from_queue()), emotion
                ):
                    sentences.append(sent_text)
                    nonlocal tts_chars
                    tts_chars += len(sent_text)
                    await out.put(_sse("audio", {"seq": seq, "mime": MIME, "b64": to_b64(audio), "text": sent_text}))
            except BaseException as exc:
                pump_tts_error.append(exc)
            finally:
                await out.put(None)

        task1 = asyncio.create_task(pump_llm())
        task2 = asyncio.create_task(pump_tts())

        try:
            while True:
                item = await out.get()
                if item is None:
                    break
                yield item

            if pump_llm_error:
                print(f"[turn] LLM stream error: {pump_llm_error[0]!r}")
            if pump_tts_error:
                print(f"[turn] TTS stream error: {pump_tts_error[0]!r}")
                yield _sse("error", {"code": "tts_failed"})
                return

            # 5. finish
            full = " ".join(sentences)
            history.append({"role": "assistant", "content": full})
            del history[:-HISTORY_MAX]
            _LAST_REPLY[call_id] = sentences
            u = llm.last_usage or {"tokens_in": 0, "tokens_out": 0}
            yield _sse("done", {"usage": {"tokens_in": u["tokens_in"], "tokens_out": u["tokens_out"], "tts_chars": tts_chars}})

            await record_turn(
                call_id, entry["user_id"], text, req.stt_sec, full, emotion,
                u["tokens_in"], u["tokens_out"], tts_chars,
            )
            if text:
                try:
                    await increment_usage(entry["user_id"], entry.get("fingerprint"))
                except Exception as exc:
                    print(f"[turn] increment_usage failed: {exc!r}")
        finally:
            if not task1.done():
                task1.cancel()
            if not task2.done():
                task2.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _fallback(call_id: str, is_greeting: bool):
    # remove the user message appended in step 2 (unless it was a greeting, which never touched history)
    if not is_greeting:
        history = _HISTORY.get(call_id)
        if history and history[-1]["role"] == "user":
            history.pop()

    text, emotion = random.choice(FALLBACK_PHRASES)
    yield _sse("fallback", {})
    yield _sse("emotion", {"emotion": emotion})
    yield _sse("text", {"delta": text})
    try:
        audio = await tts.synthesize(text, emotion)
    except Exception as exc:
        print(f"[turn] fallback TTS also failed: {exc!r}")
        yield _sse("error", {"code": "tts_failed"})
        return
    yield _sse("audio", {"seq": 1, "mime": MIME, "b64": to_b64(audio), "text": text})
    yield _sse("done", {"usage": {"tokens_in": 0, "tokens_out": 0, "tts_chars": len(text)}})


@router.get("/api/turn/debug/{call_id}")
async def turn_debug(call_id: str):
    return {"history": _HISTORY.get(call_id, [])}


@router.get("/api/usage/{call_id}")
async def usage(call_id: str):
    rows = await db.select(
        "messages",
        {"call_id": f"eq.{call_id}", "select": "*", "order": "created_at.asc"},
    )
    return {"messages": rows}
