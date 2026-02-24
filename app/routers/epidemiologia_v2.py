from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter(prefix="/epi/v2", tags=["Epidemiologia v2"])

GeoBasis = Literal["residencia", "notificacao"]
Granularity = Literal["municipio", "uf", "br"]


@router.get("/series")
async def series(
    disease: str = Query(...),
    source: Optional[str] = Query(None),
    metric: Optional[str] = Query(None),
    granularity: Granularity = Query("municipio"),
    geo_basis: GeoBasis = Query("residencia"),
    uf: Optional[str] = Query(None, min_length=2, max_length=2),
    municipio_ibge: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    sql = text("""
    SELECT
      period, date_ref, uf, municipio_ibge,
      disease, source, metric, value::float AS value, value_type,
      geo_basis, granularity, extra
    FROM epi_trusted_series
    WHERE 1=1
      AND disease = :disease
      AND (:source IS NULL OR source = :source)
      AND (:metric IS NULL OR metric = :metric)
      AND granularity = :granularity
      AND geo_basis = :geo_basis
      AND (:uf IS NULL OR uf = :uf)
      AND (:municipio_ibge IS NULL OR municipio_ibge = :municipio_ibge)
      AND (:date_from IS NULL OR date_ref >= :date_from)
      AND (:date_to IS NULL OR date_ref <= :date_to)
    ORDER BY date_ref ASC
    """)

    result = await db.execute(sql, {
        "disease": disease,
        "source": source,
        "metric": metric,
        "granularity": granularity,
        "geo_basis": geo_basis,
        "uf": uf,
        "municipio_ibge": municipio_ibge,
        "date_from": date_from,
        "date_to": date_to,
    })
    rows = [dict(r) for r in result.mappings().all()]
    return {"status_code": 200, "message": "consulta realizada com sucesso", "total_items": len(rows), "items": rows}


@router.get("/latest")
async def latest(
    disease: str = Query(...),
    source: Optional[str] = Query(None),
    metric: Optional[str] = Query(None),
    granularity: Granularity = Query("municipio"),
    geo_basis: GeoBasis = Query("residencia"),
    uf: Optional[str] = Query(None, min_length=2, max_length=2),
    municipio_ibge: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    sql = text("""
    SELECT
      period, date_ref, uf, municipio_ibge,
      disease, source, metric, value::float AS value, value_type,
      geo_basis, granularity, extra
    FROM epi_trusted_series
    WHERE 1=1
      AND disease = :disease
      AND (:source IS NULL OR source = :source)
      AND (:metric IS NULL OR metric = :metric)
      AND granularity = :granularity
      AND geo_basis = :geo_basis
      AND (:uf IS NULL OR uf = :uf)
      AND (:municipio_ibge IS NULL OR municipio_ibge = :municipio_ibge)
    ORDER BY date_ref DESC
    LIMIT 1
    """)

    result = await db.execute(sql, {
        "disease": disease,
        "source": source,
        "metric": metric,
        "granularity": granularity,
        "geo_basis": geo_basis,
        "uf": uf,
        "municipio_ibge": municipio_ibge,
    })
    row = result.mappings().first()
    return {"status_code": 200, "message": "consulta realizada com sucesso", "item": dict(row) if row else None}


@router.get("/meta/coverage")
async def coverage(
    disease: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    metric: Optional[str] = Query(None),
    granularity: Optional[Granularity] = Query(None),
    geo_basis: Optional[GeoBasis] = Query(None),
    uf: Optional[str] = Query(None, min_length=2, max_length=2),
    municipio_ibge: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    sql = text("""
    SELECT disease, source, metric, granularity, geo_basis, uf, municipio_ibge, date_min, date_max, updated_at
    FROM epi_trusted_coverage
    WHERE 1=1
      AND (:disease IS NULL OR disease = :disease)
      AND (:source IS NULL OR source = :source)
      AND (:metric IS NULL OR metric = :metric)
      AND (:granularity IS NULL OR granularity = :granularity)
      AND (:geo_basis IS NULL OR geo_basis = :geo_basis)
      AND (:uf IS NULL OR uf = :uf)
      AND (:municipio_ibge IS NULL OR municipio_ibge = :municipio_ibge)
    ORDER BY disease, source, metric, granularity, geo_basis;
    """)
    result = await db.execute(sql, {
        "disease": disease,
        "source": source,
        "metric": metric,
        "granularity": granularity,
        "geo_basis": geo_basis,
        "uf": uf,
        "municipio_ibge": municipio_ibge,
    })
    rows = [dict(r) for r in result.mappings().all()]
    return {"status_code": 200, "message": "consulta realizada com sucesso", "total_items": len(rows), "items": rows}