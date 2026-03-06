# app/collectors/demas/collector.py
from __future__ import annotations
from typing import Any
from app.collectors.demas.client import DemasClient

class DemasCollector:
    def __init__(self, client: DemasClient, *, limit: int = 20):
        self.client = client
        self.limit = limit

    async def collect_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        async for it in self.client.iter_items(path, base_params=params or {}, limit=self.limit):
            items.append(it)
        return items