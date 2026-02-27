# app/routers/demas_import.py
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings
from app.services.demas_import_service import DemasImportService
from app.services.demas_sources import DEMAS_S3_SOURCES


router = APIRouter(prefix="/demas", tags=["DEMAS (MS Dados Abertos)"])


def _session_factory() -> async_sessionmaker[AsyncSession]:
    db_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
    if not db_url:
        db_url = "postgresql+asyncpg://epi:epi@localhost:5432/epi_clipping"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def _import_service() -> DemasImportService:
    return DemasImportService(session_factory=_session_factory())


@router.post("/import/from-url/{dataset_key}")
async def demas_import_from_url(
    dataset_key: str,
    url: str = Query(..., description="URL do arquivo (CSV ou ZIP com CSV)"),
    request_year: int | None = Query(None, description="Opcional: ano associado ao import (arboviroses/SINAN etc.)"),
    normalize_events: bool = Query(True, description="Se true, normaliza para demas_events após importar"),
    timeout_seconds: int = Query(600, description="Timeout do download"),
    chunk_size: int = Query(2000, ge=100, le=10000),
):
    svc = _import_service()
    res = await svc.import_from_url(
        dataset_key=dataset_key,
        url=url,
        request_year=request_year,
        normalize_events=normalize_events,
        timeout_seconds=timeout_seconds,
        chunk_size=chunk_size,
    )

    return {
        "status_code": 200,
        "result": {
            "dataset": res.dataset,
            "fetched": res.fetched,
            "saved": res.saved,
            "duplicates": res.duplicates,
            "normalized": res.normalized,
            "events_saved": res.events_saved,
            "events_duplicates": res.events_duplicates,
        },
    }


@router.post("/import/from-url/bulk")
async def demas_import_bulk_from_url(
    timeout_seconds: int = Query(600),
    chunk_size: int = Query(2000, ge=100, le=10000),
):
    """
    ✅ Importa todos os datasets definidos em app/services/demas_sources.py (S3 fallback).
    """
    svc = _import_service()
    report = await svc.import_bulk_from_sources(
        sources=DEMAS_S3_SOURCES,
        timeout_seconds=timeout_seconds,
        chunk_size=chunk_size,
    )
    return {"status_code": 200, "result": report}