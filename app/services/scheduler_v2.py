from datetime import datetime, timedelta, date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.settings import settings
from app.collectors.sivep_gripe import ingest_sivep_gripe
from app.services.normalizers_v2 import normalize_sivep_to_trusted
from app.collectors.datasus_sinan import ingest_sinan
from app.collectors.datasus_sim import ingest_sim
from app.services.normalizers_v2 import normalize_sinan_to_trusted, normalize_sim_to_trusted

def build_scheduler_v2(AsyncSessionLocal: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    async def job_sivep_ingest_and_normalize(geo_basis: str):
        days = getattr(settings, "v2_window_days", 90)
        date_to = date.today()
        date_from = date_to - timedelta(days=days)

        async with AsyncSessionLocal() as db:
            inserted_raw = await ingest_sivep_gripe(
                db,
                geo_basis=geo_basis,
                url=settings.sivep_gripe_url,
                date_from=date_from,
                date_to=date_to,
                timeout_sec=getattr(settings, "sivep_timeout_sec", 60),
                batch_id=f"sivep-ingest-{geo_basis}-{datetime.utcnow().isoformat()}",
            )

            _ = await normalize_sivep_to_trusted(
                db,
                geo_basis=geo_basis,
                date_from=date_from,
                date_to=date_to,
                batch_id=f"sivep-norm-{geo_basis}-{datetime.utcnow().isoformat()}",
            )

    scheduler.add_job(
        job_sivep_ingest_and_normalize,
        "interval",
        minutes=getattr(settings, "v2_sync_interval_minutes", 720),
        args=["residencia"],
        id="v2_sivep_residencia",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        job_sivep_ingest_and_normalize,
        "interval",
        minutes=getattr(settings, "v2_sync_interval_minutes", 720),
        args=["notificacao"],
        id="v2_sivep_notificacao",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    return scheduler