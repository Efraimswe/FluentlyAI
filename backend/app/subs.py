import os
import time
from typing import Optional

import httpx

from . import config  # noqa: F401  (ensures load_dotenv() has run)
from .db import db

LS_API = "https://api.lemonsqueezy.com/v1"

_ACTIVE_SUB_STATUSES = ("on_trial", "active", "past_due", "cancelled", "paused")

_PORTAL_CACHE_TTL_S = 600
_portal_cache: dict[str, tuple[Optional[str], float]] = {}


async def _get_customer_portal_url(ls_subscription_id: str) -> Optional[str]:
    cached = _portal_cache.get(ls_subscription_id)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    api_key = os.getenv("LEMONSQUEEZY_API_KEY", "")
    url: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LS_API}/subscriptions/{ls_subscription_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/vnd.api+json",
                },
            )
        if resp.status_code == 200:
            attrs = resp.json().get("data", {}).get("attributes", {})
            url = attrs.get("urls", {}).get("customer_portal")
    except Exception as exc:
        print(f"[subs] customer_portal lookup failed: {exc!r}")
        url = None

    _portal_cache[ls_subscription_id] = (url, time.monotonic() + _PORTAL_CACHE_TTL_S)
    return url


async def get_subscription_info(user_id: str) -> dict:
    """Returns {"status": <users.status>, "subscription": <row dict or None>}."""
    status = "registered"
    try:
        rows = await db.select("users", {"select": "status", "id": f"eq.{user_id}"})
        if rows and rows[0].get("status"):
            status = rows[0]["status"]
    except Exception as exc:
        print(f"[subs] fetching user status failed: {exc!r}")

    subscription = None
    try:
        rows = await db.select(
            "subscriptions",
            {
                "select": "status,renews_at,trial_ends_at,cancelled_at,ls_subscription_id",
                "user_id": f"eq.{user_id}",
                "status": f"in.({','.join(_ACTIVE_SUB_STATUSES)})",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        if rows:
            row = rows[0]
            portal_url = None
            if row.get("ls_subscription_id"):
                portal_url = await _get_customer_portal_url(row["ls_subscription_id"])
            subscription = {
                "status": row.get("status"),
                "renews_at": row.get("renews_at"),
                "trial_ends_at": row.get("trial_ends_at"),
                "cancelled_at": row.get("cancelled_at"),
                "customer_portal_url": portal_url,
            }
    except Exception as exc:
        print(f"[subs] fetching subscription row failed: {exc!r}")
        subscription = None

    return {"status": status, "subscription": subscription}
