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


async def ingest_sim(
    db: AsyncSession,
    *,
    geo_basis: str,
    url: str,
    date_from: date,
    date_to: date,
    timeout_sec: int = 60,
    batch_id: str = "sim-ingest",
) -> int:
    """
    MVP: baixa JSON (lista) e grava em raw_sim.

    Formato esperado por registro (mínimo):
    {
      "ref_date": "2026-02-01",                 # data (pode ser óbito, ocorrência ou competência)
      "disease": "all_cause" | "covid19" | "J09-J18" | ...,
      "icd10": "U07.1",                         # opcional
      "municipio_ibge_residencia": "3304557",
      "municipio_ibge_notificacao": "3304557",  # normalmente não se usa no SIM, mas mantemos flexível
      "count": 1,                               # opcional (se já vier agregado)
      ... outros campos ...
    }
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
    INSERT INTO raw_sim (
      id, year, ref_date, geo_basis, municipio_ibge, disease,
      icd10, external_id, raw, hash
    )
    VALUES (
      :id, :year, :ref_date, :geo_basis, :municipio_ibge, :disease,
      :icd10, :external_id, :raw::jsonb, :hash
    )
    ON CONFLICT ON CONSTRAINT uq_raw_sim_hash DO NOTHING;
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
                "icd10": rec.get("icd10"),
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