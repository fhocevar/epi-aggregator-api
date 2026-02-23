from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import IngestionTarget, NotificationTarget
from app.schemas import (
    IngestionTargetCreate, IngestionTargetOut,
    NotificationTargetCreate, NotificationTargetOut
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/targets", response_model=list[IngestionTargetOut])
async def list_targets(db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(IngestionTarget).order_by(IngestionTarget.source_code, IngestionTarget.geo_code))
    rows = q.scalars().all()
    return [
        {
            "id": str(r.id),
            "source_code": r.source_code,
            "geo_code": r.geo_code,
            "disease": r.disease,
            "ey_start": r.ey_start,
            "ey_end": r.ey_end,
            "ew_start": r.ew_start,
            "ew_end": r.ew_end,
            "enabled": r.enabled,
        }
        for r in rows
    ]


@router.post("/targets", response_model=IngestionTargetOut, status_code=201)
async def create_target(payload: IngestionTargetCreate, db: AsyncSession = Depends(get_db)):
    # valida básica do disease
    if payload.source_code == "INFODENGUE" and payload.disease not in ("dengue", "chikungunya", "zika"):
        raise HTTPException(status_code=400, detail="disease inválida para INFODENGUE (use dengue|chikungunya|zika).")

    row = IngestionTarget(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {**payload.model_dump(), "id": str(row.id)}


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(target_id: str, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(IngestionTarget).where(IngestionTarget.id == target_id))
    row = q.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="target não encontrado")
    await db.delete(row)
    await db.commit()
    return None


@router.get("/notifications", response_model=list[NotificationTargetOut])
async def list_notifications(db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(NotificationTarget).order_by(NotificationTarget.target_type))
    rows = q.scalars().all()
    return [
        {
            "id": str(r.id),
            "target_type": r.target_type,
            "target_url": r.target_url,
            "min_severity": r.min_severity,
            "enabled": r.enabled,
            "disease_filter": r.disease_filter,
            "geo_filter": r.geo_filter,
        }
        for r in rows
    ]


@router.post("/notifications", response_model=NotificationTargetOut, status_code=201)
async def create_notification(payload: NotificationTargetCreate, db: AsyncSession = Depends(get_db)):
    if payload.target_type not in ("teams_webhook", "generic_webhook"):
        raise HTTPException(status_code=400, detail="target_type inválido (teams_webhook|generic_webhook).")

    row = NotificationTarget(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {**payload.model_dump(), "id": str(row.id)}
