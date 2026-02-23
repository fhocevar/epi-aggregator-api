from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Bulletin, EpiAlert, CasesWeekly, IndicatorsWeekly

router = APIRouter(prefix="/epidemiologia", tags=["Epidemiologia"])


@router.get("/boletins")
async def list_boletins(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    source: str | None = Query(None),
):
    stmt = select(Bulletin)
    if source:
        stmt = stmt.where(Bulletin.source_code == source)

    total = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total_items = int(total.scalar() or 0)

    q = await db.execute(
        stmt.order_by(desc(Bulletin.published_at)).offset((page - 1) * size).limit(size)
    )
    items = q.scalars().all()

    return {
        "page": page,
        "size": size,
        "total_items": total_items,
        "items": [
            {
                "id": str(x.id),
                "source_code": x.source_code,
                "external_id": x.external_id,
                "title": x.title,
                "published_at": x.published_at,
                "url": x.url,
                "summary": x.summary,
            }
            for x in items
        ],
    }


@router.get("/alertas")
async def list_alertas(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    disease: str | None = Query(None),
    geo_code: str | None = Query(None),
    severity: str | None = Query(None),
):
    stmt = select(EpiAlert)
    if disease:
        stmt = stmt.where(EpiAlert.disease == disease)
    if geo_code:
        stmt = stmt.where(EpiAlert.geo_code == geo_code)
    if severity:
        stmt = stmt.where(EpiAlert.severity == severity)

    total = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total_items = int(total.scalar() or 0)

    q = await db.execute(
        stmt.order_by(desc(EpiAlert.created_at)).offset((page - 1) * size).limit(size)
    )
    items = q.scalars().all()

    return {
        "page": page,
        "size": size,
        "total_items": total_items,
        "items": [
            {
                "id": str(x.id),
                "source_code": x.source_code,
                "disease": x.disease,
                "geo_level": x.geo_level,
                "geo_code": x.geo_code,
                "year": x.year,
                "epiweek": x.epiweek,
                "severity": x.severity,
                "title": x.title,
                "message": x.message,
                "created_at": x.created_at,
                "evidence": x.evidence,
            }
            for x in items
        ],
    }


@router.get("/casos")
async def list_casos(
    db: AsyncSession = Depends(get_db),
    disease: str = Query(...),
    geo_code: str = Query(...),

    year_from: int | None = Query(None),
    week_from: int | None = Query(None, ge=1, le=53),
    year_to: int | None = Query(None),
    week_to: int | None = Query(None, ge=1, le=53),
):
    stmt = select(CasesWeekly).where(CasesWeekly.disease == disease, CasesWeekly.geo_code == geo_code)

    if year_from is not None and week_from is not None:
        k_from = year_from * 100 + week_from
        stmt = stmt.where((CasesWeekly.year * 100 + CasesWeekly.epiweek) >= k_from)

    if year_to is not None and week_to is not None:
        k_to = year_to * 100 + week_to
        stmt = stmt.where((CasesWeekly.year * 100 + CasesWeekly.epiweek) <= k_to)

    q = await db.execute(stmt.order_by(CasesWeekly.year, CasesWeekly.epiweek))
    rows = q.scalars().all()

    return {
        "disease": disease,
        "geo_code": geo_code,
        "items": [
            {"year": r.year, "epiweek": r.epiweek, "cases": r.cases}
            for r in rows
        ],
    }



@router.get("/indicadores")
async def list_indicadores(
    db: AsyncSession = Depends(get_db),
    disease: str = Query(...),
    geo_code: str = Query(...),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
):
    stmt = select(IndicatorsWeekly).where(
        IndicatorsWeekly.disease == disease, IndicatorsWeekly.geo_code == geo_code
    )
    if year_from is not None:
        stmt = stmt.where(IndicatorsWeekly.year >= year_from)
    if year_to is not None:
        stmt = stmt.where(IndicatorsWeekly.year <= year_to)

    q = await db.execute(stmt.order_by(IndicatorsWeekly.year, IndicatorsWeekly.epiweek))
    rows = q.scalars().all()

    return {
        "disease": disease,
        "geo_code": geo_code,
        "items": [
            {
                "disease": r.disease,
                "geo_code": r.geo_code,
                "year": r.year,
                "epiweek": r.epiweek,
                "incidence": r.incidence,
                "rt": r.rt,
                "alert_level": r.alert_level,
            }
            for r in rows
        ],
    }
