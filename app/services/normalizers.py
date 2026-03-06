from __future__ import annotations
from typing import Any, Dict, Optional

def _to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(float(x))
    except Exception:
        return None

def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None

def normalize_infodengue_row(
    row: Dict[str, Any],
    *,
    disease: str,
    geo_code: str,
) -> Dict[str, Any]:
    """
    Normaliza uma linha do endpoint InfoDengue AlertCity para o modelo interno.

    O InfoDengue frequentemente traz:
      - SE = YYYYWW (ex.: 202605)
    e nem sempre traz year/epiweek separados.
    """

    se = row.get("SE") or row.get("se") or row.get("EW") or row.get("epiweek")
    se_int = _to_int(se)

    year = _to_int(row.get("year") or row.get("ano") or row.get("epiyear") or row.get("EY"))
    epiweek = _to_int(row.get("epiweek") or row.get("semana") or row.get("week") or row.get("EW"))

    if se_int and se_int >= 100000:
        year = se_int // 100
        epiweek = se_int % 100

    cases = row.get("casos")
    if cases is None:
        cases = row.get("cases")
    if cases is None:
        cases = row.get("casos_est")
    cases_i = _to_int(cases) or 0

    incidence_100k = _to_float(
        row.get("p_inc100k") or row.get("incidencia") or row.get("incidence") or row.get("incidencia_100k")
    )

    rt_point = _to_float(row.get("Rt") or row.get("rt") or row.get("rt_medio") or row.get("rt_point"))

    alert_level = _to_int(row.get("nivel") or row.get("alerta") or row.get("alert_level"))

    return {
        "source": "INFODENGUE",
        "disease": disease,
        "geo_code": geo_code,
        "year": year,
        "epiweek": epiweek,
        "cases_reported": cases_i,
        "incidence_100k": incidence_100k,
        "rt_point": rt_point,
        "alert_level": alert_level,
        "raw": row,
    }