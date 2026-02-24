from __future__ import annotations

from typing import Any


class DemasNormalizer:
    """
    Normaliza payload DEMAS para o seu schema unificado do pipeline v2.
    Ajuste os campos conforme seu modelo (municipio, data_evento, doenca, etc).
    """

    def normalize(self, raw: dict[str, Any], *, disease: str, source: str = "demas") -> dict[str, Any]:
        # Heurística: tenta achar município e data em chaves comuns
        municipio = (
            raw.get("municipio")
            or raw.get("municipio_nome")
            or raw.get("nome_municipio")
            or raw.get("no_municipio")
            or raw.get("NM_MUNICIPIO")
        )

        geocode = (
            raw.get("geocodigo")
            or raw.get("codigo_municipio")
            or raw.get("co_municipio")
            or raw.get("CO_MUNICIPIO")
            or raw.get("ibge")
        )

        dt = (
            raw.get("data")
            or raw.get("dt_notificacao")
            or raw.get("dt_sintomas")
            or raw.get("dt_obito")
            or raw.get("DT_NOTIFIC")
            or raw.get("DT_EVOLUCA")
        )

        # seu schema unificado (exemplo)
        return {
            "source": source,
            "source_dataset": disease,
            "disease": disease,
            "geo_basis": raw.get("geo_basis") or "notificacao",  # você já queria isso
            "municipio": municipio,
            "geocode": str(geocode) if geocode is not None else None,
            "date_event": dt,
            "raw": raw,  # guarda cru para auditoria/trace
        }