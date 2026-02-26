from __future__ import annotations

from datetime import date
from typing import Any

from app.normalizers.demas.base import _hash_dict, _pick_first, _to_date


class DemasNormalizer:
    """
    Normaliza item DEMAS (RAW) -> evento genérico para demas_events.

    Regras aqui são "best-effort" (MVP):
      - guarda payload inteiro
      - calcula fingerprint (hash)
      - tenta inferir event_date, epiweek, year, uf, municipio_ibge
    """

    def normalize_event(self, *, dataset_key: str, item: dict[str, Any]) -> dict[str, Any]:
        payload = item

        # datas mais comuns nos seus dicionários (arboviroses)
        event_date = (
            _to_date(_pick_first(payload, ["dt_notific", "dt_sin_pri", "dt_invest", "dt_digita", "data", "dt_obito"]))
            or date.today()
        )

        # ano / semana (quando existirem)
        year = _pick_first(payload, ["nu_ano", "ano", "year"])
        epiweek = _pick_first(payload, ["sem_not", "sem_pri", "semana", "epiweek"])

        # UF / município (nomes comuns)
        uf = _pick_first(payload, ["sg_uf_not", "sg_uf", "uf", "UF"])
        municipio_ibge = _pick_first(payload, ["id_municip", "id_mn_resi", "municipio_ibge", "municipio", "co_municipio"])

        municipio_nome = _pick_first(payload, ["nm_municip", "municipio_nome", "municipio_nm", "nome_municipio"])

        fingerprint = _hash_dict({"dataset": dataset_key, "payload": payload})

        return {
            "dataset": dataset_key,
            "event_date": event_date,
            "year": int(year) if str(year).isdigit() else event_date.year,
            "epiweek": int(epiweek) if str(epiweek).isdigit() else None,
            "uf": str(uf) if uf is not None else None,
            "municipio_ibge": str(municipio_ibge) if municipio_ibge is not None else None,
            "municipio_nome": str(municipio_nome) if municipio_nome is not None else None,
            "fingerprint": fingerprint,
            "payload": payload,
        }