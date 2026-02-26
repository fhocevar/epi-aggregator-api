# app/routers/demas.py
from __future__ import annotations

import time
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Query

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings
from app.services.demas_service import DemasSyncService, DEMAS_DATASETS


router = APIRouter(prefix="/demas", tags=["DEMAS (MS Dados Abertos)"])


def _session_factory() -> async_sessionmaker[AsyncSession]:
    db_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
    if not db_url:
        db_url = "postgresql+asyncpg://epi:epi@localhost:5432/epi_clipping"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def _service() -> DemasSyncService:
    years_csv = getattr(settings, "demas_arboviroses_years", "2024,2025,2026")
    arb_years = [int(x.strip()) for x in str(years_csv).split(",") if x.strip().isdigit()]

    return DemasSyncService(
        session_factory=_session_factory(),
        base_url=getattr(settings, "demas_base_url", "https://apidadosabertos.saude.gov.br"),
        timeout_seconds=int(getattr(settings, "demas_timeout_seconds", 60)),
        limit=int(getattr(settings, "demas_limit", 20)),
        sleep_seconds=float(getattr(settings, "demas_sleep_seconds", 0.05)),
        arboviroses_years=arb_years,
        dataset_deadline_seconds=25,  # ✅ evita travar
    )


@router.get("/health")
async def demas_health(external: bool = Query(False, description="Se true, testa chamada real ao DEMAS (pode falhar rápido)")):
    base = {
        "status": "ok",
        "ts": datetime.now(timezone.utc).isoformat(),
        "demas_base_url": getattr(settings, "demas_base_url", "https://apidadosabertos.saude.gov.br"),
    }

    if not external:
        base["external_checked"] = False
        return base

    t0 = time.perf_counter()
    try:
        svc = _service()
        ping = await svc.client.ping()
        base["external_checked"] = True
        base["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        base["ping"] = ping
        base["external_ok"] = bool(ping.get("ok"))
        return base
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        base["external_checked"] = True
        base["external_ok"] = False
        base["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        base["warning"] = f"DEMAS instável no momento: {type(e).__name__}"
        return base


@router.get("/datasets")
async def demas_datasets():
    return {"count": len(DEMAS_DATASETS), "datasets": [{"key": d.key, "path": d.path, "uses_year": d.uses_year, "kind": d.kind} for d in DEMAS_DATASETS]}


@router.get("/stats")
async def demas_stats():
    svc = _service()
    s = await svc.stats()
    return {"status_code": 200, "stats": s}


@router.post("/sync/daily")
async def demas_sync_daily():
    svc = _service()
    result = await svc.sync_all_daily()
    return {"status_code": 200, "result": result}


@router.post("/sync/weekly-municipios")
async def demas_sync_weekly_municipios():
    svc = _service()
    result = await svc.sync_municipios_weekly()
    return {"status_code": 200, "result": result}


@router.post("/sync/dataset/{dataset_key}")
async def demas_sync_dataset(dataset_key: str):
    dataset_key = dataset_key.strip()
    ds = next((d for d in DEMAS_DATASETS if d.key == dataset_key), None)
    if not ds:
        allowed = [d.key for d in DEMAS_DATASETS]
        return {"status_code": 400, "message": f"dataset_key inválido. use: {allowed}"}

    svc = _service()
    sync_res = await svc.sync_dataset(ds)
    return {"status_code": 200, "result": sync_res}


# -------------------------
# ✅ CONSULTA NO POSTGRES (RAW / EVENTS)
# -------------------------
@router.get("/raw/{dataset_key}")
async def demas_raw_query(
    dataset_key: str,
    year: int | None = Query(None, description="Para arboviroses (nu_ano)"),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
):
    svc = _service()
    return await svc.query_raw(dataset=dataset_key, year=year, page=page, size=size)


@router.get("/events/{dataset_key}")
async def demas_events_query(
    dataset_key: str,
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
    uf: str | None = Query(None, description="Ex: RJ, SP"),
    municipio_ibge: str | None = Query(None, description="Ex: 3304557"),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
):
    svc = _service()
    return await svc.query_events(
        dataset=dataset_key,
        date_from=date_from,
        date_to=date_to,
        uf=uf,
        municipio_ibge=municipio_ibge,
        page=page,
        size=size,
    )