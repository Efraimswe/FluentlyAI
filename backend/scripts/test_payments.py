"""
End-to-end test for app/payments.py and app/webhooks.py
against a running uvicorn instance (http://127.0.0.1:8000).

Run with: .venv/bin/python scripts/test_payments.py
"""
import asyncio
import hashlib
import hmac
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app import config  # noqa: F401  (load_dotenv)
from app.db import db

BACKEND_URL = "http://127.0.0.1:8000"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")

TEST_EMAIL = "state-test@charlie.local"
TEST_PASSWORD = "Test-Pass-1234"
TEST_LS_SUB_ID = "999001"

results: list[tuple[str, bool]] = []


def record(label: str, ok: bool) -> None:
    results.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}: {label}")


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


async def get_me(authorization: str | None) -> dict:
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BACKEND_URL}/api/me", headers=headers)
    resp.raise_for_status()
    return resp.json()


def sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def post_webhook(payload: bytes, signature: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.post(
            f"{BACKEND_URL}/api/webhooks/lemonsqueezy",
            headers={"Content-Type": "application/json", "X-Signature": signature},
            content=payload,
        )


def build_payload(event: str, user_id: str, status: str, extra_attrs: dict) -> dict:
    return {
        "meta": {
            "event_name": event,
            "custom_data": {"user_id": user_id},
        },
        "data": {
            "id": TEST_LS_SUB_ID,
            "attributes": {
                "status": status,
                "user_email": TEST_EMAIL,
                **extra_attrs,
            },
        },
    }


async def cleanup(user_id: str) -> None:
    try:
        await db.delete("subscriptions", {"ls_subscription_id": f"eq.{TEST_LS_SUB_ID}"})
    except Exception as exc:
        print(f"[cleanup] delete subscriptions row failed: {exc!r}")
    try:
        await db.update("users", {"id": f"eq.{user_id}"}, {"status": "registered"})
    except Exception as exc:
        print(f"[cleanup] reset user status failed: {exc!r}")


async def main() -> None:
    import json

    print("=== seeding test user ===")
    await get_or_create_test_user()
    access_token, user_id = await get_session()
    authorization = f"Bearer {access_token}"
    print(f"user_id={user_id}")

    try:
        # --- 1. checkout ---
        print("\n=== /api/checkout (no auth) ===")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{BACKEND_URL}/api/checkout")
        record("checkout without auth -> 401", resp.status_code == 401)

        print("\n=== /api/checkout (authenticated) ===")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/api/checkout",
                headers={"Authorization": authorization},
            )
        ok = resp.status_code == 200
        url = None
        if ok:
            url = resp.json().get("url", "")
            print(f"url host+prefix: {url[:60]!r}")
        else:
            print(f"checkout failed: {resp.status_code} {resp.text[:300]}")
        record("checkout returns 200 with a lemonsqueezy.com url", ok and "lemonsqueezy.com" in url)

        # --- 2. webhook signature + state transitions ---
        now = datetime.now(timezone.utc)
        plus3d = (now + timedelta(days=3)).isoformat()
        plus30d = (now + timedelta(days=30)).isoformat()

        print("\n=== webhook: wrong signature -> 401 ===")
        bad_payload = json.dumps(
            build_payload("subscription_created", user_id, "on_trial", {"trial_ends_at": plus3d, "renews_at": plus3d})
        ).encode()
        resp = await post_webhook(bad_payload, "deadbeef" * 8)
        record("webhook with wrong signature -> 401", resp.status_code == 401)

        print("\n=== webhook: subscription_created (on_trial) ===")
        payload = json.dumps(
            build_payload("subscription_created", user_id, "on_trial", {"trial_ends_at": plus3d, "renews_at": plus3d})
        ).encode()
        resp = await post_webhook(payload, sign(payload))
        record("subscription_created -> 200", resp.status_code == 200)

        me = await get_me(authorization)
        record("after on_trial: /api/me status == trial", me["status"] == "trial")
        record(
            "after on_trial: subscription.status == on_trial",
            (me.get("subscription") or {}).get("status") == "on_trial",
        )

        print("\n=== webhook: subscription_updated (active) ===")
        payload = json.dumps(
            build_payload("subscription_updated", user_id, "active", {"trial_ends_at": plus3d, "renews_at": plus30d})
        ).encode()
        resp = await post_webhook(payload, sign(payload))
        record("subscription_updated -> 200", resp.status_code == 200)

        me = await get_me(authorization)
        record("after active: /api/me status == subscriber", me["status"] == "subscriber")

        print("\n=== webhook: subscription_cancelled ===")
        payload = json.dumps(
            build_payload("subscription_cancelled", user_id, "cancelled", {"trial_ends_at": plus3d, "ends_at": plus30d})
        ).encode()
        resp = await post_webhook(payload, sign(payload))
        record("subscription_cancelled -> 200", resp.status_code == 200)

        me = await get_me(authorization)
        record("after cancelled: /api/me status still subscriber", me["status"] == "subscriber")
        record(
            "after cancelled: cancelled_at is set",
            bool((me.get("subscription") or {}).get("cancelled_at")),
        )

        print("\n=== webhook: subscription_expired ===")
        payload = json.dumps(
            build_payload("subscription_expired", user_id, "expired", {})
        ).encode()
        resp = await post_webhook(payload, sign(payload))
        record("subscription_expired -> 200", resp.status_code == 200)

        me = await get_me(authorization)
        record("after expired: /api/me status == registered", me["status"] == "registered")

    finally:
        print("\n=== cleanup ===")
        await cleanup(user_id)

    print("\n=== results ===")
    if all(ok for _, ok in results):
        print("\nALL PASS")
    else:
        print("\nSOME FAILED")


if __name__ == "__main__":
    asyncio.run(main())
