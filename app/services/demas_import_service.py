# app/services/demas_import_service.py
from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.demas_models import DemasRaw, DemasEvent
from app.normalizers.demas.normalizer import DemasNormalizer
from app.services.demas_sources import DemasSource

from app.db_bulk import save_raw_debug_find_bad_row_on_conflict


def _hash_payload(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()


def _decode_bytes(content: bytes) -> str:
    # CSV do governo frequentemente vem em latin-1 ou utf-8-sig
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")


def _sniff_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t,")
    except Exception:
        class Default(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return Default()


def _iter_csv_dicts(text: str) -> Iterable[dict[str, Any]]:
    cleaned = text.replace("\x00", "")
    buf = io.StringIO(cleaned)

    pos = buf.tell()
    sample = buf.read(8192)
    buf.seek(pos)

    dialect = _sniff_dialect(sample)
    reader = csv.DictReader(buf, dialect=dialect)

    for row in reader:
        if not row:
            continue
        out: dict[str, Any] = {}
        for k, v in row.items():
            if k is None:
                continue
            kk = str(k).strip()
            if kk == "":
                continue
            if v is None:
                out[kk] = None
            else:
                vv = str(v).strip()
                out[kk] = vv if vv != "" else None
        if out:
            yield out


def _extract_csvs_from_zip(content: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.lower().endswith(".csv"):
                out.append((name, z.read(name)))
    return out


@dataclass
class DemasCsvImportResult:
    dataset: str
    fetched: int
    saved: int
    duplicates: int
    normalized: int | None = None
    events_saved: int | None = None
    events_duplicates: int | None = None
    events_failed: int | None = None  # ✅ novo


class DemasImportService:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.normalizer = DemasNormalizer()

    # -------------------------
    # Opção 2: local/upload (CSV/ZIP)
    # -------------------------
    async def import_csv_or_zip(
        self,
        *,
        dataset_key: str,
        filename: str,
        content: bytes,
        request_year: int | None = None,
        chunk_size: int = 100,
        normalize_events: bool = True,
    ) -> DemasCsvImportResult:
        dataset_key = dataset_key.strip()

        # 1) extrai arquivos (csv único ou zip com vários csv)
        files: list[tuple[str, bytes]]
        if filename.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(content)):
            files = _extract_csvs_from_zip(content)
            if not files:
                raise ValueError("ZIP não contém nenhum .csv")
        else:
            files = [(filename, content)]

        fetched = 0
        saved = 0
        duplicates = 0
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            # 2) importa raw em lotes
            for (_csv_name, csv_bytes) in files:
                text = _decode_bytes(csv_bytes)

                batch: list[dict[str, Any]] = []
                for row in _iter_csv_dicts(text):
                    fetched += 1
                    h = _hash_payload(row)
                    batch.append(
                        {
                            "endpoint_name": dataset_key,
                            "request_year": request_year,
                            "request_limit": None,
                            "request_offset": None,
                            "record_hash": h,
                            "payload": row,
                            "collected_at": now,
                        }
                    )

                    if len(batch) >= chunk_size:
                        s, d = await self._flush_raw(session, batch)
                        saved += s
                        duplicates += d
                        batch = []

                if batch:
                    s, d = await self._flush_raw(session, batch)
                    saved += s
                    duplicates += d

            await session.commit()

        result = DemasCsvImportResult(
            dataset=dataset_key,
            fetched=fetched,
            saved=saved,
            duplicates=duplicates,
        )

        if normalize_events:
            norm = await self.normalize_dataset_events(dataset_key=dataset_key, chunk_size=chunk_size)
            result.normalized = norm["normalized"]
            result.events_saved = norm["saved"]
            result.events_duplicates = norm["duplicates"]
            result.events_failed = norm["failed"]

        return result

    async def _flush_raw(self, session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[int, int]:
        """
        Inserção RAW tolerante a duplicados e com debug 1-a-1 quando o bulk quebra.
        - Duplicados: ON CONFLICT DO NOTHING por (endpoint_name, record_hash) via constraint uq_demas_raw_endpoint_hash
        - Erros reais (tipos/JSON/data/etc): tenta achar a row ruim e levanta RuntimeError com a row.
        """
        if not rows:
            return (0, 0)

        # Primeiro tenta o caminho rápido (se funcionar, ótimo)
        stmt = (
            insert(DemasRaw)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_demas_raw_endpoint_hash")
            .returning(DemasRaw.id)
        )

        try:
            res = await session.execute(stmt)
            inserted = res.scalars().all()
            s = len(inserted)
            d = max(0, len(rows) - s)
            return s, d
        except Exception:
            # Cai pro modo debug 1-a-1, MAS mantendo ON CONFLICT DO NOTHING
            # Precisamos usar index_elements (colunas) aqui, porque a versão pg_insert com constraint
            # não está exposta nesse helper; então passamos as colunas equivalentes ao unique constraint.
            inserted_count = await save_raw_debug_find_bad_row_on_conflict(
                session,
                DemasRaw,
                rows,
                chunk_size=200,
                conflict_cols=["endpoint_name", "record_hash"],
            )
            s = int(inserted_count)
            d = max(0, len(rows) - s)
            return s, d

    async def _flush_events(self, session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[int, int]:
        """
        Mesmo padrão do RAW, agora pros eventos.
        """
        if not rows:
            return (0, 0)

        stmt = (
            insert(DemasEvent)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_demas_events_dataset_fp")
            .returning(DemasEvent.id)
        )

        try:
            res = await session.execute(stmt)
            inserted = res.scalars().all()
            s = len(inserted)
            d = max(0, len(rows) - s)
            return s, d
        except Exception:
            inserted_count = await save_raw_debug_find_bad_row_on_conflict(
                session,
                DemasEvent,
                rows,
                chunk_size=200,
                conflict_cols=["dataset", "fingerprint"],
            )
            s = int(inserted_count)
            d = max(0, len(rows) - s)
            return s, d

    # -------------------------
    # ✅ Normalização em chunks + tolerante a falhas
    # -------------------------
    async def normalize_dataset_events(self, *, dataset_key: str, chunk_size: int = 500) -> dict[str, Any]:
        normalized = 0
        saved = 0
        duplicates = 0
        failed = 0
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            last_id = 0

            while True:
                q = (
                    select(DemasRaw)
                    .where(DemasRaw.endpoint_name == dataset_key, DemasRaw.id > last_id)
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
                        ev = self.normalizer.normalize_event(dataset_key=dataset_key, item=r.payload)
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
                    s, d = await self._flush_events(session, batch)
                    saved += s
                    duplicates += d

            await session.commit()

        return {
            "dataset": dataset_key,
            "normalized": normalized,
            "saved": saved,
            "duplicates": duplicates,
            "failed": failed,
        }

    # -------------------------
    # Opção 3: baixar de URL (S3/HTTP) e importar
    # -------------------------
    async def import_from_url(
        self,
        *,
        dataset_key: str,
        url: str,
        request_year: int | None = None,
        normalize_events: bool = True,
        timeout_seconds: int = 600,
        chunk_size: int = 100,
    ) -> DemasCsvImportResult:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=30.0, read=timeout_seconds),
            follow_redirects=True,
            headers={"Accept": "*/*"},
            trust_env=False,  # importante em Windows/corp
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.content

        filename = url.split("?")[0].split("/")[-1] or "download"
        return await self.import_csv_or_zip(
            dataset_key=dataset_key,
            filename=filename,
            content=content,
            request_year=request_year,
            normalize_events=normalize_events,
            chunk_size=chunk_size,
        )

    # -------------------------
    # Bulk a partir de fontes (DEMAS_S3_SOURCES)
    # -------------------------
    async def import_bulk_from_sources(
        self,
        *,
        sources: list[DemasSource],
        timeout_seconds: int = 600,
        chunk_size: int = 100,
    ) -> dict:
        results: list[dict] = []
        ok = 0
        failed = 0

        for s in sources:
            try:
                res = await self.import_from_url(
                    dataset_key=s.key,
                    url=s.url,
                    request_year=s.request_year,
                    normalize_events=s.normalize_events,
                    timeout_seconds=timeout_seconds,
                    chunk_size=chunk_size,
                )
                results.append(
                    {
                        "dataset": s.key,
                        "ok": True,
                        "url": s.url,
                        "fetched": res.fetched,
                        "saved": res.saved,
                        "duplicates": res.duplicates,
                        "normalized": res.normalized,
                        "events_saved": res.events_saved,
                        "events_duplicates": res.events_duplicates,
                        "events_failed": res.events_failed,
                    }
                )
                ok += 1
            except Exception as e:
                results.append(
                    {
                        "dataset": s.key,
                        "ok": False,
                        "url": s.url,
                        "error_type": type(e).__name__,
                        "error": str(e)[:500],
                    }
                )
                failed += 1

        return {
            "ok": failed == 0,
            "datasets_total": len(sources),
            "datasets_ok": ok,
            "datasets_failed": failed,
            "results": results,
        }