from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_v2 import RawSinan
from app.models import RawSivepGripe

from app.collectors.demas.client import DemasClient
from app.collectors.demas.collector import DemasCollector
from app.normalizers.demas.base import DemasNormalizer


SessionFactory = Callable[[], AsyncSession]


def _to_date(value: Any) -> date | None:
    """
    Converte campos comuns em date.
    Aceita: date/datetime, ISO string 'YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM:SS'
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            # ISO date
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def _hash_raw(payload: dict[str, Any]) -> str:
    # hash estável do raw (ordenando chaves)
    import json
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()


class DemasService:
    """
    - Coleta no DEMAS
    - Normaliza (mínimo)
    - Persiste em tabelas RAW v2 (staging) SEM depender de repository externo
    """

    def __init__(
        self,
        *,
        client: DemasClient,
        collector: DemasCollector,
        normalizer: DemasNormalizer,
        session_factory: SessionFactory,
    ):
        self.client = client
        self.collector = collector
        self.normalizer = normalizer
        self.session_factory = session_factory

    async def sync_dataset(
        self,
        *,
        path: str,
        disease: str,
        params: dict[str, Any] | None = None,
        geo_basis_default: str = "notificacao",
    ) -> dict[str, Any]:
        raw_rows = await self.collector.collect_all(path, params=params)

        normalized = [self.normalizer.normalize(r, disease=disease) for r in raw_rows]

        # decide a tabela RAW alvo por disease/dataset
        # (por enquanto: arboviroses -> RawSinan, srag -> RawSivepGripe)
        if disease in {"dengue", "chikungunya", "zika"}:
            saved = await self._save_raw_sinan(normalized, disease=disease, geo_basis_default=geo_basis_default)
            target = "raw_sinan"
        elif disease in {"srag"}:
            saved = await self._save_raw_sivep(normalized, disease=disease, geo_basis_default=geo_basis_default)
            target = "raw_sivep_gripe"
        else:
            # pode estender depois (sim, sinasc etc)
            return {
                "source": "demas",
                "dataset": disease,
                "target": None,
                "fetched": len(raw_rows),
                "normalized": len(normalized),
                "saved": 0,
                "warning": f"dataset '{disease}' ainda sem destino RAW configurado",
            }

        return {
            "source": "demas",
            "dataset": disease,
            "target": target,
            "fetched": len(raw_rows),
            "normalized": len(normalized),
            "saved": saved,
        }

    async def _save_raw_sinan(self, rows: list[dict[str, Any]], *, disease: str, geo_basis_default: str) -> int:
        to_insert: list[dict[str, Any]] = []

        for r in rows:
            raw = r.get("raw") or {}
            h = _hash_raw(raw)

            ref_date = _to_date(r.get("date_event")) or _to_date(raw.get("data")) or date.today()
            municipio = r.get("geocode") or raw.get("codigo_municipio") or raw.get("CO_MUNICIPIO") or ""
            municipio = str(municipio) if municipio is not None else ""

            geo_basis = r.get("geo_basis") or geo_basis_default

            year = ref_date.year

            to_insert.append(
                {
                    "year": year,
                    "ref_date": ref_date,
                    "geo_basis": geo_basis,
                    "municipio_ibge": municipio,
                    "disease": disease,
                    "external_id": r.get("external_id"),
                    "raw": raw,
                    "hash": h,
                }
            )

        if not to_insert:
            return 0

        async with self.session_factory() as session:
            stmt = pg_insert(RawSinan).values(to_insert)
            # idempotência: não duplica pelo hash+geo_basis (constraint uq_raw_sinan_hash)
            stmt = stmt.on_conflict_do_nothing(index_elements=["geo_basis", "hash"])
            result = await session.execute(stmt)
            await session.commit()
            # rowcount em ON CONFLICT pode variar; mas geralmente funciona bem
            return int(getattr(result, "rowcount", 0) or 0)

    async def _save_raw_sivep(self, rows: list[dict[str, Any]], *, disease: str, geo_basis_default: str) -> int:
        to_insert: list[dict[str, Any]] = []

        for r in rows:
            raw = r.get("raw") or {}
            h = _hash_raw(raw)

            ref_date = _to_date(r.get("date_event")) or _to_date(raw.get("data")) or date.today()
            municipio = r.get("geocode") or raw.get("codigo_municipio") or raw.get("CO_MUNICIPIO") or ""
            municipio = str(municipio) if municipio is not None else ""

            geo_basis = r.get("geo_basis") or geo_basis_default

            year = ref_date.year

            to_insert.append(
                {
                    "year": year,
                    "ref_date": ref_date,
                    "geo_basis": geo_basis,
                    "municipio_ibge": municipio,
                    "disease": disease,
                    "external_id": r.get("external_id"),
                    "raw": raw,
                    "hash": h,
                }
            )

        if not to_insert:
            return 0

        async with self.session_factory() as session:
            stmt = pg_insert(RawSivepGripe).values(to_insert)
            stmt = stmt.on_conflict_do_nothing(index_elements=["geo_basis", "hash"])
            result = await session.execute(stmt)
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)