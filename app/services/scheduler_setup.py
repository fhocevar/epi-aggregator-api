# app/services/scheduler_setup.py
from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.schedulers.demas_scheduler import register_demas_jobs
from app.services.demas_s3_scheduler import register_demas_s3_jobs
from app.services.scheduler_v2 import build_scheduler_v2
from app.services.scheduler import build_scheduler

def setup_scheduler(
    scheduler: AsyncIOScheduler,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """
    Pluga tudo num ÚNICO scheduler.
    """
    # v1 (who + infodengue + alerts)
    s1 = build_scheduler(session_factory)
    for job in s1.get_jobs():
        scheduler.add_job(job.func, trigger=job.trigger, args=job.args, kwargs=job.kwargs, id=f"v1_{job.id}", replace_existing=True)

    # v2 (sivep/sinan/sim)
    s2 = build_scheduler_v2(session_factory)
    for job in s2.get_jobs():
        scheduler.add_job(job.func, trigger=job.trigger, args=job.args, kwargs=job.kwargs, id=f"v2_{job.id}", replace_existing=True)

    # DEMAS online
    register_demas_jobs(scheduler, session_factory)

    # DEMAS S3 fallback
    register_demas_s3_jobs(scheduler, session_factory)