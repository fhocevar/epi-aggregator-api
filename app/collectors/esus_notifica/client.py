from __future__ import annotations
from typing import Any
import httpx

class EsusNotificaClient:
    def __init__(self, *, base_url: str, username: str, password: str, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password)
        self.timeout_seconds = timeout_seconds

    async def search(self, *, index: str, query: dict[str, Any]) -> dict[str, Any]:
        """
        POST /{index}/_search
        """
        url = f"{self.base_url}/{index}/_search"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            r = await client.post(url, json=query, auth=self.auth, headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.json()