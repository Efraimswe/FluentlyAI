from datetime import datetime, timezone
from typing import Optional
from .db import db

# unit -> price_per_unit (USD); latest effective_from per unit
_RATES: dict[str, float] | None = None

_DEFAULT_RATES: dict[str, float] = {
    "token_in": 1.95e-7,
    "token_out": 1.56e-6,
    "char": 1.6e-5,
    "second": 1.28e-4,
}


async def get_rates() -> dict[str, float]:
    global _RATES
    if _RATES is not None:
        return _RATES
    rates = dict(_DEFAULT_RATES)
    try:
        rows = await db.select(
            "provider_rates",
            {"select": "unit,price_per_unit", "order": "effective_from.desc"},
        )
        seen: set[str] = set()
        for row in rows:
            unit = row["unit"]
            if unit in seen:
                continue
            seen.add(unit)
            rates[unit] = float(row["price_per_unit"])
    except Exception as exc:
        print(f"[usage] get_rates failed, using defaults: {exc!r}")
        rates = dict(_DEFAULT_RATES)
    _RATES = rates
    return _RATES


def cost_cents(tokens_in: int, tokens_out: int, tts_chars: int, stt_sec: float, rates: dict[str, float]) -> float:
    usd = (
        tokens_in * rates.get("token_in", _DEFAULT_RATES["token_in"])
        + tokens_out * rates.get("token_out", _DEFAULT_RATES["token_out"])
        + tts_chars * rates.get("char", _DEFAULT_RATES["char"])
        + stt_sec * rates.get("second", _DEFAULT_RATES["second"])
    )
    return round(usd * 100, 6)


async def record_turn(
    call_id: str,
    user_id: Optional[str],
    user_text: str,
    user_stt_sec: float,
    assistant_text: str,
    emotion: str,
    tokens_in: int,
    tokens_out: int,
    tts_chars: int,
) -> None:
    try:
        rates = await get_rates()
        stt_cost = cost_cents(0, 0, 0, user_stt_sec, rates)
        turn_cost = cost_cents(tokens_in, tokens_out, tts_chars, 0, rates)

        # PostgREST's bulk insert requires every object in the array to share the same keys,
        # so both rows carry the full column set (0 for the numeric NOT NULL columns that don't apply).
        rows = []
        if user_text:
            rows.append({
                "call_id": call_id,
                "role": "user",
                "text": user_text,
                "emotion": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "tts_chars": 0,
                "stt_sec": user_stt_sec,
                "cost_cents": stt_cost,
            })
        rows.append({
            "call_id": call_id,
            "role": "assistant",
            "text": assistant_text,
            "emotion": emotion,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tts_chars": tts_chars,
            "stt_sec": 0,
            "cost_cents": turn_cost,
        })
        await db.insert("messages", rows)

        if user_id:
            total_cost = stt_cost + turn_cost
            today = datetime.now(timezone.utc).date().isoformat()
            existing = await db.select(
                "usage_daily",
                {"select": "*", "user_id": f"eq.{user_id}", "day": f"eq.{today}"},
            )
            if existing:
                row = existing[0]
                await db.update(
                    "usage_daily",
                    {"user_id": f"eq.{user_id}", "day": f"eq.{today}"},
                    {"messages": row["messages"] + 1, "cost_cents": float(row["cost_cents"]) + total_cost},
                )
            else:
                await db.insert(
                    "usage_daily",
                    {"user_id": user_id, "day": today, "messages": 1, "cost_cents": total_cost},
                )
    except Exception as exc:
        print(f"[usage] failed: {exc!r}")
