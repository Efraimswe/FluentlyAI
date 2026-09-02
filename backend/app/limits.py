import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header

from . import config  # noqa: F401  (ensures load_dotenv() has run)
from .auth import get_user_id
from .db import db

router = APIRouter()

GUEST_DAILY_BUDGET_CENTS = float(os.getenv("GUEST_DAILY_BUDGET_CENTS", "300"))
CALL_MAX_S = int(os.getenv("CALL_MAX_S", "900"))
TURN_RATE_LIMIT_PER_MIN = 20

_DEFAULT_LIMITS: dict[str, tuple[int, str]] = {
    "guest": (2, "total"),
    "registered": (10, "total"),
    "trial": (100, "day"),
    "subscriber": (100, "day"),
}

_LIMITS_TABLE: dict[str, tuple[int, str]] | None = None

# call_id -> list of monotonic timestamps of recent /api/turn calls
_RATE_WINDOW: dict[str, list[float]] = {}


@dataclass
class LimitInfo:
    status: str            # guest|registered|trial|subscriber
    used: int
    limit: int
    period: str            # total|day
    left: int
    allowed: bool          # left > 0 (and guest budget ok)
    reason: Optional[str] = None   # "limit" | "guest_budget" | None


async def get_limits_table() -> dict[str, tuple[int, str]]:
    global _LIMITS_TABLE
    if _LIMITS_TABLE is not None:
        return _LIMITS_TABLE
    table = dict(_DEFAULT_LIMITS)
    try:
        rows = await db.select("limits", {"select": "status,messages,period"})
        for row in rows:
            table[row["status"]] = (int(row["messages"]), row["period"])
    except Exception as exc:
        print(f"[limits] get_limits_table failed, using defaults: {exc!r}")
        table = dict(_DEFAULT_LIMITS)
    _LIMITS_TABLE = table
    return table


async def get_user_status(user_id: str) -> str:
    try:
        rows = await db.select("users", {"select": "status", "id": f"eq.{user_id}"})
        if rows and rows[0].get("status"):
            return rows[0]["status"]
        return "registered"
    except Exception as exc:
        print(f"[limits] get_user_status failed: {exc!r}")
        return "registered"


def _today_start_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _today_str(tz: Optional[str]) -> str:
    if tz:
        try:
            return datetime.now(ZoneInfo(tz)).date().isoformat()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now(timezone.utc).date().isoformat()


async def _guest_budget_used_cents() -> float:
    calls = await db.select(
        "calls",
        {"select": "id", "user_id": "is.null", "started_at": f"gte.{_today_start_utc_iso()}"},
    )
    call_ids = [c["id"] for c in calls]
    if not call_ids:
        return 0.0
    ids = ",".join(str(i) for i in call_ids)
    messages = await db.select(
        "messages",
        {"select": "cost_cents", "call_id": f"in.({ids})"},
    )
    return sum(float(m.get("cost_cents") or 0) for m in messages)


async def get_limit_info(user_id: Optional[str], fingerprint: Optional[str], tz: Optional[str] = None) -> LimitInfo:
    try:
        limits_table = await get_limits_table()

        if user_id is None:
            status = "guest"
            limit, period = limits_table.get(status, _DEFAULT_LIMITS[status])
            used = 0
            if fingerprint:
                rows = await db.select(
                    "guests",
                    {"select": "messages_used", "fingerprint": f"eq.{fingerprint}"},
                )
                if rows:
                    used = int(rows[0].get("messages_used") or 0)
            left = max(limit - used, 0)
            allowed = left > 0
            reason = None if allowed else "limit"

            if allowed:
                budget_used = await _guest_budget_used_cents()
                if budget_used >= GUEST_DAILY_BUDGET_CENTS:
                    allowed = False
                    reason = "guest_budget"

            return LimitInfo(status=status, used=used, limit=limit, period=period, left=left, allowed=allowed, reason=reason)

        status = await get_user_status(user_id)
        limit, period = limits_table.get(status, _DEFAULT_LIMITS.get(status, (10, "total")))

        if period == "day":
            day = _today_str(tz)
            rows = await db.select(
                "usage_daily",
                {"select": "messages", "user_id": f"eq.{user_id}", "day": f"eq.{day}"},
            )
            used = int(rows[0]["messages"]) if rows else 0
        else:
            calls = await db.select("calls", {"select": "id", "user_id": f"eq.{user_id}"})
            call_ids = [c["id"] for c in calls]
            if call_ids:
                ids = ",".join(str(i) for i in call_ids)
                messages = await db.select(
                    "messages",
                    {"select": "id", "call_id": f"in.({ids})", "role": "eq.user"},
                )
                used = len(messages)
            else:
                used = 0

        left = max(limit - used, 0)
        allowed = left > 0
        reason = None if allowed else "limit"
        return LimitInfo(status=status, used=used, limit=limit, period=period, left=left, allowed=allowed, reason=reason)
    except Exception as exc:
        print(f"[limits] get_limit_info failed, failing open: {exc!r}")
        status = "guest" if user_id is None else "registered"
        limit, period = _DEFAULT_LIMITS[status]
        return LimitInfo(status=status, used=0, limit=limit, period=period, left=limit, allowed=True, reason=None)


async def increment_usage(user_id: Optional[str], fingerprint: Optional[str]) -> None:
    if user_id is not None or not fingerprint:
        return
    try:
        rows = await db.select(
            "guests",
            {"select": "messages_used", "fingerprint": f"eq.{fingerprint}"},
        )
        now = datetime.now(timezone.utc).isoformat()
        if rows:
            used = int(rows[0].get("messages_used") or 0)
            await db.update(
                "guests",
                {"fingerprint": f"eq.{fingerprint}"},
                {"messages_used": used + 1, "last_seen": now},
            )
        else:
            await db.insert(
                "guests",
                {"fingerprint": fingerprint, "messages_used": 1, "first_seen": now, "last_seen": now},
            )
    except Exception as exc:
        print(f"[limits] increment_usage failed: {exc!r}")


def check_rate(call_id: str) -> bool:
    now = time.monotonic()
    window = _RATE_WINDOW.setdefault(call_id, [])
    cutoff = now - 60.0
    while window and window[0] < cutoff:
        window.pop(0)
    if len(window) >= TURN_RATE_LIMIT_PER_MIN:
        return False
    window.append(now)
    return True


def call_too_long(started_at: float) -> bool:
    return time.time() - started_at > CALL_MAX_S


@router.get("/api/me")
async def me(
    authorization: Optional[str] = Header(default=None),
    x_fingerprint: Optional[str] = Header(default=None),
    x_timezone: Optional[str] = Header(default=None),
) -> dict:
    user_id = await get_user_id(authorization)
    info = await get_limit_info(user_id, x_fingerprint, x_timezone)

    user = None
    if user_id is not None:
        email = None
        try:
            rows = await db.select("users", {"select": "email", "id": f"eq.{user_id}"})
            if rows:
                email = rows[0].get("email")
        except Exception as exc:
            print(f"[limits] fetching user email failed: {exc!r}")
        user = {"id": user_id, "email": email}

    return {
        "status": info.status,
        "limits": {
            "left": info.left,
            "limit": info.limit,
            "used": info.used,
            "period": info.period,
        },
        "user": user,
        "subscription": None,
    }
