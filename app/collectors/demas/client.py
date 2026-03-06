# app/collectors/demas/client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import asyncio
import httpx

@dataclass
class DemasClient:
    """
    DEMAS (apidadosabertos.saude.gov.br)
      - Sem token/login (na prática, vários endpoints públicos)
      - Paginação: limit + offset
      - Fail-fast quando upstream/proxy do DEMAS está ruim (502/503/504)
    """
    base_url: str = "https://apidadosabertos.saude.gov.br"
    timeout_seconds: int = 60

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")

    def _make_http(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            timeout=min(self.timeout_seconds, 20),
            connect=5.0,
            read=min(self.timeout_seconds, 15),
            write=10.0,
            pool=5.0,
        )
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            limits=limits,
            headers={"Accept": "application/json"},
            follow_redirects=True,
            trust_env=False,
        )

    async def ping(self) -> dict[str, Any]:
        """
        Ping rápido e mais fiel: chama um endpoint leve do DEMAS com limit=1.
        Se isso falhar, tratamos como DEMAS indisponível.
        """
        async with self._make_http() as http:
            try:
                r = await http.get(
                    "/macrorregiao-e-regiao-de-saude/municipio",
                    params={"limit": 1, "offset": 0},
                )
                if r.status_code in (502, 503, 504):
                    return {"ok": False, "status_code": r.status_code, "error_type": "UpstreamBadGateway"}
                r.raise_for_status()
                return {"ok": True, "status_code": r.status_code}
            except Exception as e:
                return {"ok": False, "error_type": type(e).__name__, "error": str(e)[:200]}

    async def _get_with_retries(self, http: httpx.AsyncClient, path: str, params: dict[str, Any]) -> Any:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = await http.get(path, params=params)
                if r.status_code in (502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"Upstream instável ({r.status_code})",
                        request=r.request,
                        response=r,
                    )
                r.raise_for_status()
                return r.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_err = e
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code in (502, 503, 504):
                    raise
                last_err = e
            except httpx.HTTPError as e:
                last_err = e

            await asyncio.sleep(0.25 * (attempt + 1))

        raise last_err or httpx.HTTPError("Falha ao chamar DEMAS")

    async def iter_items(
        self,
        path: str,
        *,
        base_params: dict[str, Any] | None = None,
        limit: int = 20,
        start_offset: int = 0,
        max_pages: int = 200,
        list_keys: tuple[str, ...] = ("parametros", "items", "data", "results", "macrorregiao_regiao_saude_municipios"),
        hard_deadline_seconds: int = 20,
    ) -> AsyncIterator[dict[str, Any]]:
        base_params = dict(base_params or {})
        offset = int(base_params.pop("offset", start_offset))

        async with self._make_http() as http:
            for _ in range(max_pages):
                params = dict(base_params)
                params["limit"] = int(limit)
                params["offset"] = int(offset)

                data = await asyncio.wait_for(
                    self._get_with_retries(http, path, params),
                    timeout=hard_deadline_seconds,
                )

                if isinstance(data, list):
                    if not data:
                        return
                    for item in data:
                        yield item if isinstance(item, dict) else {"value": item}
                    return

                if not isinstance(data, dict):
                    return

                items: list[Any] | None = None
                for k in list_keys:
                    v = data.get(k)
                    if isinstance(v, list):
                        items = v
                        break

                if items is None:
                    for v in data.values():
                        if isinstance(v, list):
                            items = v
                            break

                if not items:
                    return

                for item in items:
                    yield item if isinstance(item, dict) else {"value": item}

                if len(items) < limit:
                    return

                offset += 1