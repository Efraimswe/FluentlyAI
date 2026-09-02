"""
End-to-end test for /api/call/end (postcall summary + state/memory persistence)
against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_postcall.py
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db
from app.auth import ensure_user

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


async def call_turn(text: str, call_id: str, authorization: str) -> tuple[str, str]:
    """Returns (joined text deltas, emotion)."""
    headers = {"Content-Type": "application/json", "Authorization": authorization}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/turn",
            headers=headers,
            json={"text": text, "call_id": call_id},
        )
    events = sse_events(resp.text)
    text_out = "".join(d["delta"] for name, d in events if name == "text")
    emotion = next((d["emotion"] for name, d in events if name == "emotion"), "")
    return text_out, emotion


async def call_start(call_id: str, authorization: str) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": authorization}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/call/start",
            headers=headers,
            json={},
        )
    resp.raise_for_status()
    return resp.json()


async def call_end(call_id: str, authorization: str, duration_s: int, end_reason: str) -> tuple[dict, float]:
    headers = {"Content-Type": "application/json", "Authorization": authorization}
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/call/end",
            headers=headers,
            json={"call_id": call_id, "duration_s": duration_s, "end_reason": end_reason},
        )
    elapsed_s = time.perf_counter() - start
    resp.raise_for_status()
    return resp.json(), elapsed_s


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


async def main() -> None:
    print("=== seeding test user ===")
    await get_or_create_test_user()
    access_token, user_id = await get_session()
    print(f"user_id={user_id}")
    await ensure_user(user_id, TEST_EMAIL)
    authorization = f"Bearer {access_token}"

    call_id = f"test-postcall-{user_id[:8]}"

    print("\n=== /api/call/start ===")
    start = await call_start(call_id, authorization)
    call_id = start["call_id"]
    print(f"call_id={call_id} mood={start['mood']!r} day_event={start['day_event']!r}")

    print("\n=== greeting turn ===")
    greet_text, greet_emotion = await call_turn("", call_id, authorization)
    print(f"emotion={greet_emotion!r}")
    print(f"text={greet_text!r}")

    user_text = "Hey Charlie! It's Efraim. My job interview went great, they want me back next week."
    print(f"\n=== user turn: {user_text!r} ===")
    t1_text, t1_emotion = await call_turn(user_text, call_id, authorization)
    print(f"emotion={t1_emotion!r}")
    print(f"text={t1_text!r}")

    print("\n=== /api/call/end (user_hung_up_mid_story) ===")
    end_resp, elapsed_s = await call_end(call_id, authorization, duration_s=95, end_reason="user_hung_up_mid_story")
    print(f"elapsed={elapsed_s:.2f}s")
    print(json.dumps(end_resp, indent=2))

    print("\n=== readback: charlie_state ===")
    state_rows = await db.select("charlie_state", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"})
    state_row = state_rows[0] if state_rows else None
    print(json.dumps(state_row, indent=2))

    print("\n=== readback: last 5 memories ===")
    memory_rows = await db.select(
        "memories",
        {"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc", "limit": "5"},
    )
    print(json.dumps(memory_rows, indent=2))

    print("\n=== readback: calls row ===")
    calls_rows = await db.select("calls", {"id": f"eq.{call_id}", "select": "*", "limit": "1"})
    calls_row = calls_rows[0] if calls_rows else None
    print(json.dumps(calls_row, indent=2))

    print("\n=== results ===")
    summary = end_resp.get("summary", {})
    praise = summary.get("praise")
    record("response has non-null praise (string >= 20 chars)", isinstance(praise, str) and len(praise) >= 20)
    record("charlie_state.mood is 'offended' (hung up mid-story)", bool(state_row) and state_row.get("mood") == "offended")
    memories_mention_interview = any(
        "interview" in (m.get("content", "").lower()) for m in memory_rows
    )
    record("memories contain something about the interview", memories_mention_interview)
    record("calls.ended_at set", bool(calls_row) and calls_row.get("ended_at") is not None)

    if all(ok for _, ok in results):
        print("\nALL PASS")
    else:
        print("\nSOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
