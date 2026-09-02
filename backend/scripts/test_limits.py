"""
End-to-end test for app/limits.py (/api/me, increment_usage, check_rate)
against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_limits.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db
from app import limits

BACKEND_URL = "http://127.0.0.1:8000"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

TEST_EMAIL = "state-test@charlie.local"
TEST_PASSWORD = "Test-Pass-1234"
TEST_FP = "test-fp-001"

results: list[tuple[str, bool]] = []


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


async def get_me(authorization: str | None) -> dict:
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["X-Fingerprint"] = TEST_FP
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/api/me", headers=headers)
    resp.raise_for_status()
    return resp.json()


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


async def count_user_messages(user_id: str) -> int:
    calls = await db.select("calls", {"select": "id", "user_id": f"eq.{user_id}"})
    call_ids = [c["id"] for c in calls]
    if not call_ids:
        return 0
    ids = ",".join(str(i) for i in call_ids)
    messages = await db.select("messages", {"select": "id", "call_id": f"in.({ids})", "role": "eq.user"})
    return len(messages)


async def cleanup_guest_row() -> None:
    try:
        await db.delete("guests", {"fingerprint": f"eq.{TEST_FP}"})
        print(f"cleaned up guests row for fingerprint={TEST_FP!r}")
    except Exception as exc:
        print(f"cleanup failed: {exc!r}")


async def main() -> None:
    print("=== (1) GET /api/me as guest (no auth), fresh fingerprint ===")
    me1 = await get_me(None)
    print(me1)
    record("guest status", me1["status"] == "guest")
    record("guest limit == 2", me1["limits"]["limit"] == 2)
    record("guest period == total", me1["limits"]["period"] == "total")

    print("\n=== (2) increment_usage(None, fp) twice, then GET /api/me ===")
    await limits.increment_usage(None, TEST_FP)
    await limits.increment_usage(None, TEST_FP)
    info = await limits.get_limit_info(None, TEST_FP)
    print(f"LimitInfo: {info}")
    me2 = await get_me(None)
    print(me2)
    record("used == 2 after 2 increments", me2["limits"]["used"] == 2)
    record("left == 0", me2["limits"]["left"] == 0)
    record("get_limit_info.allowed is False", info.allowed is False)

    print("\n=== (3) GET /api/me authenticated ===")
    access_token, user_id = await get_session()
    print(f"user_id={user_id}")
    expected_used = await count_user_messages(user_id)
    print(f"expected used (user messages so far) = {expected_used}")
    me3 = await get_me(f"Bearer {access_token}")
    print(me3)
    record("registered status", me3["status"] == "registered")
    record("registered limit == 10", me3["limits"]["limit"] == 10)
    record("registered used matches message count", me3["limits"]["used"] == expected_used)

    print("\n=== (4) check_rate('x') 20x True then False ===")
    rate_results = [limits.check_rate("x") for _ in range(21)]
    print(rate_results)
    record("first 20 calls True", all(rate_results[:20]))
    record("21st call False", rate_results[20] is False)

    print("\n=== (5) cleanup ===")
    await cleanup_guest_row()

    print("\n=== results ===")
    if all(ok for _, ok in results):
        print("ALL PASS")
    else:
        print("SOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
