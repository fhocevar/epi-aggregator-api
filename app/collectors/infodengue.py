import httpx

async def fetch_infodengue_alertcity(
    base_url: str,
    geocode: str,
    disease: str,
    ew_start: int,
    ew_end: int,
    ey_start: int,
    ey_end: int,
) -> list[dict]:
    # https://info.dengue.mat.br/api/alertcity?<PARAMETROS> (json/csv)
    params = dict(
        geocode=geocode,
        disease=disease,
        format="json",
        ew_start=ew_start,
        ew_end=ew_end,
        ey_start=ey_start,
        ey_end=ey_end,
    )

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(base_url, params=params)
        r.raise_for_status()
        data = r.json()

    # geralmente retorna lista de linhas semanais
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
        return data["results"]
    return []

from datetime import date

def _to_int(x):
    if x is None:
        return None
    try:
        return int(float(x))
    except Exception:
        return None

def _to_float(x):
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None

def normalize_infodengue_row(row: dict, disease: str, geo_code: str) -> dict:
    """
    Canon:
      year, epiweek
      cases_reported (casos)
      cases_estimated (casos_est)
      incidence_100k (p_inc100k)
      pr_rt_gt_1 (p_rt1)
      alert_level (nivel)
      rt_point (Rt)
      week_start_date (data_iniSE)
      pop
    """
    se = row.get("SE") or row.get("se") or row.get("epiweek") or row.get("EW")
    se_int = _to_int(se)

    year = _to_int(row.get("year") or row.get("ano") or row.get("EY"))
    epiweek = None

    if se_int and se_int > 10000:
        year = se_int // 100
        epiweek = se_int % 100
    else:
        epiweek = _to_int(se_int)

    week_start = row.get("data_iniSE") or row.get("data_inise") or row.get("week_start")

    mapped = {
        "disease": disease,
        "geo_code": geo_code,
        "year": year,
        "epiweek": epiweek,
        "week_start_date": week_start,
        "cases_reported": _to_int(row.get("casos") or row.get("cases")),
        "cases_estimated": _to_int(row.get("casos_est")),
        "cases_est_min": _to_int(row.get("casos_est_min")),
        "cases_est_max": _to_int(row.get("casos_est_max")),
        "incidence_100k": _to_float(row.get("p_inc100k") or row.get("incidencia")),
        "pr_rt_gt_1": _to_float(row.get("p_rt1")),
        "alert_level": _to_int(row.get("nivel") or row.get("level") or row.get("alert_level")),
        "rt_point": _to_float(row.get("Rt") or row.get("rt")),
        "pop": _to_float(row.get("pop")),
        "raw": row,
    }

    if mapped["year"] is None or mapped["epiweek"] is None:
        mapped["year"] = mapped["year"] or 0
        mapped["epiweek"] = mapped["epiweek"] or 0

    return mapped

