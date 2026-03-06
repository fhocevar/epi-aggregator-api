from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.models import Bulletin, CasesWeekly, IndicatorsWeekly, EpiAlert, AlertDedup

async def upsert_bulletin(db: AsyncSession, item: dict) -> None:
    stmt = insert(Bulletin).values(**item)
    stmt = stmt.on_conflict_do_nothing(index_elements=["source_code", "external_id"])
    await db.execute(stmt)

async def upsert_cases_weekly(db: AsyncSession, item: dict) -> None:
    stmt = insert(CasesWeekly).values(**item)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_code", "disease", "geo_code", "year", "epiweek"],
        set_={"cases": stmt.excluded.cases, "raw": stmt.excluded.raw},
    )
    await db.execute(stmt)


async def upsert_indicators_weekly(db: AsyncSession, item: dict) -> None:
    stmt = insert(IndicatorsWeekly).values(**item)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_code", "disease", "geo_code", "year", "epiweek"],
        set_={
            "incidence": stmt.excluded.incidence,
            "rt": stmt.excluded.rt,
            "alert_level": stmt.excluded.alert_level,
            "raw": stmt.excluded.raw,
        },
    )
    await db.execute(stmt)

async def create_generated_alert(db: AsyncSession, alert: dict) -> bool:
    stmt = insert(EpiAlert).values(**alert)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["source_code", "disease", "geo_code", "year", "epiweek", "title"]
    )
    res = await db.execute(stmt)
    return True

async def get_dedup(db: AsyncSession, fingerprint: str):
    q = await db.execute(select(AlertDedup).where(AlertDedup.fingerprint == fingerprint))
    return q.scalar_one_or_none()

async def upsert_dedup(db: AsyncSession, fingerprint: str, last_sent_at):
    stmt = insert(AlertDedup).values(fingerprint=fingerprint, last_sent_at=last_sent_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fingerprint"],
        set_={"last_sent_at": stmt.excluded.last_sent_at},
    )
    await db.execute(stmt)
