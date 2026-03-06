# app/services/demas_service.py
from __future__ import annotations
import json
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert
from app.collectors.demas.client import DemasClient
from app.collectors.demas.collector import DemasCollector
from app.demas_models import DemasRaw, DemasEvent, DemasMunicipioDim
from app.normalizers.demas.normalizer import DemasNormalizer

def _hash_payload(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()

@dataclass(frozen=True)
class DemasDataset:
    key: str
    path: str
    uses_year: bool = False
    kind: str = "events"

DEMAS_DATASETS: list[DemasDataset] = [
    DemasDataset("arboviroses_dengue", "/arboviroses/dengue", uses_year=True, kind="events"),
    DemasDataset("arboviroses_chikungunya", "/arboviroses/chikungunya", uses_year=True, kind="events"),
    DemasDataset("arboviroses_zikavirus", "/arboviroses/zikavirus", uses_year=True, kind="events"),
    DemasDataset(
        "arboviroses_febre_amarela",
        "/arboviroses/febre-amarela-humanos-primatas-nao-humanos",
        uses_year=True,
        kind="events",
    ),
    DemasDataset("sg_2020", "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-2020", kind="events"),
    DemasDataset("sg_2021", "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-2021", kind="events"),
    DemasDataset("sg_2022", "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-2022", kind="events"),
    DemasDataset("sg_2023", "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-2023", kind="events"),
    DemasDataset("sg_2024", "/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-2024", kind="events"),
    DemasDataset("srag_2019_2026", "/vigilancia-e-meio-ambiente/srag-2019-2026", kind="events"),
    DemasDataset("macrorregiao_municipio", "/macrorregiao-e-regiao-de-saude/municipio", kind="dim"),
    DemasDataset("cnes_estabelecimentos", "/v1/cnes/estabelecimentos", kind="raw_only"),
]

class DemasSyncService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        base_url: str,
        timeout_seconds: int = 60,
        limit: int = 20,
        sleep_seconds: float = 0.05,
        arboviroses_years: list[int] | None = None,
        dataset_deadline_seconds: int = 25,
        raw_chunk_size: int = 500,
        events_chunk_size: int = 500,
    ):
        self.session_factory = session_factory
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.limit = limit
        self.sleep_seconds = sleep_seconds
        self.arboviroses_years = arboviroses_years or [2024, 2025, 2026]
        self.dataset_deadline_seconds = dataset_deadline_seconds
        self.raw_chunk_size = raw_chunk_size
        self.events_chunk_size = events_chunk_size
        self.client = DemasClient(base_url=self.base_url, timeout_seconds=self.timeout_seconds)
        self.collector = DemasCollector(client=self.client, limit=self.limit)
        self.normalizer = DemasNormalizer()
        self.datasets_daily = [d for d in DEMAS_DATASETS if d.kind != "dim"]

    def _dataset_by_key(self, key: str) -> DemasDataset | None:
        return next((d for d in DEMAS_DATASETS if d.key == key), None)

    async def _collect_items_for_dataset(self, ds: DemasDataset, *, year: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if ds.uses_year and year is not None:
            params["nu_ano"] = str(year)

        if ds.key.startswith("cnes_") and ds.path.startswith("/v1/"):
            try:
                return await self.collector.collect_all(ds.path, params=params)
            except Exception:
                alt = ds.path.replace("/v1/", "/")
                return await self.collector.collect_all(alt, params=params)

        return await self.collector.collect_all(ds.path, params=params)

    async def _flush_raw_batch(self, session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[int, int]:
        """
        ✅ bulk insert com RETURNING pra contar inseridos vs duplicados.
        """
        stmt = (
            insert(DemasRaw)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_demas_raw_endpoint_hash")
            .returning(DemasRaw.id)
        )
        res = await session.execute(stmt)
        inserted = res.scalars().all()
        s = len(inserted)
        d = max(0, len(rows) - s)
        return s, d

    async def sync_dataset_raw(self, ds: DemasDataset, *, chunk_size: int | None = None) -> dict[str, Any]:
        """
        ✅ Ajustado: em vez de inserir 1 a 1, faz bulk insert em chunks (muito mais rápido).
        """
        fetched = 0
        saved = 0
        duplicates = 0
        chunk_size = chunk_size or self.raw_chunk_size

        async with self.session_factory() as session:
            years: Iterable[int | None] = self.arboviroses_years if ds.uses_year else [None]

            for y in years:
                items = await self._collect_items_for_dataset(ds, year=y)
                fetched += len(items)

                batch: list[dict[str, Any]] = []
                now = datetime.now(timezone.utc)

                for it in items:
                    h = _hash_payload(it)
                    batch.append(
                        {
                            "endpoint_name": ds.key,
                            "request_year": y,
                            "request_limit": self.limit,
                            "request_offset": None,
                            "record_hash": h,
                            "payload": it,
                            "collected_at": now,
                        }
                    )

                    if len(batch) >= chunk_size:
                        s, d = await self._flush_raw_batch(session, batch)
                        saved += s
                        duplicates += d
                        batch = []

                    if self.sleep_seconds:
                        await asyncio.sleep(self.sleep_seconds)

                if batch:
                    s, d = await self._flush_raw_batch(session, batch)
                    saved += s
                    duplicates += d

            await session.commit()

        return {"dataset": ds.key, "fetched": fetched, "saved": saved, "duplicates": duplicates}

    async def normalize_dataset_events(self, ds: DemasDataset, *, chunk_size: int | None = None) -> dict[str, Any]:
        """
        ✅ Ajustado: normaliza em chunks (por id) + tolera falhas item-a-item + bulk insert.
        """
        if ds.kind != "events":
            return {"dataset": ds.key, "skipped": True, "reason": f"kind={ds.kind}"}

        normalized = 0
        saved = 0
        duplicates = 0
        failed = 0
        chunk_size = chunk_size or self.events_chunk_size
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            last_id = 0

            while True:
                q = (
                    select(DemasRaw)
                    .where(DemasRaw.endpoint_name == ds.key, DemasRaw.id > last_id)
                    .order_by(DemasRaw.id.asc())
                    .limit(chunk_size)
                )
                rows = (await session.execute(q)).scalars().all()
                if not rows:
                    break

                last_id = rows[-1].id

                batch: list[dict[str, Any]] = []
                for r in rows:
                    try:
                        ev = self.normalizer.normalize_event(dataset_key=ds.key, item=r.payload)
                        normalized += 1
                        batch.append(
                            {
                                "dataset": ev["dataset"],
                                "event_date": ev["event_date"],
                                "epiweek": ev["epiweek"],
                                "year": ev["year"],
                                "uf": ev["uf"],
                                "municipio_ibge": ev["municipio_ibge"],
                                "municipio_nome": ev["municipio_nome"],
                                "fingerprint": ev["fingerprint"],
                                "payload": ev["payload"],
                                "normalized_at": now,
                            }
                        )
                    except Exception:
                        failed += 1

                if batch:
                    stmt = (
                        insert(DemasEvent)
                        .values(batch)
                        .on_conflict_do_nothing(constraint="uq_demas_events_dataset_fp")
                        .returning(DemasEvent.id)
                    )
                    res = await session.execute(stmt)
                    inserted = res.scalars().all()
                    s = len(inserted)
                    d = max(0, len(batch) - s)
                    saved += s
                    duplicates += d

            await session.commit()

        return {
            "dataset": ds.key,
            "normalized": normalized,
            "saved": saved,
            "duplicates": duplicates,
            "failed": failed,
        }

    async def sync_municipios_dim(self) -> dict[str, Any]:
        ds = self._dataset_by_key("macrorregiao_municipio")
        if not ds:
            return {"ok": False, "reason": "dataset macrorregiao_municipio não existe"}

        items = await self._collect_items_for_dataset(ds)
        upserted = 0

        async with self.session_factory() as session:
            for it in items:
                municipio_ibge = str(
                    it.get("municipio_ibge")
                    or it.get("codigo_municipio")
                    or it.get("id_municip")
                    or it.get("id_mn_resi")
                    or ""
                ).strip()
                if not municipio_ibge:
                    continue

                row = {
                    "municipio_ibge": municipio_ibge,
                    "municipio_nome": it.get("municipio_nome") or it.get("nome_municipio") or it.get("nm_municip"),
                    "uf": it.get("uf") or it.get("sg_uf"),
                    "regiao_saude_codigo": it.get("regiao_saude_codigo") or it.get("regiao_codigo"),
                    "regiao_saude_nome": it.get("regiao_saude_nome") or it.get("regiao_nome"),
                    "macrorregiao_codigo": it.get("macrorregiao_codigo"),
                    "macrorregiao_nome": it.get("macrorregiao_nome"),
                    "updated_at": datetime.now(timezone.utc),
                }

                stmt = (
                    insert(DemasMunicipioDim)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=[DemasMunicipioDim.municipio_ibge],
                        set_={k: row[k] for k in row.keys() if k != "municipio_ibge"},
                    )
                )
                await session.execute(stmt)
                upserted += 1

            await session.commit()

        return {"dataset": ds.key, "fetched": len(items), "upserted": upserted}

    async def sync_dataset(self, ds: DemasDataset) -> dict[str, Any]:
        raw_res = await self.sync_dataset_raw(ds)

        if ds.kind == "events":
            ev_res = await self.normalize_dataset_events(ds)
            return {"raw": raw_res, "events": ev_res}

        if ds.kind == "dim":
            dim_res = await self.sync_municipios_dim()
            return {"raw": raw_res, "dim": dim_res}

        return {"raw": raw_res, "note": "raw_only"}

    async def sync_all_daily(self) -> dict[str, Any]:
        """
        ✅ Circuit breaker + deadline por dataset.
        Se DEMAS estiver ruim (502/timeout), retorna rápido sem travar 49 min.
        """
        # 1) ping rápido (2–3s de custo)
        ping = await self.client.ping()
        if not ping.get("ok"):
            return {
                "ok": False,
                "reason": "demas_unreachable",
                "ping": ping,
                "datasets_total": len(self.datasets_daily),
                "datasets_ok": 0,
                "datasets_failed": len(self.datasets_daily),
                "results": [
                    {"dataset": ds.key, "ok": False, "error_type": "DEMAS_DOWN", "error": "ping failed"}
                    for ds in self.datasets_daily
                ],
            }

        results: list[dict[str, Any]] = []

        for ds in self.datasets_daily:
            try:
                res = await asyncio.wait_for(self.sync_dataset(ds), timeout=self.dataset_deadline_seconds)
                results.append({"dataset": ds.key, "ok": True, "result": res})
            except Exception as e:
                results.append({"dataset": ds.key, "ok": False, "error_type": type(e).__name__, "error": str(e)[:300]})

        return {
            "ok": True,
            "datasets_total": len(self.datasets_daily),
            "datasets_ok": sum(1 for r in results if r["ok"]),
            "datasets_failed": sum(1 for r in results if not r["ok"]),
            "results": results,
        }

    async def sync_municipios_weekly(self) -> dict[str, Any]:
        ds = self._dataset_by_key("macrorregiao_municipio")
        if not ds:
            return {"ok": False, "reason": "dataset não encontrado"}
        return await asyncio.wait_for(self.sync_dataset(ds), timeout=self.dataset_deadline_seconds)

    async def stats(self) -> dict[str, Any]:
        async with self.session_factory() as session:
            raw_total = (await session.execute(select(func.count()).select_from(DemasRaw))).scalar_one()
            ev_total = (await session.execute(select(func.count()).select_from(DemasEvent))).scalar_one()
            dim_total = (await session.execute(select(func.count()).select_from(DemasMunicipioDim))).scalar_one()
            return {"raw_total": int(raw_total), "events_total": int(ev_total), "municipios_dim_total": int(dim_total)}

    async def query_raw(self, *, dataset: str, year: int | None, page: int, size: int) -> dict[str, Any]:
        offset = max(page, 0) * max(size, 1)

        async with self.session_factory() as session:
            conds = [DemasRaw.endpoint_name == dataset]
            if year is not None:
                conds.append(DemasRaw.request_year == year)

            total = (await session.execute(select(func.count()).select_from(DemasRaw).where(and_(*conds)))).scalar_one()

            q = (
                select(DemasRaw)
                .where(and_(*conds))
                .order_by(DemasRaw.id.desc())
                .offset(offset)
                .limit(size)
            )
            rows = (await session.execute(q)).scalars().all()

        return {
            "page": page,
            "size": size,
            "total_items": int(total),
            "items": [
                {
                    "id": r.id,
                    "dataset": r.endpoint_name,
                    "request_year": r.request_year,
                    "record_hash": r.record_hash,
                    "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                    "payload": r.payload,
                }
                for r in rows
            ],
        }

    async def query_events(
        self,
        *,
        dataset: str,
        date_from: str | None,
        date_to: str | None,
        uf: str | None,
        municipio_ibge: str | None,
        page: int,
        size: int,
    ) -> dict[str, Any]:
        offset = max(page, 0) * max(size, 1)

        async with self.session_factory() as session:
            conds = [DemasEvent.dataset == dataset]

            if uf:
                conds.append(DemasEvent.uf == uf)

            if municipio_ibge:
                conds.append(DemasEvent.municipio_ibge == municipio_ibge)

            if date_from:
                conds.append(DemasEvent.event_date >= date_from)
            if date_to:
                conds.append(DemasEvent.event_date <= date_to)

            total = (await session.execute(select(func.count()).select_from(DemasEvent).where(and_(*conds)))).scalar_one()

            q = (
                select(DemasEvent)
                .where(and_(*conds))
                .order_by(DemasEvent.event_date.desc(), DemasEvent.id.desc())
                .offset(offset)
                .limit(size)
            )
            rows = (await session.execute(q)).scalars().all()

        return {
            "page": page,
            "size": size,
            "total_items": int(total),
            "items": [
                {
                    "id": r.id,
                    "dataset": r.dataset,
                    "event_date": r.event_date.isoformat() if r.event_date else None,
                    "epiweek": r.epiweek,
                    "year": r.year,
                    "uf": r.uf,
                    "municipio_ibge": r.municipio_ibge,
                    "municipio_nome": r.municipio_nome,
                    "fingerprint": r.fingerprint,
                    "payload": r.payload,
                }
                for r in rows
            ],
        }