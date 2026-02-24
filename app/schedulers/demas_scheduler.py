from __future__ import annotations

from app.settings import settings
from app.collectors.demas.client import DemasClient
from app.collectors.demas.collector import DemasCollector
from app.normalizers.demas.base import DemasNormalizer
from app.services.demas_service import DemasService


def register_demas_jobs(scheduler, session_factory) -> None:
    """
    session_factory: AsyncSessionLocal (do app/db.py)
    """

    client = DemasClient(
        base_url=settings.demas_base_url,
        timeout_seconds=settings.demas_timeout_seconds,
        token=getattr(settings, "demas_token", None),
        username=getattr(settings, "demas_username", None),
        password=getattr(settings, "demas_password", None),
    )

    collector = DemasCollector(client, page_size=settings.demas_page_size)
    normalizer = DemasNormalizer()
    service = DemasService(client=client, collector=collector, normalizer=normalizer, session_factory=session_factory)

    scheduler.add_job(
        service.sync_dataset,
        "interval",
        minutes=settings.sync_interval_minutes,
        kwargs={"path": "/arboviroses/dengue", "disease": "dengue"},
        id="demas_arboviroses_dengue",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        service.sync_dataset,
        "interval",
        minutes=settings.sync_interval_minutes,
        kwargs={"path": "/arboviroses/chikungunya", "disease": "chikungunya"},
        id="demas_arboviroses_chikungunya",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        service.sync_dataset,
        "interval",
        minutes=settings.sync_interval_minutes,
        kwargs={"path": "/arboviroses/zikavirus", "disease": "zika"},
        id="demas_arboviroses_zika",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        service.sync_dataset,
        "interval",
        minutes=settings.sync_interval_minutes,
        kwargs={"path": "/vigilancia-e-meio-ambiente/srag-2019-2026", "disease": "srag"},
        id="demas_srag_2019_2026",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )