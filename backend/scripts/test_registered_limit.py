"""
End-to-end test for the registered-user message limit (10 total messages)
against a running uvicorn instance (http://127.0.0.1:8000).

Creates a fresh Supabase auth user, drives it through /api/call/start and
/api/turn up to and past the limit, checks /api/me accounting, calls
/api/call/end, then cleans up every row it created (including the auth user).

Run with: .venv/bin/python scripts/test_registered_limit.py
"""
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db

BACKEND_URL = "http://127.0.0.1:8000"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

TEST_EMAIL = f"limit-test-{secrets.token_hex(4)}@charlie.local"
TEST_PASSWORD = "Test-Pass-1234"
TZ = "Europe/Brussels"

USER_TURNS = [
    "Hey man",
    "How was the bar?",
    "Nice",
    "Tell me about the gig",
    "Who else was there",
    "That sounds fun",
    "What are you up to now",
    "Miss you man",
    "Talk soon?",
    "Alright, love you",
]

results: list[tuple[str, bool]] = []


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


def sse_events(raw: str) -> list[tuple[str, dict]]:
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


async def create_test_user() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "email_confirm": True},
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"admin create user failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()["id"]


async def get_session() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON_KEY},
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"password login failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()["access_token"]


async def get_me(authorization: str) -> dict:
    headers = {"Authorization": authorization, "X-Timezone": TZ}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/api/me", headers=headers)
    resp.raise_for_status()
    return resp.json()


async def call_start(authorization: str) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": authorization, "X-Timezone": TZ}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{BACKEND_URL}/api/call/start", headers=headers, json={})
    resp.raise_for_status()
    return resp.json()


async def call_turn(text: str, call_id: str, authorization: str) -> list[tuple[str, dict]]:
    headers = {"Content-Type": "application/json", "Authorization": authorization, "X-Timezone": TZ}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/turn",
            headers=headers,
            json={"text": text, "call_id": call_id},
        )
    resp.raise_for_status()
    return sse_events(resp.text)


async def call_end(call_id: str, authorization: str) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": authorization}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/call/end",
            headers=headers,
            json={"call_id": call_id, "duration_s": 120},
        )
    resp.raise_for_status()
    return resp.json()


async def cleanup(user_id: str) -> None:
    print("\n=== cleanup ===")
    try:
        calls = await db.select("calls", {"select": "id", "user_id": f"eq.{user_id}"})
        call_ids = [c["id"] for c in calls]
        if call_ids:
            ids = ",".join(str(i) for i in call_ids)
            await db.delete("messages", {"call_id": f"in.({ids})"})
            print(f"deleted messages for {len(call_ids)} call(s)")
    except Exception as exc:
        print(f"[cleanup] messages delete failed: {exc!r}")

    for table in ("calls", "usage_daily", "charlie_state", "memories", "users"):
        try:
            await db.delete(table, {"user_id": f"eq.{user_id}"} if table != "users" else {"id": f"eq.{user_id}"})
            print(f"deleted {table} row(s)")
        except Exception as exc:
            print(f"[cleanup] {table} delete failed: {exc!r}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            )
        print(f"deleted auth user (status={resp.status_code})")
    except Exception as exc:
        print(f"[cleanup] auth user delete failed: {exc!r}")


async def main() -> None:
    print(f"=== creating fresh test user: {TEST_EMAIL} ===")
    user_id = await create_test_user()
    print(f"user_id={user_id}")

    try:
        access_token = await get_session()
        authorization = f"Bearer {access_token}"

        print("\n=== GET /api/me (fresh registered user) ===")
        me0 = await get_me(authorization)
        print(me0)
        record("status == registered", me0.get("status") == "registered")
        record("limit == 10", me0.get("limits", {}).get("limit") == 10)
        record("used == 0", me0.get("limits", {}).get("used") == 0)

        print("\n=== /api/call/start ===")
        start = await call_start(authorization)
        call_id = start["call_id"]
        print(f"call_id={call_id} status={start.get('status')!r} limits={start.get('limits')!r}")

        print("\n=== greeting turn ===")
        greet_events = await call_turn("", call_id, authorization)
        greet_names = [n for n, _ in greet_events]
        print(f"events={greet_names}")

        fallback_seen = False
        turn10_text = ""

        for i, text in enumerate(USER_TURNS, start=1):
            print(f"\n=== turn {i}: {text!r} ===")
            events = await call_turn(text, call_id, authorization)
            names = [n for n, _ in events]
            has_limit = "limit" in names
            has_audio = "audio" in names
            joined_text = "".join(d["delta"] for n, d in events if n == "text")
            is_fallback = "fallback" in names
            if is_fallback:
                fallback_seen = True
                print(f"[note] turn {i} hit LLM fallback")
            print(f"events={names} limit={has_limit} audio={has_audio} text[:80]={joined_text[:80]!r}")

            if i < 10:
                record(f"turn {i} has no limit event", not has_limit)
            elif i == 10:
                record("turn 10 has limit event", has_limit)
                record("turn 10 has audio event", has_audio)
                turn10_text = joined_text
            await asyncio.sleep(0.5)

        print(f"\n=== turn 10 full text ===\n{turn10_text!r}")

        print("\n=== turn 11 (should be blocked) ===")
        events11 = await call_turn("One more thing", call_id, authorization)
        names11 = [n for n, _ in events11]
        print(f"events={names11}")
        record("turn 11 has limit event", "limit" in names11)
        record("turn 11 has no audio event", "audio" not in names11)

        print("\n=== GET /api/me (after limit) ===")
        me1 = await get_me(authorization)
        print(me1)
        record("used == 10", me1.get("limits", {}).get("used") == 10)
        record("left == 0", me1.get("limits", {}).get("left") == 0)

        print("\n=== /api/call/end ===")
        end_resp = await call_end(call_id, authorization)
        summary = end_resp.get("summary", {})
        print(f"mood={summary.get('mood')!r} praise={summary.get('praise')!r}")
        record("call/end returned a summary", isinstance(summary, dict) and "mood" in summary)

        if fallback_seen:
            print("\n[note] at least one turn hit the LLM fallback path; counted as a message, not a failure")

    finally:
        await cleanup(user_id)

    print("\n=== results ===")
    if all(ok for _, ok in results):
        print("ALL PASS")
    else:
        print("SOME FAIL")


if __name__ == "__main__":
    asyncio.run(main())
