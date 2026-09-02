import os
import time
from typing import Optional
import httpx
from . import config  # noqa: F401  (ensures load_dotenv() has run)
from .db import db

_CACHE_TTL_S = 60
_CACHE_MAX = 1000
_cache: dict[str, tuple[str, float]] = {}


async def ensure_user(user_id: str, email: Optional[str]) -> None:
    await db.insert("users", {"id": user_id, "email": email}, upsert=True, on_conflict="id")


async def get_user_id(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None

    cached = _cache.get(authorization)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    headers = {"apikey": anon_key, "Authorization": authorization}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{supabase_url}/auth/v1/user", headers=headers)
    except httpx.HTTPError:
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()
    user_id = data.get("id")
    if not user_id:
        return None

    is_new = authorization not in _cache
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[authorization] = (user_id, time.monotonic() + _CACHE_TTL_S)

    if is_new:
        try:
            await ensure_user(user_id, data.get("email"))
        except Exception as exc:
            print(f"[auth] ensure_user failed: {exc!r}")

    return user_id
