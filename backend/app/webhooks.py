import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from . import config  # noqa: F401  (ensures load_dotenv() has run)
from .db import db

router = APIRouter()

# ls subscription status -> our users.status, for events that carry a fresh status
_LS_STATUS_TO_USER_STATUS = {
    "on_trial": "trial",
    "active": "subscriber",
    "past_due": "subscriber",
    "cancelled": "subscriber",  # LS keeps access until period end; subscription_expired downgrades later
    "paused": "subscriber",
    "expired": "registered",
    "unpaid": "registered",
}


def _verify_signature(body: bytes, signature: Optional[str]) -> bool:
    secret = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _find_user_id_by_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    try:
        rows = await db.select("users", {"select": "id", "email": f"eq.{email}"})
        if rows:
            return rows[0]["id"]
    except Exception as exc:
        print(f"[ls] lookup user by email failed: {exc!r}")
    return None


async def _upsert_subscription(
    ls_sub_id: str,
    user_id: str,
    ls_status: str,
    attrs: dict,
    cancelled_at: Optional[str],
) -> None:
    row = {
        "user_id": user_id,
        "ls_subscription_id": ls_sub_id,
        "plan_id": "monthly",
        "status": ls_status,
        "trial_ends_at": attrs.get("trial_ends_at"),
        "renews_at": attrs.get("renews_at"),
        "cancelled_at": cancelled_at,
    }
    existing = await db.select("subscriptions", {"select": "id", "ls_subscription_id": f"eq.{ls_sub_id}"})
    if existing:
        await db.update("subscriptions", {"ls_subscription_id": f"eq.{ls_sub_id}"}, row)
    else:
        await db.insert("subscriptions", row)


@router.post("/api/webhooks/lemonsqueezy")
async def ls_webhook(request: Request) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Signature")
    if not _verify_signature(body, signature):
        raise HTTPException(401, "invalid_signature")

    payload = json.loads(body)
    meta = payload.get("meta", {})
    event = meta.get("event_name")
    user_id = (meta.get("custom_data") or {}).get("user_id")
    data = payload.get("data", {})
    attrs = data.get("attributes", {})
    ls_sub_id = str(data.get("id"))

    if not user_id:
        user_id = await _find_user_id_by_email(attrs.get("user_email"))

    if not user_id:
        print(f"[ls] {event} sub={ls_sub_id} user=None -> ignored (no_user)")
        return {"ok": True, "ignored": "no_user"}

    new_status: Optional[str] = None
    try:
        if event in (
            "subscription_created",
            "subscription_updated",
            "subscription_resumed",
            "subscription_payment_success",
        ):
            ls_status = attrs.get("status")
            new_status = _LS_STATUS_TO_USER_STATUS.get(ls_status, "registered")
            cancelled_at = attrs.get("ends_at") if ls_status == "cancelled" else None
            await _upsert_subscription(ls_sub_id, user_id, ls_status, attrs, cancelled_at)
        elif event == "subscription_cancelled":
            new_status = "subscriber"
            cancelled_at = datetime.now(timezone.utc).isoformat()
            await _upsert_subscription(ls_sub_id, user_id, "cancelled", attrs, cancelled_at)
        elif event == "subscription_expired":
            new_status = "registered"
            await _upsert_subscription(ls_sub_id, user_id, "expired", attrs, None)
        elif event == "subscription_payment_failed":
            new_status = None
        else:
            new_status = None

        if new_status:
            await db.update("users", {"id": f"eq.{user_id}"}, {"status": new_status})
    except Exception as exc:
        print(f"[ls] db update failed for {event} sub={ls_sub_id} user={user_id}: {exc!r}")

    print(f"[ls] {event} sub={ls_sub_id} user={user_id} -> {new_status}")
    return {"ok": True}
