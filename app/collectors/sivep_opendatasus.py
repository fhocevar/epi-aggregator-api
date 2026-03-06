# app/collectors/sivep_opendatasus.py
from __future__ import annotations
import csv
import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Dict, Optional
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def _sha256_dict(d: Dict) -> str:
    raw = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _parse_date_any(v: str) -> Optional[date]:
    if not v:
        return None
    v = v.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except Exception:
            pass
    return None

async def ingest_sivep_srag_opendatasus(
    db: AsyncSession,
    *,
    geo_basis: str,
    year: int,
    date_from: date,
    date_to: date,
    resource_url: str,
    timeout_sec: int = 180,
    batch_id: str = "sivep-srag",
) -> int:
    """
    Ingest SRAG (SIVEP-Gripe) via URL direta de CSV (sem CKAN).
    Espera CSV separado por ';' (padrão SRAG).

    Campos usados:
      - CO_MUN_RES (residência)
      - CO_MUN_NOT (notificação)
      - DT_NOTIFIC ou DT_SIN_PRI como ref_date
    """
    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    if not resource_url:
        raise ValueError("resource_url vazio. Configure OPENDATASUS_SIVEP_SRG_CSV_URL no .env")

    insert_sql = text("""
    INSERT INTO raw_sivep_gripe (
      id, year, ref_date, geo_basis, municipio_ibge, disease,
      external_id, raw, hash, ingested_at
    ) VALUES (
      :id, :year, :ref_date, :geo_basis, :municipio_ibge, :disease,
      :external_id, :raw::jsonb, :hash, NOW()
    )
    ON CONFLICT ON CONSTRAINT uq_raw_sivep_hash DO NOTHING;
    """)

    inserted = 0

    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        async with client.stream("GET", resource_url) as resp:
            resp.raise_for_status()

            # SRAG costuma vir em Latin-1/Windows-1252 às vezes.
            # Vamos decodificar “tolerante”.
            lines = (line for line in resp.aiter_lines())

            reader = csv.DictReader(lines, delimiter=";")

            for row in reader:
                # filtra ano (alguns arquivos têm múltiplos anos)
                # se existir "NU_ANO", usa; se não, ignora.
                nu_ano = (row.get("NU_ANO") or "").strip()
                if nu_ano and nu_ano.isdigit() and int(nu_ano) != int(year):
                    continue

                dref = _parse_date_any(row.get("DT_NOTIFIC", "")) or _parse_date_any(row.get("DT_SIN_PRI", ""))
                if not dref:
                    continue
                if dref < date_from or dref > date_to:
                    continue

                if geo_basis == "residencia":
                    municipio = (row.get("CO_MUN_RES") or "").strip()
                else:
                    municipio = (row.get("CO_MUN_NOT") or "").strip()

                if not municipio:
                    continue

                minimal = {
                    "year": year,
                    "geo_basis": geo_basis,
                    "CO_MUN_RES": row.get("CO_MUN_RES"),
                    "CO_MUN_NOT": row.get("CO_MUN_NOT"),
                    "DT_NOTIFIC": row.get("DT_NOTIFIC"),
                    "DT_SIN_PRI": row.get("DT_SIN_PRI"),
                    "CLASSI_FIN": row.get("CLASSI_FIN"),
                    "PCR_SARS2": row.get("PCR_SARS2"),
                }
                h = _sha256_dict(minimal)

                await db.execute(
                    insert_sql,
                    {
                        "id": str(uuid.uuid4()),
                        "year": year,
                        "ref_date": dref,
                        "geo_basis": geo_basis,
                        "municipio_ibge": municipio,
                        "disease": "srag",
                        "external_id": None,
                        "raw": json.dumps(row, ensure_ascii=False),
                        "hash": h,
                    },
                )

                inserted += 1
                if inserted % 2000 == 0:
                    await db.commit()

    await db.commit()
    return inserted