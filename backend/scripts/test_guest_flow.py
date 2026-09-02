"""
End-to-end test for the guest message-limit flow (app/limits.py + app/turn.py +
app/deepgram_token.py) against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_guest_flow.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db

BACKEND_URL = "http://127.0.0.1:8000"
FP = "guest-flow-test-1"
TZ = "Europe/Brussels"
CALL_ID = f"test-{FP}"

HEADERS = {"Content-Type": "application/json", "X-Fingerprint": FP, "X-Timezone": TZ}

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


async def call_start() -> httpx.Response:
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(f"{BACKEND_URL}/api/call/start", headers=HEADERS, json={"call_id": CALL_ID})


async def call_turn(text: str) -> tuple[list[tuple[str, dict]], str]:
    """Returns (events, joined text deltas)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_URL}/api/turn",
            headers=HEADERS,
            json={"text": text, "call_id": CALL_ID},
        )
    events = sse_events(resp.text)
    text_out = "".join(d["delta"] for name, d in events if name == "text")
    return events, text_out


async def get_me() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/api/me", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


async def cleanup() -> None:
    try:
        await db.delete("guests", {"fingerprint": f"eq.{FP}"})
    except Exception as exc:
        print(f"[cleanup] guests delete failed: {exc!r}")
    try:
        await db.delete("calls", {"guest_fp": f"eq.{FP}"})
    except Exception as exc:
        print(f"[cleanup] calls delete failed: {exc!r}")


async def main() -> None:
    await cleanup()  # in case a previous failed run left rows behind

    print("=== 1. /api/call/start ===")
    start_resp = await call_start()
    start_resp.raise_for_status()
    start = start_resp.json()
    print(f"status={start.get('status')!r} limits={start.get('limits')!r}")
    record("call/start status is guest", start.get("status") == "guest")
    record("call/start limits.left == 2", start.get("limits", {}).get("left") == 2)

    print("\n=== 2. greeting ===")
    greet_events, greet_text = await call_turn("")
    greet_emotion = next((d["emotion"] for name, d in greet_events if name == "emotion"), "")
    print(f"emotion={greet_emotion!r}")
    print(f"text={greet_text!r}")
    record("greeting produced text", bool(greet_text.strip()))

    print('\n=== 3. turn: "Hey man, how\'s the bar tonight?" ===')
    t1_events, t1_text = await call_turn("Hey man, how's the bar tonight?")
    t1_names = [name for name, _ in t1_events]
    print(f"events={t1_names}")
    print(f"text={t1_text!r}")
    record("turn 1 has no limit event", "limit" not in t1_names)
    record("turn 1 produced text", bool(t1_text.strip()))

    print('\n=== 4. turn: "Nice. And what about your music?" ===')
    t2_events, t2_text = await call_turn("Nice. And what about your music?")
    t2_names = [name for name, _ in t2_events]
    print(f"events={t2_names}")
    print(f"text={t2_text!r}")
    record("turn 2 has a limit event", "limit" in t2_names)
    hook_or_signup = any(
        kw in t2_text.lower()
        for kw in ("sign up", "sign-up", "register", "account", "make an account")
    )
    record("turn 2 text mentions a hook / sign-up", hook_or_signup)

    print('\n=== 5. turn: "Tell me more" (should be blocked) ===')
    t3_events, t3_text = await call_turn("Tell me more")
    t3_names = [name for name, _ in t3_events]
    print(f"events={t3_names}")
    print(f"text={t3_text!r}")
    record("turn 3 events start with limit", bool(t3_names) and t3_names[0] == "limit")
    record("turn 3 has no audio event", "audio" not in t3_names)
    record("turn 3 has a done event", "done" in t3_names)

    print("\n=== 6. GET /api/me ===")
    me = await get_me()
    print(f"me={me!r}")
    record("/api/me left == 0", me.get("limits", {}).get("left") == 0)

    print("\n=== 7. /api/call/start again (should 403) ===")
    start2_resp = await call_start()
    print(f"status_code={start2_resp.status_code}")
    try:
        detail = start2_resp.json().get("detail")
    except Exception:
        detail = None
    print(f"detail={detail!r}")
    record("second call/start returns 403", start2_resp.status_code == 403)
    record("second call/start detail.code == 'limit'", isinstance(detail, dict) and detail.get("code") == "limit")

    print("\n=== 8. cleanup ===")
    await cleanup()
    print("cleaned up guests + calls rows")

    print("\n=== results ===")
    if all(ok for _, ok in results):
        print("\nALL PASS")
    else:
        print("\nSOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
