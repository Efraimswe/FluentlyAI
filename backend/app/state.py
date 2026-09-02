import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from .db import db

_PROMPTS = Path(__file__).parent / "prompts"

_STATE_BLOCK_TEMPLATE = (_PROMPTS / "state_block.md").read_text(encoding="utf-8").strip()


def _parse_state_rules(text: str) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = stripped[3:].strip()
            rules[current] = []
        elif stripped.startswith("- ") and current is not None:
            rules[current].append(stripped[2:].strip())
    return rules


_STATE_RULES = _parse_state_rules((_PROMPTS / "state_rules.md").read_text(encoding="utf-8"))


@dataclass
class CharlieState:
    mood: str = "calm"
    mood_level: int = 3
    attention: int = 6
    relationship: str = "new"
    offended_reason: Optional[str] = None
    last_call_at: Optional[str] = None


_DEFAULT_STATE_ROW = {
    "mood": "calm",
    "mood_level": 3,
    "attention": 6,
    "relationship": "new",
    "offended_reason": None,
    "last_call_at": None,
}


def _state_from_row(row: dict) -> CharlieState:
    return CharlieState(
        mood=row.get("mood", "calm"),
        mood_level=row.get("mood_level", 3),
        attention=row.get("attention", 6),
        relationship=row.get("relationship", "new"),
        offended_reason=row.get("offended_reason"),
        last_call_at=row.get("last_call_at"),
    )


async def load_state(user_id: str) -> CharlieState:
    rows = await db.select("charlie_state", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"})
    if rows:
        return _state_from_row(rows[0])
    row = {"user_id": user_id, **_DEFAULT_STATE_ROW}
    inserted = await db.insert("charlie_state", row, upsert=True, on_conflict="user_id")
    return _state_from_row(inserted[0]) if inserted else CharlieState()


async def load_memories(user_id: str, limit: int = 20) -> list[dict]:
    return await db.select(
        "memories",
        {"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc", "limit": str(limit)},
    )


def _weighted_choice(events: list[dict]) -> dict:
    weights = [max(e.get("weight", 1), 0) for e in events]
    if sum(weights) <= 0:
        return random.choice(events)
    return random.choices(events, weights=weights, k=1)[0]


async def pick_day_event(user_id: Optional[str]) -> dict:
    today = date.today().isoformat()

    if user_id:
        links = await db.select(
            "user_day_event",
            {"user_id": f"eq.{user_id}", "day": f"eq.{today}", "select": "*", "limit": "1"},
        )
        if links:
            event_id = links[0]["event_id"]
            events = await db.select("day_events", {"id": f"eq.{event_id}", "select": "*", "limit": "1"})
            if events:
                return events[0]

    all_events = await db.select("day_events", {"select": "*"})
    if not all_events:
        raise RuntimeError("state pick_day_event: no day_events rows")
    event = _weighted_choice(all_events)

    if user_id:
        try:
            await db.insert(
                "user_day_event",
                {"user_id": user_id, "day": today, "event_id": event["id"]},
                upsert=True,
                on_conflict="user_id,day",
            )
        except Exception as exc:
            print(f"[state] user_day_event insert failed: {exc!r}")

    return event


def start_mood(state: CharlieState, day_event: dict) -> tuple[str, int]:
    if state.mood == "offended" and state.offended_reason:
        return ("offended", state.mood_level)

    if state.last_call_at:
        try:
            last_call = datetime.fromisoformat(state.last_call_at.replace("Z", "+00:00"))
            if last_call.tzinfo is None:
                last_call = last_call.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_call).total_seconds() / 3600
        except ValueError:
            hours_since = None
        if hours_since is not None and hours_since < 24 and state.mood != "calm":
            return (state.mood, state.mood_level)

    mood_effect = day_event["mood_effect"]
    return (mood_effect, 5 if mood_effect != "calm" else 3)


def _attention_bucket(attention: int) -> str:
    if attention < 4:
        return "low"
    if attention <= 7:
        return "mid"
    return "high"


def build_state_block(
    state: CharlieState,
    memories: list[dict],
    day_event: dict,
    is_guest: bool,
    mood: str,
    mood_level: int,
    extra_rules: Optional[list[str]] = None,
) -> str:
    memory = "; ".join(f"{m['kind']}: {m['content']}" for m in memories) or "nothing yet"

    rule_lines: list[str] = []
    rule_lines.extend(_STATE_RULES.get(f"mood:{mood}", []))
    rule_lines.extend(_STATE_RULES.get(f"attention:{_attention_bucket(state.attention)}", []))
    rule_lines.extend(_STATE_RULES.get(f"relationship:{state.relationship}", []))
    if is_guest:
        rule_lines.extend(_STATE_RULES.get("first_call_guest", []))
    for key in extra_rules or []:
        rule_lines.extend(_STATE_RULES.get(key, []))

    rules = "\n".join(f"- {line}" for line in rule_lines)
    if mood == "offended":
        rules = rules.replace("{offended_reason}", state.offended_reason or "")

    return (
        _STATE_BLOCK_TEMPLATE
        .replace("{mood}", mood)
        .replace("{mood_level}", str(mood_level))
        .replace("{attention}", str(state.attention))
        .replace("{relationship}", state.relationship)
        .replace("{day_event}", day_event["text"])
        .replace("{memory}", memory)
        .replace("{rules}", rules)
    )
