import os
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException

from . import config  # noqa: F401  (ensures load_dotenv() has run)
from .auth import get_user_id
from .db import db
from .subs import LS_API, get_subscription_info

router = APIRouter()

APP_URL = os.getenv("APP_URL", "https://fluently-ai.vercel.app")


@router.post("/api/checkout")
async def create_checkout(authorization: Optional[str] = Header(default=None)) -> dict:
    user_id = await get_user_id(authorization)
    if user_id is None:
        raise HTTPException(401, "auth_required")

    email = None
    try:
        rows = await db.select("users", {"select": "email", "id": f"eq.{user_id}"})
        if rows:
            email = rows[0].get("email")
    except Exception as exc:
        print(f"[payments] fetching user email failed: {exc!r}")

    api_key = os.getenv("LEMONSQUEEZY_API_KEY", "")
    store_id = os.getenv("LEMONSQUEEZY_STORE_ID", "")
    variant_id = os.getenv("LEMONSQUEEZY_VARIANT_ID", "")

    body = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": email,
                    "custom": {"user_id": user_id},
                },
                "checkout_options": {
                    "embed": True,
                    "media": False,
                    "logo": True,
                },
                "product_options": {
                    "enabled_variants": [int(variant_id)],
                    "redirect_url": f"{APP_URL}/?checkout=success",
                    "receipt_button_text": "Back to Charlie",
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(store_id)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{LS_API}/checkouts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
            json=body,
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        print(f"[payments] checkout_failed {resp.status_code}: {resp.text[:300]}")
        raise HTTPException(502, "checkout_failed")

    data = resp.json()["data"]
    return {"url": data["attributes"]["url"]}


@router.get("/api/subscription")
async def my_subscription(authorization: Optional[str] = Header(default=None)) -> dict:
    user_id = await get_user_id(authorization)
    if user_id is None:
        raise HTTPException(401, "auth_required")
    return await get_subscription_info(user_id)
