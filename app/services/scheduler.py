from __future__ import annotations
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.collectors.infodengue import fetch_infodengue_alertcity
from app.collectors.who_don import fetch_who_dons
from app.crud import upsert_bulletin, upsert_cases_weekly, upsert_indicators_weekly
from app.models import IngestionTarget
from app.services.alert_engine import run_alert_engine_for_city
from app.settings import settings
from app.services.normalizers import normalize_infodengue_row

def build_scheduler(get_session_factory):
    scheduler = AsyncIOScheduler()

    async def sync_all():
        async with get_session_factory() as db:
            try:
                await sync_who(db)
                await db.commit()
            except Exception as e:
                print("ERRO sync_who:", repr(e))
                await db.rollback()

            try:
                await sync_infodengue(db)
                await db.commit()
            except Exception as e:
                print("ERRO sync_infodengue:", repr(e))
                await db.rollback()

            try:
                await run_alerts(db)
                await db.commit()
            except Exception as e:
                print("ERRO run_alerts:", repr(e))
                await db.rollback()

    async def sync_who(db: AsyncSession):
        items = await fetch_who_dons(settings.who_don_url)

        for it in items:
            external_id = str(it.get("id") or it.get("Id") or it.get("key") or it.get("uuid") or "")

            title = (
                it.get("title")
                or it.get("Title")
                or it.get("headline")
                or it.get("Headline")
                or "WHO Disease Outbreak News"
            )

            published = (
                it.get("published")
                or it.get("Published")
                or it.get("publishedAt")
                or it.get("PublishedAt")
                or it.get("publishedDate")
                or it.get("PublishedDate")
                or it.get("date")
                or it.get("Date")
                or it.get("startDate")
                or it.get("StartDate")
                or it.get("created")
                or it.get("Created")
            )

            url = it.get("url") or it.get("Url") or it.get("link") or it.get("Link")
            if not url:
                slug = it.get("urlName") or it.get("UrlName") or it.get("slug") or it.get("Slug")
                if slug:
                    url = f"https://www.who.int/emergencies/disease-outbreak-news/item/{slug}"

            summary = it.get("summary") or it.get("Summary") or it.get("description") or it.get("Description") or None

            pub_dt = datetime.now(timezone.utc)
            if isinstance(published, str) and published.strip():
                txt = published.strip().replace("Z", "+00:00")

                if len(txt) == 10 and txt[4] == "-" and txt[7] == "-":
                    txt = f"{txt}T00:00:00+00:00"

                try:
                    pub_dt = datetime.fromisoformat(txt)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pub_dt = datetime.now(timezone.utc)

            await upsert_bulletin(
                db,
                dict(
                    source_code="WHO_DON",
                    external_id=external_id or title,
                    title=title,
                    published_at=pub_dt,
                    url=url,
                    summary=summary,
                    raw=it,
                ),
            )

    async def sync_infodengue(db: AsyncSession):
        q = await db.execute(
            select(IngestionTarget).where(
                IngestionTarget.enabled.is_(True),
                IngestionTarget.source_code == "INFODENGUE",
            )
        )
        targets = q.scalars().all()
        if not targets:
            return

        for t in targets:
            rows = await fetch_infodengue_alertcity(
                settings.infodengue_alertcity_url,
                geocode=t.geo_code,
                disease=t.disease,
                ew_start=t.ew_start,
                ew_end=t.ew_end,
                ey_start=t.ey_start,
                ey_end=t.ey_end,
            )

            for r in rows:
                mapped = normalize_infodengue_row(r, disease=t.disease, geo_code=t.geo_code)

                await upsert_cases_weekly(
                    db,
                    dict(
                        source_code="INFODENGUE",
                        disease=t.disease,
                        geo_level="city",
                        geo_code=t.geo_code,
                        year=mapped["year"],
                        epiweek=mapped["epiweek"],
                        cases=mapped["cases_reported"],
                        raw=mapped["raw"],
                    ),
                )

                await upsert_indicators_weekly(
                    db,
                    dict(
                        source_code="INFODENGUE",
                        disease=t.disease,
                        geo_level="city",
                        geo_code=t.geo_code,
                        year=mapped["year"],
                        epiweek=mapped["epiweek"],
                        incidence=mapped["incidence_100k"],
                        rt=mapped["rt_point"],
                        alert_level=mapped["alert_level"],
                        raw=mapped["raw"],
                    ),
                )

    async def run_alerts(db: AsyncSession):
        geocodes = [x.strip() for x in settings.infodengue_default_geocodes.split(",") if x.strip()]
        diseases = [x.strip() for x in settings.infodengue_default_diseases.split(",") if x.strip()]

        for geo in geocodes:
            for dis in diseases:
                await run_alert_engine_for_city(
                    db,
                    disease=dis,
                    geo_code=geo,
                    cooldown_minutes=settings.alert_cooldown_minutes,
                    threshold_week_cases=300,
                )

    scheduler.add_job(sync_all, "interval", minutes=settings.sync_interval_minutes)
    return scheduler