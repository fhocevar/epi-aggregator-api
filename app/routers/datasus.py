from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.collectors.sivep_zip import ingest_sivep_srag_from_zip_url
from app.collectors.sivep_opendatasus import ingest_sivep_srag_opendatasus
from app.settings import settings

router = APIRouter(prefix="/datasus", tags=["DATASUS"])


@router.post("/sync/sivep-srag")
async def sync_sivep_srag(
    geo_basis: str,
    year: int,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
):
    if year == 2024:
        zip_url = settings.opendatasus_sivep_srag_zip_url_2024
    else:
        zip_url = None

    if not zip_url:
        raise HTTPException(
            status_code=400,
            detail=f"Falta configurar a URL do ZIP no .env para o ano {year}. "
                   f"Ex.: OPENDATASUS_SIVEP_SRAG_ZIP_URL_{year}=https://.../INFLUD{str(year)[-2:]}....zip"
 )

    inserted = await ingest_sivep_srag_from_zip_url(
        db,
        geo_basis=geo_basis,
        year=year,
        date_from=date_from,
        date_to=date_to,
        zip_url=zip_url,
        batch_id=f"sivep-{year}",
    )
    return {"status": "ok", "inserted": inserted, "year": year, "geo_basis": geo_basis}