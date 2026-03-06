import hashlib
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CasesWeekly, NotificationTarget
from app.crud import get_dedup, upsert_dedup, create_generated_alert
from app.services.notifier import send_notification

def fp(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:40]

def severity_from_ratio(ratio: float) -> str:
    if ratio >= 2.0:
        return "critical"
    if ratio >= 1.6:
        return "high"
    if ratio >= 1.3:
        return "warning"
    return "info"

async def run_alert_engine_for_city(
    db: AsyncSession,
    disease: str,
    geo_code: str,
    cooldown_minutes: int,
    threshold_week_cases: int = 50,
) -> list[dict]:
    """
    Gera alertas a partir de CasesWeekly (InfoDengue) e:
      - salva em EpiAlert (source_code=GENERATED)
      - aplica dedupe/cooldown via AlertDedup
      - notifica via NotificationTarget (Teams/Webhook)
    """

    q = await db.execute(
        select(CasesWeekly)
        .where(
            CasesWeekly.source_code == "INFODENGUE",
            CasesWeekly.disease == disease,
            CasesWeekly.geo_code == geo_code,
        )
        .order_by(desc(CasesWeekly.year), desc(CasesWeekly.epiweek))
        .limit(6)
    )
    rows = q.scalars().all()
    if len(rows) < 2:
        return []

    latest = rows[0]
    prev_weeks = rows[1:5]

    latest_cases = latest.cases or 0
    base_vals = [(r.cases or 0) for r in prev_weeks if r.cases is not None]

    alerts: list[dict] = []

    if latest_cases >= threshold_week_cases:
        sev = "high" if latest_cases >= threshold_week_cases * 2 else "warning"
        alerts.append(
            {
                "kind": "threshold",
                "severity": sev,
                "title": f"{disease.upper()} - limiar semanal atingido",
                "message": f"Casos na SE {latest.epiweek}/{latest.year}: {latest_cases} (limiar={threshold_week_cases})",
                "evidence": {"latest_cases": latest_cases, "threshold": threshold_week_cases},
                "year": latest.year,
                "epiweek": latest.epiweek,
            }
        )

    if base_vals:
        base_avg = sum(base_vals) / max(len(base_vals), 1)
        ratio = (latest_cases / base_avg) if base_avg > 0 else (999.0 if latest_cases > 0 else 1.0)
        sev = severity_from_ratio(ratio)
        if sev in ("warning", "high", "critical") and latest_cases >= 50:
            alerts.append(
                {
                    "kind": "growth",
                    "severity": sev,
                    "title": f"{disease.upper()} - crescimento anormal",
                    "message": (
                        f"SE {latest.epiweek}/{latest.year}: {latest_cases} "
                        f"vs média 4 semanas: {base_avg:.1f} (ratio={ratio:.2f})"
                    ),
                    "evidence": {"latest_cases": latest_cases, "baseline_avg": base_avg, "ratio": ratio},
                    "year": latest.year,
                    "epiweek": latest.epiweek,
                }
            )

    if not alerts:
        return []

    nq = await db.execute(select(NotificationTarget).where(NotificationTarget.enabled == True))
    notification_targets = nq.scalars().all()

    created: list[dict] = []
    now = datetime.now(timezone.utc)

    for a in alerts:
        fingerprint = fp("INFODENGUE", disease, geo_code, a["kind"], str(a["year"]), str(a["epiweek"]))
        prev = await get_dedup(db, fingerprint)

        if prev:
            last = prev.last_sent_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last < timedelta(minutes=cooldown_minutes):
                continue

        await create_generated_alert(
            db,
            dict(
                source_code="GENERATED",
                disease=disease,
                geo_level="city",
                geo_code=geo_code,
                geo_name=None,
                year=a["year"],
                epiweek=a["epiweek"],
                severity=a["severity"],
                title=a["title"],
                message=a["message"],
                created_at=now,
                evidence=a["evidence"],
            ),
        )

        await upsert_dedup(db, fingerprint, now)

        alert_payload = {
            "source": "GENERATED",
            "severity": a["severity"],
            "title": a["title"],
            "message": a["message"],
            "disease": disease,
            "geo_code": geo_code,
            "year": a["year"],
            "epiweek": a["epiweek"],
            "evidence": a["evidence"],
            "created_at": now.isoformat(),
        }

        for t in notification_targets:
            try:
                await send_notification(t, alert_payload)
            except Exception:
                pass

        created.append(a)

    return created
