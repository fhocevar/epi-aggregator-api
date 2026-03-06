from __future__ import annotations
from typing import Callable
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RawSivepGripe
from app.collectors.esus_notifica.client import EsusNotificaClient
from app.collectors.esus_notifica.collector import EsusNotificaCollector
from app.normalizers.esus_notifica.base import EsusNotificaNormalizer
from app.db_bulk import bulk_insert_on_conflict_do_nothing_chunked

SessionFactory = Callable[[], AsyncSession]

class EsusNotificaService:
    def __init__(
        self,
        *,
        client: EsusNotificaClient,
        collector: EsusNotificaCollector,
        normalizer: EsusNotificaNormalizer,
        session_factory: SessionFactory,
    ):
        self.client = client
        self.collector = collector
        self.normalizer = normalizer
        self.session_factory = session_factory

    async def sync(
        self,
        *,
        uf: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        geo_basis: str = "notificacao",
        disease: str = "srag",
        chunk_size: int = 2000,
    ) -> dict:
        hits = await self.collector.collect(uf=uf, date_from=date_from, date_to=date_to)

        rows = [
            self.normalizer.normalize_raw_sivep_v2(h, geo_basis=geo_basis, disease=disease)
            for h in hits
        ]

        saved = await self._save_raw_chunked(rows, chunk_size=chunk_size)

        return {
            "source": "esus_notifica",
            "index": self.collector.build_index(uf),
            "fetched": len(hits),
            "normalized": len(rows),
            "attempted": len(rows),
            "saved": saved,
            "duplicates": len(rows) - saved,
            "chunk_size": chunk_size,
        }

    async def _save_raw_chunked(self, rows: list[dict], *, chunk_size: int = 500) -> int:
        if not rows:
            return 0

        async with self.session_factory() as session:
            inserted = await bulk_insert_on_conflict_do_nothing_chunked(
                session=session,
                model_or_table=RawSivepGripe,
                rows=rows,
                chunk_size=chunk_size,
                conflict_cols=["geo_basis", "hash"],
            )
            await session.commit()
            return inserted