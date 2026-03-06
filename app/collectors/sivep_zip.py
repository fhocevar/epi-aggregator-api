from __future__ import annotations
import csv
import hashlib
import json
import os
import tempfile
import uuid
import zipfile
from datetime import date, datetime
from typing import Dict, Optional
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def _sha256_dict(d: Dict) -> str:
    raw = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _parse_date_pt(v: str) -> Optional[date]:
    if not v:
        return None
    v = v.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except Exception:
            pass
    return None

async def ingest_sivep_srag_from_zip_url(
    db: AsyncSession,
    *,
    geo_basis: str,
    year: int,
    date_from: date,
    date_to: date,
    zip_url: str,
    batch_id: str = "sivep-zip",
    timeout_sec: int = 300,
) -> int:
    """
    Baixa ZIP do SRAG (SIVEP-Gripe), lê o CSV interno e grava em raw_sivep_gripe.
    Usa DT_NOTIFIC como data de referência (conforme pedido).
    """

    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    insert_sql = text("""
    INSERT INTO raw_sivep_gripe (
      id, year, ref_date, geo_basis, municipio_ibge, disease,
      external_id, raw, hash
    ) VALUES (
      :id, :year, :ref_date, :geo_basis, :municipio_ibge, :disease,
      :external_id, :raw::jsonb, :hash
    )
    ON CONFLICT ON CONSTRAINT uq_raw_sivep_hash DO NOTHING;
    """)

    # 1) baixa ZIP para arquivo temporário (evita estourar memória)
    tmp_path = None
    inserted = 0

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = tmp.name

        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            async with client.stream("GET", zip_url) as resp:
                resp.raise_for_status()
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)

        # 2) abre ZIP e acha o CSV (geralmente 1 grande)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                raise RuntimeError(f"ZIP não contém CSV. Conteúdo: {zf.namelist()[:20]}")

            csv_names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
            csv_name = csv_names[0]

            with zf.open(csv_name, "r") as raw_fp:
                # SRAG costuma vir em Latin-1/ISO-8859-1
                # e separado por ';'
                text_fp = (line.decode("latin-1", errors="ignore") for line in raw_fp)
                reader = csv.DictReader(text_fp, delimiter=";")

                for row in reader:
                    dref = _parse_date_pt(row.get("DT_NOTIFIC", ""))
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
                        "DT_NOTIFIC": row.get("DT_NOTIFIC"),
                        "CO_MUN_RES": row.get("CO_MUN_RES"),
                        "CO_MUN_NOT": row.get("CO_MUN_NOT"),
                        "ID_MUNICIP": municipio,
                        "NU_NOTIFIC": row.get("NU_NOTIFIC"),
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
                            "external_id": row.get("NU_NOTIFIC"),
                            "raw": json.dumps(row, ensure_ascii=False),
                            "hash": h,
                        },
                    )
                    inserted += 1

                    if inserted % 2000 == 0:
                        await db.commit()

        await db.commit()
        return inserted

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass