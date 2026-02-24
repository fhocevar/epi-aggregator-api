import hashlib
import json
import uuid
from datetime import date
from typing import Any, Dict

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def sha256_dict(d: Dict[str, Any]) -> str:
    raw = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def ingest_sinan(
    db: AsyncSession,
    *,
    geo_basis: str,
    url: str,
    date_from: date,
    date_to: date,
    timeout_sec: int = 60,
    batch_id: str = "sinan-ingest",
) -> int:
    """
    MVP: baixa JSON (lista) e grava em raw_sinan.

    Formato esperado por registro (mínimo):
    {
      "ref_date": "2026-02-01",                 # data de referência da notificação/evento
      "disease": "malaria",                     # id da doença (padronizado por você)
      "municipio_ibge_residencia": "3304557",
      "municipio_ibge_notificacao": "3304557",
      "count": 1,                               # opcional (se já vier agregado)
      ... quaisquer outros campos ...
    }

    Observação: se a fonte real vier agregada (TabNet), você pode usar count.
    Se vier microdado, use count=1 e agregue no normalizer.
    """
    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        raise ValueError("Esperado JSON em lista de registros")

    insert_sql = text("""
    INSERT INTO raw_sinan (
      id, year, ref_date, geo_basis, municipio_ibge, disease,
      external_id, raw, hash
    )
    VALUES (
      :id, :year, :ref_date, :geo_basis, :municipio_ibge, :disease,
      :external_id, :raw::jsonb, :hash
    )
    ON CONFLICT ON CONSTRAINT uq_raw_sinan_hash DO NOTHING;
    """)

    inserted = 0
    for rec in data:
        ref_date_str = rec.get("ref_date")
        disease = rec.get("disease")
        if not ref_date_str or not disease:
            continue

        dref = date.fromisoformat(ref_date_str)
        if dref < date_from or dref > date_to:
            continue

        if geo_basis == "residencia":
            municipio = rec.get("municipio_ibge_residencia") or rec.get("municipio_ibge")
        else:
            municipio = rec.get("municipio_ibge_notificacao") or rec.get("municipio_ibge")

        if not municipio:
            continue

        h = sha256_dict(rec)

        await db.execute(
            insert_sql,
            {
                "id": str(uuid.uuid4()),
                "year": dref.year,
                "ref_date": dref,
                "geo_basis": geo_basis,
                "municipio_ibge": str(municipio),
                "disease": str(disease),
                "external_id": rec.get("external_id"),
                "raw": json.dumps(rec, ensure_ascii=False),
                "hash": h,
            },
        )
        inserted += 1

        if inserted % 1000 == 0:
            await db.commit()

    await db.commit()
    return inserted