import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel

from .auth import get_user_id
from .db import db
from .llm import EMOTIONS, llm
from .turn import _CALLS, _HISTORY, _LAST_REPLY

router = APIRouter()

LLM_TIMEOUT_S = 12.0

_PROMPTS = Path(__file__).parent / "prompts"
_POSTCALL_TEMPLATE = (_PROMPTS / "postcall.md").read_text(encoding="utf-8").strip()

RELATIONSHIPS = {"new", "warming up", "close"}
MEMORY_KINDS = {"name", "fact", "promise", "topic", "how_treated"}

_ASSISTANT_TAG_RE = re.compile(r"^\s*\[(\w+)\]\s*")


class CallEndRequest(BaseModel):
    call_id: str
    duration_s: int = 0
    end_reason: str = "normal"          # normal | user_hung_up_mid_story | limit
    transcript: list[dict] | None = None  # [{"role":"user"|"assistant","text":...}] fallback when the server has no history (cold instance)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_transcript(history: list[dict]) -> str:
    lines: list[str] = []
    for turn in history:
        role = turn.get("role")
        text = (turn.get("content") or "").strip()
        if role == "user":
            lines.append(f"User: {text}")
        elif role == "assistant":
            lines.append(f"Charlie: {_ASSISTANT_TAG_RE.sub('', text)}")
    return "\n".join(lines)


def _format_memory(memories: list[dict]) -> str:
    return "; ".join(f"{m['kind']}: {m['content']}" for m in memories) or "nothing yet"


def _build_prompt(
    history: list[dict],
    mood: str,
    mood_level: int,
    attention: int,
    relationship: str,
    offended_reason: Optional[str],
    memories: list[dict],
    end_reason: str,
) -> str:
    return (
        _POSTCALL_TEMPLATE
        .replace("{mood}", mood)
        .replace("{mood_level}", str(mood_level))
        .replace("{attention}", str(attention))
        .replace("{relationship}", relationship)
        .replace("{offended_reason}", offended_reason or "none")
        .replace("{memory}", _format_memory(memories))
        .replace("{end_reason}", end_reason)
        .replace("{transcript}", _format_transcript(history))
    )


def _parse_json_object(text: str) -> Optional[dict]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    parsed = json.loads(t[start:end + 1])
    if not isinstance(parsed, dict):
        return None
    return parsed


def _clamp_int(value, default: int) -> int:
    try:
        iv = int(value)
    except (TypeError, ValueError):
        iv = default
    return max(1, min(10, iv))


def _validate(data: dict, prev_relationship: str) -> dict:
    mood = data.get("mood")
    if mood not in EMOTIONS:
        mood = "calm"

    relationship = data.get("relationship")
    if relationship not in RELATIONSHIPS:
        relationship = prev_relationship

    offended_reason = data.get("offended_reason")
    if not isinstance(offended_reason, str) or not offended_reason.strip():
        offended_reason = None

    new_memories: list[dict] = []
    for item in data.get("new_memories") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        content = item.get("content")
        if kind in MEMORY_KINDS and isinstance(content, str) and content.strip():
            new_memories.append({"kind": kind, "content": content.strip()})

    call_summary = data.get("call_summary")
    if not isinstance(call_summary, str) or not call_summary.strip():
        call_summary = None

    praise_for_user = data.get("praise_for_user")
    if not isinstance(praise_for_user, str) or not praise_for_user.strip():
        praise_for_user = None

    return {
        "mood": mood,
        "mood_level": _clamp_int(data.get("mood_level"), 5),
        "attention": _clamp_int(data.get("attention"), 6),
        "relationship": relationship,
        "offended_reason": offended_reason,
        "new_memories": new_memories,
        "call_summary": call_summary,
        "praise_for_user": praise_for_user,
    }


def _cleanup(call_id: str) -> None:
    _CALLS.pop(call_id, None)
    _HISTORY.pop(call_id, None)
    _LAST_REPLY.pop(call_id, None)


@router.post("/api/call/end")
async def call_end(req: CallEndRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    call_id = req.call_id
    entry = _CALLS.get(call_id)
    user_id = entry["user_id"] if entry else await get_user_id(authorization)

    raw_history = _HISTORY.get(call_id)
    if raw_history:
        history = raw_history
    else:
        history = [{"role": t.get("role"), "content": t.get("text", "")} for t in (req.transcript or [])]

    if not history:
        mood = entry["mood"] if entry else "calm"
        _cleanup(call_id)
        return {"summary": {"duration_s": req.duration_s, "mood": mood, "praise": None}}

    if entry:
        state = entry["state"]
        prev_mood, prev_mood_level = entry["mood"], entry["mood_level"]
        attention = state.attention
        relationship = state.relationship
        offended_reason = state.offended_reason
        memories = entry["memories"]
    else:
        prev_mood, prev_mood_level = "calm", 3
        attention = 6
        relationship = "new"
        offended_reason = None
        memories = []

    prompt = _build_prompt(
        history, prev_mood, prev_mood_level, attention, relationship, offended_reason, memories, req.end_reason,
    )

    prompt_messages = [{"role": "user", "content": prompt}]

    async def _run_llm() -> str:
        return "".join([d async for d in llm.stream_raw(prompt_messages, temperature=0.3, max_tokens=500)])

    result: Optional[dict] = None
    try:
        text = await asyncio.wait_for(_run_llm(), timeout=LLM_TIMEOUT_S)
        parsed = _parse_json_object(text)
        if parsed is None:
            raise ValueError("no JSON object found in LLM output")
        result = _validate(parsed, relationship)
    except Exception as exc:
        print(f"[postcall] failed: {exc!r}")

    if result is None:
        _cleanup(call_id)
        return {"summary": {"duration_s": req.duration_s, "mood": prev_mood, "praise": None}}

    now = _now_iso()

    if user_id is not None:
        try:
            await db.insert(
                "charlie_state",
                {
                    "user_id": user_id,
                    "mood": result["mood"],
                    "mood_level": result["mood_level"],
                    "attention": result["attention"],
                    "relationship": result["relationship"],
                    "offended_reason": result["offended_reason"],
                    "last_call_at": now,
                    "updated_at": now,
                },
                upsert=True,
                on_conflict="user_id",
            )
        except Exception as exc:
            print(f"[postcall] charlie_state upsert failed: {exc!r}")

        for mem in result["new_memories"]:
            try:
                existing = await db.select(
                    "memories",
                    {"user_id": f"eq.{user_id}", "content": f"eq.{mem['content']}", "select": "id", "limit": "1"},
                )
                if existing:
                    continue
                await db.insert("memories", {"user_id": user_id, "kind": mem["kind"], "content": mem["content"]})
            except Exception as exc:
                print(f"[postcall] memory insert failed: {exc!r}")

    try:
        calls_row = {
            "ended_at": now,
            "duration_s": req.duration_s,
            "end_mood": result["mood"],
            "summary": result["call_summary"],
            "praise": result["praise_for_user"],
        }
        updated = await db.update("calls", {"id": f"eq.{call_id}"}, calls_row)
        if not updated:
            await db.insert("calls", {"id": call_id, "user_id": user_id, "start_mood": prev_mood, **calls_row})
    except Exception as exc:
        print(f"[postcall] calls update failed: {exc!r}")

    _cleanup(call_id)
    return {
        "summary": {
            "duration_s": req.duration_s,
            "mood": result["mood"],
            "mood_level": result["mood_level"],
            "praise": result["praise_for_user"],
        }
    }
