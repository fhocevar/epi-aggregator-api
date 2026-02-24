# app/collectors/opendatasus_ckan.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class CkanResource:
    id: str
    name: str
    format: str
    url: str


class OpenDataSUSCkanClient:
    """
    CKAN Action API client (package_show), com fallback de hosts.

    Na sua rede:
      - ckan-dadosabertos.saude.gov.br NÃO resolve DNS (Errno 11001).
    Então evitamos depender dele e tentamos apenas hosts que resolvem,
    validando se /api/3/action existe via status_show.
    """

    DEFAULT_BASE_URLS = [
        # este resolve no seu DNS
        "https://opendatasus.saude.gov.br",
        # alguns redirects caem aqui
        "https://dadosabertos.saude.gov.br",
        # (não incluir ckan-dadosabertos... pq não resolve no seu DNS)
    ]

    def __init__(self, base_url: Optional[str] = None):
        self.base_urls = [base_url] if base_url else list(self.DEFAULT_BASE_URLS)
        self.base_url: Optional[str] = None
        self.api: Optional[str] = None

    async def _ensure_api(self) -> None:
        if self.api:
            return

        last_err: Optional[Exception] = None

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        ) as client:
            for b in self.base_urls:
                b = (b or "").rstrip("/")
                if not b:
                    continue

                api = f"{b}/api/3/action"

                try:
                    r = await client.get(f"{api}/status_show")
                    if r.status_code == 200:
                        js = r.json()
                        if js.get("success") is True:
                            self.base_url = b
                            self.api = api
                            return
                    last_err = RuntimeError(f"{b} status_show retornou {r.status_code}")
                except Exception as e:
                    last_err = e

        raise RuntimeError(
            "Não encontrei um host CKAN funcional via /api/3/action/status_show. "
            f"Tentados: {self.base_urls}. Último erro: {last_err}"
        )

    async def package_show(self, dataset_id_or_name: str) -> Dict[str, Any]:
        await self._ensure_api()
        assert self.api is not None

        url = f"{self.api}/package_show"

        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        ) as client:
            r = await client.get(url, params={"id": dataset_id_or_name})
            r.raise_for_status()
            payload = r.json()

        if not payload.get("success"):
            raise RuntimeError(f"CKAN package_show failed: {payload}")
        return payload["result"]

    async def list_resources(self, dataset_id_or_name: str) -> List[CkanResource]:
        pkg = await self.package_show(dataset_id_or_name)
        out: List[CkanResource] = []
        for res in pkg.get("resources", []):
            out.append(
                CkanResource(
                    id=str(res.get("id") or ""),
                    name=str(res.get("name") or ""),
                    format=str(res.get("format") or "").upper(),
                    url=str(res.get("url") or ""),
                )
            )
        return out

    async def find_resource_url(
        self,
        dataset_id_or_name: str,
        *,
        must_contain: List[str],
        prefer_format: Optional[str] = "CSV",
    ) -> str:
        resources = await self.list_resources(dataset_id_or_name)

        def score(r: CkanResource) -> int:
            s = 0
            name = (r.name or "").lower()
            url = (r.url or "").lower()

            for tok in must_contain:
                t = tok.lower()
                if t in name:
                    s += 5
                if t in url:
                    s += 3

            if prefer_format and r.format.upper() == prefer_format.upper():
                s += 2

            return s

        resources.sort(key=score, reverse=True)
        best = resources[0] if resources else None

        if not best or score(best) <= 0:
            top = [(r.format, r.name, r.url) for r in resources[:10]]
            raise RuntimeError(
                f"Não achei resource em '{dataset_id_or_name}' com must_contain={must_contain}. "
                f"Top candidates={top}"
            )

        return best.url