# app/routers/demas_analytics.py
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings
from app.demas_models import DemasEvent


router = APIRouter(prefix="/demas/analytics", tags=["DEMAS Analytics"])


def _session_factory() -> async_sessionmaker[AsyncSession]:
    db_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
    if not db_url:
        db_url = "postgresql+asyncpg://epi:epi@localhost:5432/epi_clipping"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


def _dataset_cond(dataset: str | None) -> list:
    conds = []
    if dataset:
        conds.append(DemasEvent.dataset == dataset)
    return conds


@router.get("/summary")
async def summary(
    dataset: str | None = Query(None),
    uf: str | None = Query(None),
    municipio_ibge: str | None = Query(None),
    year: int | None = Query(None),
):
    conds = _dataset_cond(dataset)
    if uf:
        conds.append(DemasEvent.uf == uf)
    if municipio_ibge:
        conds.append(DemasEvent.municipio_ibge == municipio_ibge)
    if year is not None:
        conds.append(DemasEvent.year == year)

    where = and_(*conds) if conds else True

    async with _session_factory() as session:
        total = (await session.execute(select(func.count()).select_from(DemasEvent).where(where))).scalar_one()
        min_dt = (await session.execute(select(func.min(DemasEvent.event_date)).where(where))).scalar_one()
        max_dt = (await session.execute(select(func.max(DemasEvent.event_date)).where(where))).scalar_one()

    return {
        "dataset": dataset,
        "filters": {"uf": uf, "municipio_ibge": municipio_ibge, "year": year},
        "total_events": int(total),
        "date_min": min_dt.isoformat() if min_dt else None,
        "date_max": max_dt.isoformat() if max_dt else None,
    }


@router.get("/by-uf")
async def by_uf(
    dataset: str = Query(...),
    year: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    conds = [DemasEvent.dataset == dataset]
    if year is not None:
        conds.append(DemasEvent.year == year)

    async with _session_factory() as session:
        q = (
            select(DemasEvent.uf, func.count().label("count"))
            .where(and_(*conds))
            .group_by(DemasEvent.uf)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()

    return {
        "dataset": dataset,
        "year": year,
        "items": [{"uf": uf, "count": int(c)} for (uf, c) in rows],
    }


@router.get("/by-municipio")
async def by_municipio(
    dataset: str = Query(...),
    uf: str | None = Query(None),
    year: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    conds = [DemasEvent.dataset == dataset]
    if uf:
        conds.append(DemasEvent.uf == uf)
    if year is not None:
        conds.append(DemasEvent.year == year)

    async with _session_factory() as session:
        q = (
            select(DemasEvent.municipio_ibge, DemasEvent.municipio_nome, func.count().label("count"))
            .where(and_(*conds))
            .group_by(DemasEvent.municipio_ibge, DemasEvent.municipio_nome)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()

    return {
        "dataset": dataset,
        "filters": {"uf": uf, "year": year},
        "items": [
            {"municipio_ibge": mi, "municipio_nome": mn, "count": int(c)}
            for (mi, mn, c) in rows
        ],
    }


@router.get("/by-epiweek")
async def by_epiweek(
    dataset: str = Query(...),
    year: int | None = Query(None),
    uf: str | None = Query(None),
):
    conds = [DemasEvent.dataset == dataset]
    if year is not None:
        conds.append(DemasEvent.year == year)
    if uf:
        conds.append(DemasEvent.uf == uf)

    async with _session_factory() as session:
        q = (
            select(DemasEvent.year, DemasEvent.epiweek, func.count().label("count"))
            .where(and_(*conds))
            .group_by(DemasEvent.year, DemasEvent.epiweek)
            .order_by(DemasEvent.year.asc(), DemasEvent.epiweek.asc())
        )
        rows = (await session.execute(q)).all()

    return {
        "dataset": dataset,
        "filters": {"year": year, "uf": uf},
        "items": [{"year": y, "epiweek": ew, "count": int(c)} for (y, ew, c) in rows],
    }