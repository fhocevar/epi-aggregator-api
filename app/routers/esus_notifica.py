from __future__ import annotations
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.settings import settings
from app.db import AsyncSessionLocal, get_db
from app.collectors.esus_notifica.client import EsusNotificaClient
from app.collectors.esus_notifica.collector import EsusNotificaCollector
from app.normalizers.esus_notifica.base import EsusNotificaNormalizer
from app.services.esus_notifica_service import EsusNotificaService
from app.models import RawSivepGripe

router = APIRouter(prefix="/esus-notifica", tags=["e-SUS Notifica (OpenSearch)"])

def _service() -> EsusNotificaService:
    if not settings.esus_opensearch_user or not settings.esus_opensearch_password:
        raise RuntimeError("ESUS_OPENSEARCH_USER/ESUS_OPENSEARCH_PASSWORD não configurados no .env")

    client = EsusNotificaClient(
        base_url=settings.esus_opensearch_base_url,
        username=settings.esus_opensearch_user,
        password=settings.esus_opensearch_password,
        timeout_seconds=settings.esus_opensearch_timeout_seconds,
    )

    collector = EsusNotificaCollector(
        client,
        page_size=settings.esus_opensearch_page_size,
        max_pages=settings.esus_opensearch_max_pages,
    )

    normalizer = EsusNotificaNormalizer()

    return EsusNotificaService(
        client=client,
        collector=collector,
        normalizer=normalizer,
        session_factory=AsyncSessionLocal,
    )

@router.get("/health")
async def health():
    """
    Faz uma busca mínima (últimos 2 dias) e salva no banco.
    """
    svc = _service()
    df = (date.today() - timedelta(days=2)).isoformat()
    result = await svc.sync(uf=None, date_from=df, date_to=None)
    return {"status": "ok", **result}

@router.post("/sync")
async def sync(
    uf: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    geo_basis: str = "notificacao",
    disease: str = "srag",
):
    """
    Dispara coleta + persistência em RAW (Postgres).
    """
    svc = _service()
    return await svc.sync(
        uf=uf,
        date_from=date_from,
        date_to=date_to,
        geo_basis=geo_basis,
        disease=disease,
    )

@router.post("/preview")
async def preview(
    uf: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
):
    """
    Mostra exemplos direto do OpenSearch (não salva).
    """
    if not settings.esus_opensearch_user or not settings.esus_opensearch_password:
        raise RuntimeError("ESUS_OPENSEARCH_USER/ESUS_OPENSEARCH_PASSWORD não configurados no .env")

    client = EsusNotificaClient(
        base_url=settings.esus_opensearch_base_url,
        username=settings.esus_opensearch_user,
        password=settings.esus_opensearch_password,
        timeout_seconds=settings.esus_opensearch_timeout_seconds,
    )

    collector = EsusNotificaCollector(
        client,
        page_size=min(settings.esus_opensearch_page_size, max(1, limit)),
        max_pages=1,
    )

    hits = await collector.collect(uf=uf, date_from=date_from, date_to=date_to)
    hits = hits[:limit]

    return {"status_code": 200, "total_items": len(hits), "items": hits}

@router.get("/raw")
async def list_raw(
    uf: str | None = Query(default=None, description="UF (ex: rj, sp)"),
    disease: str | None = Query(default=None),
    geo_basis: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Consulta dados RAW já salvos (endpoint técnico).
    """
    stmt = select(RawSivepGripe)

    if disease:
        stmt = stmt.where(RawSivepGripe.disease == disease)

    if geo_basis:
        stmt = stmt.where(RawSivepGripe.geo_basis == geo_basis)

    if uf:
        stmt = stmt.where(RawSivepGripe.municipio_ibge.like(f"{uf.upper()}%"))

    stmt = stmt.order_by(RawSivepGripe.ingested_at.desc())
    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    return {
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "ingested_at": r.ingested_at,
                "geo_basis": r.geo_basis,
                "municipio_ibge": r.municipio_ibge,
                "disease": r.disease,
                "external_id": r.external_id,
            }
            for r in rows
        ],
    }

@router.get("/raw/summary")
async def raw_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    disease: str | None = Query(default="srag"),
    geo_basis: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    """
    Sumário agregado dos dados RAW (crus).
    """
    filters = []

    if disease:
        filters.append(RawSivepGripe.disease == disease)

    if geo_basis:
        filters.append(RawSivepGripe.geo_basis == geo_basis)

    if date_from:
        filters.append(RawSivepGripe.ref_date >= date_from)

    if date_to:
        filters.append(RawSivepGripe.ref_date <= date_to)

    total_stmt = select(func.count()).select_from(RawSivepGripe).where(*filters)
    total = (await session.execute(total_stmt)).scalar()

    geo_basis_stmt = (
        select(RawSivepGripe.geo_basis, func.count().label("count"))
        .where(*filters)
        .group_by(RawSivepGripe.geo_basis)
    )
    geo_basis_rows = (await session.execute(geo_basis_stmt)).all()

    municipios_stmt = (
        select(
            RawSivepGripe.municipio_ibge,
            func.count().label("count"),
        )
        .where(*filters)
        .group_by(RawSivepGripe.municipio_ibge)
        .order_by(func.count().desc())
        .limit(10)
    )
    municipios = (await session.execute(municipios_stmt)).all()

    return {
        "filters": {
            "disease": disease,
            "geo_basis": geo_basis,
            "date_from": date_from,
            "date_to": date_to,
        },
        "total_records": total,
        "by_geo_basis": [
            {"geo_basis": gb, "count": cnt} for gb, cnt in geo_basis_rows
        ],
        "top_municipios": [
            {"municipio_ibge": m, "count": cnt} for m, cnt in municipios
        ],
    }

@router.get("/raw/insights")
async def raw_insights(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    disease: str | None = Query(default="srag"),
    geo_basis: str | None = Query(default=None),
    top_n: int = Query(default=10, ge=3, le=50),
    session: AsyncSession = Depends(get_db),
):
    """
    Insights: headline + evolução diária + concentração + top municípios.
    """
    filters = []
    if disease:
        filters.append(RawSivepGripe.disease == disease)
    if geo_basis:
        filters.append(RawSivepGripe.geo_basis == geo_basis)
    if date_from:
        filters.append(RawSivepGripe.ref_date >= date_from)
    if date_to:
        filters.append(RawSivepGripe.ref_date <= date_to)

    total_stmt = select(func.count()).select_from(RawSivepGripe).where(*filters)
    total = int((await session.execute(total_stmt)).scalar() or 0)

    win_stmt = select(
        func.min(RawSivepGripe.ref_date),
        func.max(RawSivepGripe.ref_date),
    ).where(*filters)
    min_ref, max_ref = (await session.execute(win_stmt)).one()

    daily_stmt = (
        select(RawSivepGripe.ref_date, func.count().label("count"))
        .where(*filters)
        .group_by(RawSivepGripe.ref_date)
        .order_by(RawSivepGripe.ref_date.asc())
    )
    daily_rows = (await session.execute(daily_stmt)).all()

    top_stmt = (
        select(RawSivepGripe.municipio_ibge, func.count().label("count"))
        .where(*filters)
        .group_by(RawSivepGripe.municipio_ibge)
        .order_by(func.count().desc())
        .limit(top_n)
    )
    top_rows = (await session.execute(top_stmt)).all()

    top_total = sum(int(r.count) for r in top_rows) if top_rows else 0
    top1 = int(top_rows[0].count) if top_rows else 0
    top5 = sum(int(r.count) for r in top_rows[:5]) if len(top_rows) >= 5 else top_total

    def pct(a: int, b: int) -> float:
        return round((a / b) * 100, 2) if b else 0.0

    uf_map = {
        "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
        "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
        "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
        "41": "PR", "42": "SC", "43": "RS",
        "50": "MS", "51": "MT", "52": "GO", "53": "DF",
    }

    top_items = []
    for m, cnt in top_rows:
        ibge = str(m)
        uf = uf_map.get(ibge[:2], None)
        top_items.append(
            {
                "municipio_ibge": ibge,
                "uf": uf,
                "count": int(cnt),
                "share_total_pct": pct(int(cnt), total),
            }
        )

    if total == 0:
        headline = "Nenhum registro encontrado com os filtros atuais."
    else:
        headline = (
            f"Foram {total} registros"
            + (f" entre {min_ref} e {max_ref}" if min_ref and max_ref else "")
            + (f" para disease='{disease}'" if disease else "")
            + (f" (geo_basis='{geo_basis}')" if geo_basis else "")
            + f". O top 1 município concentra {pct(top1, total)}% e o top 5 concentra {pct(top5, total)}%."
        )

    return {
        "filters": {
            "disease": disease,
            "geo_basis": geo_basis,
            "date_from": date_from,
            "date_to": date_to,
            "top_n": top_n,
        },
        "headline": headline,
        "total_records": total,
        "window": {"min_ref_date": min_ref, "max_ref_date": max_ref},
        "concentration": {
            "top1_count": top1,
            "top1_share_pct": pct(top1, total),
            "top5_count": top5,
            "top5_share_pct": pct(top5, total),
        },
        "daily": [{"ref_date": d, "count": int(c)} for d, c in daily_rows],
        "top_municipios": top_items,
    }