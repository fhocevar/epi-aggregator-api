from __future__ import annotations

from typing import Any

from app.collectors.demas.client import DemasClient


class DemasCollector:
    def __init__(self, client: DemasClient, page_size: int = 1000):
        self.client = client
        self.page_size = page_size

    async def collect_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        async for item in self.client.iter_items(path, base_params=params, page_size=self.page_size):
            rows.append(item)
        return rows