"""
End-to-end test for usage/cost tracking (messages, usage_daily, v_daily_margin)
against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_usage.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db

BACKEND_URL = "http://127.0.0.1:8000"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

TEST_EMAIL = "state-test@charlie.local"
TEST_PASSWORD = "Test-Pass-1234"

results: list[tuple[str, bool]] = []


async def get_or_create_test_user() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "email_confirm": True},
        )
    if resp.status_code not in (200, 201) and "already registered" not in resp.text.lower() and resp.status_code != 422:
        raise RuntimeError(f"admin create user failed: {resp.status_code} {resp.text[:300]}")


async def get_session() -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON_KEY},
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"password login failed: {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    return data["access_token"], data["user"]["id"]


def sse_events(raw: str):
    events = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if event_name and data is not None:
            events.append((event_name, json.loads(data)))
    return events


async def call_start(authorization: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/call/start",
            headers={"Content-Type": "application/json", "Authorization": authorization},
            json={},
        )
    resp.raise_for_status()
    return resp.json()["call_id"]


async def call_turn(text: str, call_id: str, authorization: str, stt_sec: float = 0.0) -> tuple[str, str]:
    """Returns (joined text deltas, emotion)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/turn",
            headers={"Content-Type": "application/json", "Authorization": authorization},
            json={"text": text, "call_id": call_id, "stt_sec": stt_sec},
        )
    events = sse_events(resp.text)
    text_out = "".join(d["delta"] for name, d in events if name == "text")
    emotion = next((d["emotion"] for name, d in events if name == "emotion"), "")
    return text_out, emotion


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


async def main() -> None:
    print("=== seeding test user ===")
    await get_or_create_test_user()
    access_token, user_id = await get_session()
    print(f"user_id={user_id}")
    authorization = f"Bearer {access_token}"

    print("\n=== /api/call/start (authenticated) ===")
    call_id = await call_start(authorization)
    print(f"call_id={call_id}")

    print("\n=== greeting ===")
    greet_text, greet_emotion = await call_turn("", call_id, authorization)
    print(f"emotion={greet_emotion!r} text={greet_text!r}")

    print("\n=== turn: \"Tell me about your Friday gig, man.\" ===")
    t1_text, t1_emotion = await call_turn(
        "Tell me about your Friday gig, man.", call_id, authorization, stt_sec=2.4
    )
    print(f"emotion={t1_emotion!r} text={t1_text!r}")

    await asyncio.sleep(1)

    print("\n=== GET /api/usage/{call_id} ===")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/api/usage/{call_id}")
    resp.raise_for_status()
    rows = resp.json()["messages"]
    for row in rows:
        print(
            f"role={row.get('role'):<10} tokens_in={row.get('tokens_in')!s:<6} "
            f"tokens_out={row.get('tokens_out')!s:<6} tts_chars={row.get('tts_chars')!s:<6} "
            f"stt_sec={row.get('stt_sec')!s:<6} cost_cents={row.get('cost_cents')}"
        )

    print("\n=== usage_daily (direct DB) ===")
    today = datetime.now(timezone.utc).date().isoformat()
    daily = await db.select(
        "usage_daily",
        {"select": "*", "user_id": f"eq.{user_id}", "day": f"eq.{today}"},
    )
    print(daily)

    print("\n=== v_daily_margin (direct DB) ===")
    margin = await db.select("v_daily_margin", {"select": "*", "limit": "3"})
    print(margin)

    print("\n=== results ===")
    record("3 message rows (assistant greeting, user, assistant)", len(rows) == 3)

    assistant_rows = [r for r in rows if r.get("role") == "assistant"]
    record(
        "assistant rows have tokens_in > 1000 and cost_cents > 0",
        len(assistant_rows) == 2
        and all((r.get("tokens_in") or 0) > 1000 for r in assistant_rows)
        and all((r.get("cost_cents") or 0) > 0 for r in assistant_rows),
    )

    user_rows = [r for r in rows if r.get("role") == "user"]
    record(
        "user row stt_sec == 2.4",
        len(user_rows) == 1 and float(user_rows[0].get("stt_sec") or 0) == 2.4,
    )

    record(
        "usage_daily.messages >= 2",
        len(daily) == 1 and daily[0].get("messages", 0) >= 2,
    )

    if all(ok for _, ok in results):
        print("\nALL PASS")
    else:
        print("\nSOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
