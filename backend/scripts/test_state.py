"""
End-to-end test for level-4 state wiring: users/charlie_state/memories/day_events
against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_state.py
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


async def get_session() -> str:
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


async def seed_state_and_memories(user_id: str) -> None:
    await ensure_user(user_id, TEST_EMAIL)
    now = datetime.now(timezone.utc).isoformat()
    await db.insert(
        "charlie_state",
        {
            "user_id": user_id,
            "mood": "offended",
            "mood_level": 6,
            "attention": 3,
            "relationship": "warming up",
            "offended_reason": "he hung up in the middle of my story about the Friday gig",
            "last_call_at": now,
        },
        upsert=True,
        on_conflict="user_id",
    )

    # delete existing memories for this user, then insert the fixed set
    client = db._get_client()
    resp = await client.delete("/memories", params={"user_id": f"eq.{user_id}"})
    if resp.status_code >= 300:
        raise RuntimeError(f"delete memories failed: {resp.status_code} {resp.text[:200]}")

    await db.insert(
        "memories",
        [
            {"user_id": user_id, "kind": "name", "content": "Efraim"},
            {"user_id": user_id, "kind": "fact", "content": "builds websites for small businesses"},
            {"user_id": user_id, "kind": "promise", "content": "said he'd tell me how the job interview went"},
        ],
    )


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


async def call_turn(text: str, call_id: str, authorization: str | None) -> tuple[str, str]:
    """Returns (joined text deltas, emotion)."""
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
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


async def call_start(call_id: str, authorization: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/call/start",
            headers=headers,
            json={"call_id": call_id},
        )
    resp.raise_for_status()
    return resp.json()


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


async def main() -> None:
    print("=== seeding test user ===")
    await get_or_create_test_user()
    access_token, user_id = await get_session()
    print(f"user_id={user_id}")
    await seed_state_and_memories(user_id)
    authorization = f"Bearer {access_token}"

    call_id = f"test-user-{user_id[:8]}"

    print("\n=== /api/call/start (authenticated) ===")
    start = await call_start(call_id, authorization)
    print(f"mood={start['mood']!r} day_event={start['day_event']!r} is_guest={start['is_guest']!r}")

    print("\n=== greeting (authenticated) ===")
    greet_text, greet_emotion = await call_turn("", call_id, authorization)
    print(f"emotion={greet_emotion!r}")
    print(f"text={greet_text!r}")

    print("\n=== turn 1: \"Hey Charlie, what's up?\" ===")
    t1_text, t1_emotion = await call_turn("Hey Charlie, what's up?", call_id, authorization)
    print(f"emotion={t1_emotion!r}")
    print(f"text={t1_text!r}")

    print("\n=== turn 2: apology ===")
    t2_text, t2_emotion = await call_turn("Sorry man, I'm just tired. What's wrong?", call_id, authorization)
    print(f"emotion={t2_emotion!r}")
    print(f"text={t2_text!r}")

    print("\n=== greeting WITHOUT auth header (guest) ===")
    guest_call_id = f"test-guest-{user_id[:8]}"
    guest_start = await call_start(guest_call_id, None)
    print(f"is_guest={guest_start['is_guest']!r}")
    guest_text, guest_emotion = await call_turn("", guest_call_id, None)
    print(f"emotion={guest_emotion!r}")
    print(f"text={guest_text!r}")

    print("\n=== results ===")
    hung_up_mentioned = any(
        "hung up" in t.lower() or "story" in t.lower() or "gig" in t.lower()
        for t in (greet_text, t1_text, t2_text)
    )
    record(
        "greeting emotion is offended OR a reply mentions being hung up on / the story",
        greet_emotion == "offended" or hung_up_mentioned,
    )

    name_or_interview_mentioned = any(
        "efraim" in t.lower() or "interview" in t.lower()
        for t in (greet_text, t1_text, t2_text)
    )
    record("user's name 'Efraim' or the interview appears in a reply", name_or_interview_mentioned)

    record("guest call_start returns is_guest True", guest_start["is_guest"] is True)

    if all(ok for _, ok in results):
        print("\nALL PASS")
    else:
        print("\nSOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
