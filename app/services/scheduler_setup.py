from app.schedulers.demas_scheduler import register_demas_jobs
from app.services.scheduler import register_infodengue_jobs
from app.services.scheduler import register_who_don_jobs


def setup_scheduler(scheduler, session_factory) -> None:
    # antigos (mantém)
    register_infodengue_jobs(scheduler, session_factory)
    register_who_don_jobs(scheduler, session_factory)

    # novo (adiciona)
    register_demas_jobs(scheduler, session_factory)