import os, uuid
import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from . import config  # noqa: F401
from .auth import get_user_id
from .db import db
from .limits import get_limit_info
from .turn import prepare_call

router = APIRouter()
DEEPGRAM_GRANT_URL = "https://api.deepgram.com/v1/auth/grant"
TOKEN_TTL_S = 60


async def grant_token(ttl_s: int = TOKEN_TTL_S) -> dict:
    """POST /v1/auth/grant with the project key. Returns {"access_token", "expires_in"}.
    Raises HTTPException(502, "deepgram_grant_forbidden") on 403 (key needs Member permissions),
    HTTPException(502, "deepgram_grant_failed") on other errors."""
    key = os.getenv("DEEPGRAM_API_KEY", "")
    headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
    body = {"ttl_seconds": ttl_s}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DEEPGRAM_GRANT_URL, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(502, "deepgram_grant_failed") from exc
    if resp.status_code == 403:
        raise HTTPException(502, "deepgram_grant_forbidden")
    if resp.status_code != 200:
        raise HTTPException(502, "deepgram_grant_failed")
    return resp.json()


class CallStartRequest(BaseModel):
    fingerprint: str | None = None
    call_id: str | None = None


@router.post("/api/call/start")
async def call_start(
    req: CallStartRequest,
    authorization: str | None = Header(default=None),
    x_fingerprint: str | None = Header(default=None),
    x_timezone: str | None = Header(default=None),
):
    is_new_call = req.call_id is None
    call_id = req.call_id or str(uuid.uuid4())
    user_id = await get_user_id(authorization)

    info = await get_limit_info(user_id, x_fingerprint, x_timezone)
    if not info.allowed:
        raise HTTPException(403, detail={
            "code": "limit",
            "status": info.status,
            "limits": {"left": info.left, "limit": info.limit, "used": info.used, "period": info.period},
            "reason": info.reason,
        })

    entry = await prepare_call(call_id, user_id)
    entry["fingerprint"] = x_fingerprint
    entry["tz"] = x_timezone
    entry["status"] = info.status
    if is_new_call:
        try:
            insert_row = {"id": call_id, "user_id": entry["user_id"], "start_mood": entry["mood"]}
            if entry["is_guest"]:
                insert_row["guest_fp"] = x_fingerprint
            await db.insert("calls", insert_row)
        except Exception as e:
            print(f"[calls] insert failed: {e!r}")
    limits_payload = {"left": info.left, "limit": info.limit, "used": info.used, "period": info.period}
    try:
        tok = await grant_token()
    except HTTPException as exc:
        if exc.detail == "deepgram_grant_forbidden" and os.getenv("DEEPGRAM_DEV_RAW_KEY") == "1":
            print("[call/start] DEV: using raw Deepgram key (grant forbidden)")
            return {
                "call_id": call_id,
                "deepgram_token": os.getenv("DEEPGRAM_API_KEY"),
                "deepgram_auth": "token",
                "deepgram_expires_in": None,
                "limits": limits_payload,
                "status": info.status,
                "day_event": entry["day_event"]["text"],
                "mood": entry["mood"],
                "is_guest": entry["is_guest"],
            }
        raise
    return {
        "call_id": call_id,
        "deepgram_token": tok["access_token"],
        "deepgram_auth": "bearer",
        "deepgram_expires_in": tok["expires_in"],
        "limits": limits_payload,
        "status": info.status,
        "day_event": entry["day_event"]["text"],
        "mood": entry["mood"],
        "is_guest": entry["is_guest"],
    }
