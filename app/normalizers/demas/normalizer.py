from __future__ import annotations
import re
from datetime import date
from typing import Any
from app.normalizers.demas.base import _hash_dict, _pick_first, _to_date

def _clean_uf(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().upper()
    return s or None

def _clean_municipio_ibge(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    s = re.sub(r"\D+", "", s)
    return s or None

def _parse_epiweek(v: Any) -> tuple[int | None, int | None]:
    """
    Suporta:
      - "AAAASS" (ex 202605) => year=2026, epiweek=5
      - "SS" / "S" => epiweek
      - int
    Retorna (year, epiweek)
    """
    if v is None:
        return (None, None)

    s = str(v).strip()
    if not s:
        return (None, None)

    if s.isdigit() and len(s) == 6:
        y = int(s[:4])
        w = int(s[4:])
        return (y, w)

    if s.isdigit():
        return (None, int(s))

    return (None, None)

class DemasNormalizer:
    """
    Normaliza item DEMAS (RAW) -> evento genérico para demas_events.

    MVP:
      - guarda payload inteiro
      - fingerprint = hash(dataset + payload)
      - tenta inferir event_date, epiweek, year, uf, municipio_ibge
    """

    def normalize_event(self, *, dataset_key: str, item: dict[str, Any]) -> dict[str, Any]:
        payload = item

        event_date = (
            _to_date(
                _pick_first(
                    payload,
                    ["dt_notific", "dt_sin_pri", "dt_invest", "dt_digita", "data", "dt_obito"],
                )
            )
            or date.today()
        )

        raw_year = _pick_first(payload, ["nu_ano", "ano", "year"])
        raw_epiweek = _pick_first(payload, ["sem_not", "sem_pri", "semana", "epiweek"])
        y_from_week, w = _parse_epiweek(raw_epiweek)

        year: int
        if raw_year is not None and str(raw_year).strip().isdigit():
            year = int(str(raw_year).strip())
        elif y_from_week is not None:
            year = y_from_week
        else:
            year = int(event_date.year)

        uf = _clean_uf(_pick_first(payload, ["sg_uf_not", "sg_uf", "uf", "UF"]))
        municipio_ibge = _clean_municipio_ibge(
            _pick_first(payload, ["id_municip", "id_mn_resi", "municipio_ibge", "municipio", "co_municipio"])
        )
        municipio_nome = _pick_first(payload, ["nm_municip", "municipio_nome", "municipio_nm", "nome_municipio"])
        municipio_nome = str(municipio_nome).strip() if municipio_nome is not None else None

        fingerprint = _hash_dict({"dataset": dataset_key, "payload": payload})

        return {
            "dataset": dataset_key,
            "event_date": event_date,
            "year": year,
            "epiweek": w,
            "uf": uf,
            "municipio_ibge": municipio_ibge,
            "municipio_nome": municipio_nome or None,
            "fingerprint": fingerprint,
            "payload": payload,
        }