from __future__ import annotations
from datetime import date, datetime
from hashlib import sha256
from typing import Any

def _to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except Exception:
            return None
    return None

def _hash_dict(payload: dict[str, Any]) -> str:
    import json
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()

class EsusNotificaNormalizer:
    """
    Normaliza hit do OpenSearch para um registro RAW (staging).
    """
    def normalize_raw_sivep_v2(
        self,
        hit: dict[str, Any],
        *,
        geo_basis: str = "notificacao",
        disease: str = "srag",
    ) -> dict[str, Any]:
        src = hit.get("_source") or {}
        raw = src

        ref_date = (
            _to_date(src.get("dataNotificacao"))
            or _to_date(src.get("dataInicioSintomas"))
            or _to_date(src.get("dataTeste"))
            or date.today()
        )

        municipio = (
            src.get("municipioIBGE")
            or src.get("municipio")
            or src.get("co_municipio")
            or src.get("CO_MUNICIPIO")
            or ""
        )
        municipio = str(municipio) if municipio is not None else ""

        external_id = (
            src.get("id")
            or src.get("uuid")
            or hit.get("_id")
        )

        h = _hash_dict(raw)

        return {
            "year": int(ref_date.year),
            "ref_date": ref_date,
            "geo_basis": geo_basis,
            "municipio_ibge": municipio,
            "disease": disease,
            "external_id": str(external_id) if external_id is not None else None,
            "raw": raw,
            "hash": h,
        }