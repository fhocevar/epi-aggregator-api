from __future__ import annotations

from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.demas_import_service import DemasImportService
from app.services.demas_sources import DEMAS_S3_SOURCES


def register_demas_s3_jobs(scheduler, session_factory: async_sessionmaker[AsyncSession]) -> None:
    """
    DEMAS S3 fallback: baixa ZIP/CSV da Amazon S3 e importa no banco.
    """

    async def job_demas_s3_bulk():
        svc = DemasImportService(session_factory=session_factory)
        r = await svc.import_bulk_from_sources(
            sources=DEMAS_S3_SOURCES,
            timeout_seconds=600,
            chunk_size=2000,
        )
        print(f"[{datetime.now()}] DEMAS S3 bulk:", r)

    # roda todo dia 04:40 (antes do daily DEMAS online)
    scheduler.add_job(
        job_demas_s3_bulk,
        CronTrigger(hour=4, minute=40),
        id="demas_s3_bulk_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


async def run_demas_s3_bulk_import(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    """
    Execução manual (útil para endpoint / operação).
    """
    svc = DemasImportService(session_factory=session_factory)
    return await svc.import_bulk_from_sources(
        sources=DEMAS_S3_SOURCES,
        timeout_seconds=600,
        chunk_size=2000,
    )