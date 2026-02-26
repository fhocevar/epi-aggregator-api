from __future__ import annotations

import os
import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.services.demas_service import DemasSyncService


# ============
# SETTINGS
# ============
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/epiclip")

DEMAS_BASE_URL = os.getenv("DEMAS_BASE_URL", "https://apidadosabertos.saude.gov.br/v1")
DEMAS_TIMEOUT = int(os.getenv("DEMAS_TIMEOUT_SECONDS", "60"))
DEMAS_LIMIT = int(os.getenv("DEMAS_LIMIT", "20"))
DEMAS_SLEEP = float(os.getenv("DEMAS_SLEEP_SECONDS", "0.05"))

# anos padrão arboviroses (ex: "2024,2025,2026")
DEMAS_ARB_YEARS = os.getenv("DEMAS_ARBOVIROSES_YEARS", "2024,2025,2026")
ARB_YEARS = [int(x.strip()) for x in DEMAS_ARB_YEARS.split(",") if x.strip().isdigit()]

TZ = os.getenv("TZ", "America/Sao_Paulo")


def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def job_daily() -> None:
    service = DemasSyncService(
        session_factory=_session_factory(),
        base_url=DEMAS_BASE_URL,
        timeout_seconds=DEMAS_TIMEOUT,
        limit=DEMAS_LIMIT,
        sleep_seconds=DEMAS_SLEEP,
        arboviroses_years=ARB_YEARS,
    )
    r = await service.sync_all_daily()
    print(f"[{datetime.now()}] DEMAS daily:", r)


async def job_weekly_municipios() -> None:
    service = DemasSyncService(
        session_factory=_session_factory(),
        base_url=DEMAS_BASE_URL,
        timeout_seconds=DEMAS_TIMEOUT,
        limit=DEMAS_LIMIT,
        sleep_seconds=DEMAS_SLEEP,
        arboviroses_years=ARB_YEARS,
    )
    r = await service.sync_municipios_weekly()
    print(f"[{datetime.now()}] DEMAS weekly municipios:", r)


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)

    # Daily coleta + normaliza (05:10)
    scheduler.add_job(
        job_daily,
        CronTrigger(hour=5, minute=10),
        id="demas_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Weekly municipios DIM (domingo 06:10)
    scheduler.add_job(
        job_weekly_municipios,
        CronTrigger(day_of_week="sun", hour=6, minute=10),
        id="demas_weekly_municipios",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    return scheduler


if __name__ == "__main__":
    # executa scheduler em loop
    start_scheduler()
    asyncio.get_event_loop().run_forever()