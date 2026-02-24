from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


@dataclass
class DemasClient:
    base_url: str
    timeout_seconds: int = 60
    token: str | None = None
    username: str | None = None
    password: str | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds, headers=headers)

    async def login_if_needed(self) -> None:
        """
        Login só se não tiver token e tiver user/pass.
        OBS: o payload exato pode variar; deixei bem tolerante.
        Se seu swagger mostrar outro formato, é só ajustar aqui.
        """
        if self.token or not (self.username and self.password):
            return

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as http:
            # endpoint mostrado no swagger: POST /autenticacao/login
            payload_variants = [
                {"login": self.username, "senha": self.password},
                {"username": self.username, "password": self.password},
                {"usuario": self.username, "senha": self.password},
            ]

            last_err: Exception | None = None
            for payload in payload_variants:
                try:
                    r = await http.post("/autenticacao/login", json=payload, headers={"Accept": "application/json"})
                    r.raise_for_status()
                    data = r.json()

                    # tenta achar token nos lugares mais comuns
                    token = (
                        data.get("access_token")
                        or data.get("token")
                        or data.get("accessToken")
                        or (data.get("data") or {}).get("access_token")
                        or (data.get("data") or {}).get("token")
                    )
                    if not token:
                        raise ValueError(f"Login OK mas não achei token no JSON: keys={list(data.keys())}")

                    self.token = token
                    return
                except Exception as e:
                    last_err = e

            raise RuntimeError(f"Falha no login DEMAS. Último erro: {last_err}")

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self.login_if_needed()
        async with await self._get_http() as http:
            r = await http.get(path, params=params)
            r.raise_for_status()
            return r.json()

    async def iter_items(
        self,
        path: str,
        base_params: dict[str, Any] | None = None,
        page_size: int = 1000,
        max_pages: int = 10_000,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Itera em resultados com paginação.
        Compatível com respostas:
          - {"items":[...], "page":1, "size":50, "total_items":123}
          - lista direta [...]
          - {"data":[...]} / {"results":[...]}
        Parâmetros de página variam; usamos 'page' e 'size' e também tentamos 'pagina' e 'tamanho'.
        """
        await self.login_if_needed()

        base_params = dict(base_params or {})
        page = 1

        async with await self._get_http() as http:
            for _ in range(max_pages):
                params = dict(base_params)

                # tenta os formatos mais comuns
                params.setdefault("page", page)
                params.setdefault("size", page_size)

                r = await http.get(path, params=params)
                r.raise_for_status()
                data = r.json()

                if isinstance(data, list):
                    if not data:
                        return
                    for item in data:
                        if isinstance(item, dict):
                            yield item
                        else:
                            yield {"value": item}
                    return

                if not isinstance(data, dict):
                    return

                items = (
                    data.get("items")
                    or data.get("data")
                    or data.get("results")
                    or data.get("resultado")
                    or []
                )

                if not items:
                    return

                for item in items:
                    if isinstance(item, dict):
                        yield item
                    else:
                        yield {"value": item}

                # heurística de parada:
                # - se veio "total_items" e já passamos do total, para
                total = data.get("total_items") or data.get("total") or data.get("count")
                if total is not None:
                    # se a API for 1-based, page*size >= total encerra
                    if page * page_size >= int(total):
                        return

                # se retornou menos que o page_size, provavelmente acabou
                if isinstance(items, list) and len(items) < page_size:
                    return

                page += 1