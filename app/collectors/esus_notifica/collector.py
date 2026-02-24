from __future__ import annotations

from typing import Any

from app.collectors.esus_notifica.client import EsusNotificaClient


class EsusNotificaCollector:
    def __init__(self, client: EsusNotificaClient, *, page_size: int = 200, max_pages: int = 20):
        self.client = client
        self.page_size = page_size
        self.max_pages = max_pages

    @staticmethod
    def build_index(uf: str | None) -> str:
        """
        No portal:
          desc-esus-notifica-estado-*/_search
          ou desc-esus-notifica-estado-rj/_search
        """
        if uf:
            return f"desc-esus-notifica-estado-{uf.lower()}"
        return "desc-esus-notifica-estado-*"

    @staticmethod
    def build_query(
        *,
        uf: str | None,
        date_from: str | None,
        date_to: str | None,
        size: int,
        offset: int,
    ) -> dict[str, Any]:
        """
        Filtro por dataNotificacao (mais comum).
        Se o mapeamento do índice usar outro nome, ajuste aqui.
        """
        filters: list[dict[str, Any]] = []

        # alguns índices têm UF em campos variados; como a UF já está no índice, isso é opcional
        if uf:
            # mantemos como "should" para não travar caso campo não exista
            filters.append({"bool": {"should": [{"term": {"estado": uf.upper()}}, {"term": {"uf": uf.upper()}}], "minimum_should_match": 1}})

        if date_from or date_to:
            rng: dict[str, Any] = {}
            if date_from:
                rng["gte"] = date_from
            if date_to:
                rng["lte"] = date_to
            filters.append({"range": {"dataNotificacao": rng}})

        query: dict[str, Any] = {
            "from": offset,
            "size": size,
            "_source": True,
            "track_total_hits": True,
            # sort simples para estabilidade
            "sort": [{"dataNotificacao": "desc"}],
            "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        }
        return query

    async def collect(
        self,
        *,
        uf: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Paginação simples via from/size (bom para janelas pequenas).
        Para janelas enormes, o ideal seria search_after/scroll; deixei simples e seguro.
        """
        index = self.build_index(uf)

        all_hits: list[dict[str, Any]] = []
        offset = 0

        for _ in range(self.max_pages):
            q = self.build_query(uf=uf, date_from=date_from, date_to=date_to, size=self.page_size, offset=offset)
            data = await self.client.search(index=index, query=q)

            hits = (((data or {}).get("hits") or {}).get("hits")) or []
            if not hits:
                break

            all_hits.extend(hits)

            # se veio menos que o page_size, acabou
            if len(hits) < self.page_size:
                break

            offset += self.page_size

        return all_hits