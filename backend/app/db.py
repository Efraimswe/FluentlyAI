import os
from typing import Any, Optional
import httpx
from . import config  # noqa: F401  (ensures load_dotenv() has run)


class Db:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{self.url}/rest/v1",
                timeout=10.0,
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def _check(self, resp: httpx.Response, method: str, table: str) -> None:
        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(f"db {method} {table} {resp.status_code}: {resp.text[:200]}")

    async def select(self, table: str, params: dict) -> list[dict]:
        client = self._get_client()
        resp = await client.get(f"/{table}", params=params)
        self._check(resp, "select", table)
        return resp.json()

    async def insert(
        self,
        table: str,
        rows: dict | list[dict],
        upsert: bool = False,
        on_conflict: Optional[str] = None,
    ) -> list[dict]:
        client = self._get_client()
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        headers = {"Prefer": prefer}
        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        resp = await client.post(f"/{table}", json=rows, headers=headers, params=params)
        self._check(resp, "insert", table)
        return resp.json()

    async def update(self, table: str, params: dict, data: dict) -> list[dict]:
        client = self._get_client()
        headers = {"Prefer": "return=representation"}
        resp = await client.patch(f"/{table}", params=params, json=data, headers=headers)
        self._check(resp, "update", table)
        return resp.json()

    async def delete(self, table: str, params: dict) -> list[dict]:
        client = self._get_client()
        headers = {"Prefer": "return=representation"}
        resp = await client.delete(f"/{table}", params=params, headers=headers)
        self._check(resp, "delete", table)
        return resp.json()

    async def rpc(self, fn: str, args: dict) -> Any:
        client = self._get_client()
        resp = await client.post(f"/rpc/{fn}", json=args)
        self._check(resp, "rpc", fn)
        return resp.json()


db = Db()
