import uuid
from datetime import date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def iso_week_start(yyyy: int, ww: int) -> date:
    # segunda-feira da semana ISO
    return date.fromisocalendar(yyyy, ww, 1)


def period_week(yyyy: int, ww: int) -> str:
    return f"{yyyy}-W{ww:02d}"


async def normalize_sivep_to_trusted(
    db: AsyncSession,
    *,
    geo_basis: str,
    date_from: date,
    date_to: date,
    batch_id: str,
) -> int:
    """
    Agrega RAW SIVEP -> Trusted (municipio/semana).
    Aqui fazemos o MVP: métrica 'casos' de SRAG por município.
    Você pode ampliar para métricas específicas (covid19, influenza etc.) depois.
    """
    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    # 1) agrega raw em semana ISO
    # OBS: aqui assumimos que raw.ref_date já é uma data válida do registro (ex: dt_sintomas ou dt_notificacao).
    # Se você guardar outra data no raw, ajuste aqui.
    agg_sql = text("""
    WITH base AS (
      SELECT
        municipio_ibge,
        EXTRACT(ISOYEAR FROM ref_date)::int AS isoyear,
        EXTRACT(WEEK FROM ref_date)::int AS isoweek,
        COUNT(*)::numeric AS casos
      FROM raw_sivep_gripe
      WHERE geo_basis = :geo_basis
        AND ref_date >= :date_from
        AND ref_date <= :date_to
      GROUP BY municipio_ibge, EXTRACT(ISOYEAR FROM ref_date), EXTRACT(WEEK FROM ref_date)
    )
    SELECT municipio_ibge, isoyear, isoweek, casos
    FROM base
    ORDER BY isoyear, isoweek;
    """)

    res = await db.execute(
        agg_sql,
        {"geo_basis": geo_basis, "date_from": date_from, "date_to": date_to},
    )
    rows = res.mappings().all()

    if not rows:
        return 0

    # 2) upsert no trusted
    upsert_sql = text("""
    INSERT INTO epi_trusted_series (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge,
      year, epiweek, period, date_ref,
      value, value_type, extra, batch_id
    )
    VALUES (
      :id, :disease, :source, :metric, :granularity, :geo_basis,
      NULL, :municipio_ibge,
      :year, :epiweek, :period, :date_ref,
      :value, :value_type, :extra::jsonb, :batch_id
    )
    ON CONFLICT ON CONSTRAINT uq_epi_trusted_series_key
    DO UPDATE SET
      value = EXCLUDED.value,
      extra = EXCLUDED.extra,
      batch_id = EXCLUDED.batch_id,
      ingested_at = now();
    """)

    inserted = 0
    for r in rows:
        yyyy = int(r["isoyear"])
        ww = int(r["isoweek"])
        await db.execute(
            upsert_sql,
            {
                "id": str(uuid.uuid4()),
                "disease": "srag",
                "source": "sivep_gripe",
                "metric": "casos",
                "granularity": "municipio",
                "geo_basis": geo_basis,
                "municipio_ibge": r["municipio_ibge"],
                "year": yyyy,
                "epiweek": ww,
                "period": period_week(yyyy, ww),
                "date_ref": iso_week_start(yyyy, ww),
                "value": float(r["casos"]),
                "value_type": "integer",
                "extra": "{}",
                "batch_id": batch_id,
            },
        )
        inserted += 1

        if inserted % 500 == 0:
            await db.commit()

    await db.commit()

    # 3) atualizar coverage (municipio por municipio)
    coverage_sql = text("""
    INSERT INTO epi_trusted_coverage (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge, date_min, date_max
    )
    SELECT
      gen_random_uuid(),
      'srag', 'sivep_gripe', 'casos', 'municipio', :geo_basis,
      NULL, municipio_ibge, MIN(date_ref), MAX(date_ref)
    FROM epi_trusted_series
    WHERE source='sivep_gripe'
      AND disease='srag'
      AND metric='casos'
      AND granularity='municipio'
      AND geo_basis=:geo_basis
    GROUP BY municipio_ibge
    ON CONFLICT ON CONSTRAINT uq_epi_coverage_key
    DO UPDATE SET
      date_min = EXCLUDED.date_min,
      date_max = EXCLUDED.date_max,
      updated_at = now();
    """)

    await db.execute(coverage_sql, {"geo_basis": geo_basis})
    await db.commit()

    return inserted

async def normalize_sinan_to_trusted(
    db: AsyncSession,
    *,
    geo_basis: str,
    disease: str,
    date_from: date,
    date_to: date,
    batch_id: str,
) -> int:
    """
    RAW SINAN -> Trusted (municipio/semana).
    Métrica MVP: 'casos' (soma de count se existir; senão conta registros).
    """
    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    agg_sql = text("""
    WITH base AS (
      SELECT
        municipio_ibge,
        EXTRACT(ISOYEAR FROM ref_date)::int AS isoyear,
        EXTRACT(WEEK FROM ref_date)::int AS isoweek,
        SUM(COALESCE((raw->>'count')::numeric, 1))::numeric AS casos
      FROM raw_sinan
      WHERE geo_basis = :geo_basis
        AND disease = :disease
        AND ref_date >= :date_from
        AND ref_date <= :date_to
      GROUP BY municipio_ibge, EXTRACT(ISOYEAR FROM ref_date), EXTRACT(WEEK FROM ref_date)
    )
    SELECT municipio_ibge, isoyear, isoweek, casos
    FROM base
    ORDER BY isoyear, isoweek;
    """)

    res = await db.execute(
        agg_sql,
        {"geo_basis": geo_basis, "disease": disease, "date_from": date_from, "date_to": date_to},
    )
    rows = res.mappings().all()
    if not rows:
        return 0

    upsert_sql = text("""
    INSERT INTO epi_trusted_series (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge,
      year, epiweek, period, date_ref,
      value, value_type, extra, batch_id
    )
    VALUES (
      :id, :disease, :source, :metric, :granularity, :geo_basis,
      NULL, :municipio_ibge,
      :year, :epiweek, :period, :date_ref,
      :value, :value_type, :extra::jsonb, :batch_id
    )
    ON CONFLICT ON CONSTRAINT uq_epi_trusted_series_key
    DO UPDATE SET
      value = EXCLUDED.value,
      extra = EXCLUDED.extra,
      batch_id = EXCLUDED.batch_id,
      ingested_at = now();
    """)

    inserted = 0
    for r in rows:
        yyyy = int(r["isoyear"])
        ww = int(r["isoweek"])
        await db.execute(
            upsert_sql,
            {
                "id": str(uuid.uuid4()),
                "disease": disease,
                "source": "datasus_sinan",
                "metric": "casos",
                "granularity": "municipio",
                "geo_basis": geo_basis,
                "municipio_ibge": r["municipio_ibge"],
                "year": yyyy,
                "epiweek": ww,
                "period": period_week(yyyy, ww),
                "date_ref": iso_week_start(yyyy, ww),
                "value": float(r["casos"]),
                "value_type": "integer",
                "extra": "{}",
                "batch_id": batch_id,
            },
        )
        inserted += 1
        if inserted % 500 == 0:
            await db.commit()

    await db.commit()

    # coverage
    coverage_sql = text("""
    INSERT INTO epi_trusted_coverage (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge, date_min, date_max
    )
    SELECT
      gen_random_uuid(),
      :disease, 'datasus_sinan', 'casos', 'municipio', :geo_basis,
      NULL, municipio_ibge, MIN(date_ref), MAX(date_ref)
    FROM epi_trusted_series
    WHERE source='datasus_sinan'
      AND disease=:disease
      AND metric='casos'
      AND granularity='municipio'
      AND geo_basis=:geo_basis
    GROUP BY municipio_ibge
    ON CONFLICT ON CONSTRAINT uq_epi_coverage_key
    DO UPDATE SET
      date_min = EXCLUDED.date_min,
      date_max = EXCLUDED.date_max,
      updated_at = now();
    """)
    await db.execute(coverage_sql, {"geo_basis": geo_basis, "disease": disease})
    await db.commit()

    return inserted


async def normalize_sim_to_trusted(
    db: AsyncSession,
    *,
    geo_basis: str,
    disease: str,
    date_from: date,
    date_to: date,
    batch_id: str,
) -> int:
    """
    RAW SIM -> Trusted (municipio/semana).
    Métrica MVP: 'obitos' (soma de count se existir; senão conta registros).
    """
    if geo_basis not in ("residencia", "notificacao"):
        raise ValueError("geo_basis deve ser residencia|notificacao")

    agg_sql = text("""
    WITH base AS (
      SELECT
        municipio_ibge,
        EXTRACT(ISOYEAR FROM ref_date)::int AS isoyear,
        EXTRACT(WEEK FROM ref_date)::int AS isoweek,
        SUM(COALESCE((raw->>'count')::numeric, 1))::numeric AS obitos
      FROM raw_sim
      WHERE geo_basis = :geo_basis
        AND disease = :disease
        AND ref_date >= :date_from
        AND ref_date <= :date_to
      GROUP BY municipio_ibge, EXTRACT(ISOYEAR FROM ref_date), EXTRACT(WEEK FROM ref_date)
    )
    SELECT municipio_ibge, isoyear, isoweek, obitos
    FROM base
    ORDER BY isoyear, isoweek;
    """)

    res = await db.execute(
        agg_sql,
        {"geo_basis": geo_basis, "disease": disease, "date_from": date_from, "date_to": date_to},
    )
    rows = res.mappings().all()
    if not rows:
        return 0

    upsert_sql = text("""
    INSERT INTO epi_trusted_series (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge,
      year, epiweek, period, date_ref,
      value, value_type, extra, batch_id
    )
    VALUES (
      :id, :disease, :source, :metric, :granularity, :geo_basis,
      NULL, :municipio_ibge,
      :year, :epiweek, :period, :date_ref,
      :value, :value_type, :extra::jsonb, :batch_id
    )
    ON CONFLICT ON CONSTRAINT uq_epi_trusted_series_key
    DO UPDATE SET
      value = EXCLUDED.value,
      extra = EXCLUDED.extra,
      batch_id = EXCLUDED.batch_id,
      ingested_at = now();
    """)

    inserted = 0
    for r in rows:
        yyyy = int(r["isoyear"])
        ww = int(r["isoweek"])
        await db.execute(
            upsert_sql,
            {
                "id": str(uuid.uuid4()),
                "disease": disease,
                "source": "datasus_sim",
                "metric": "obitos",
                "granularity": "municipio",
                "geo_basis": geo_basis,
                "municipio_ibge": r["municipio_ibge"],
                "year": yyyy,
                "epiweek": ww,
                "period": period_week(yyyy, ww),
                "date_ref": iso_week_start(yyyy, ww),
                "value": float(r["obitos"]),
                "value_type": "integer",
                "extra": "{}",
                "batch_id": batch_id,
            },
        )
        inserted += 1
        if inserted % 500 == 0:
            await db.commit()

    await db.commit()

    # coverage
    coverage_sql = text("""
    INSERT INTO epi_trusted_coverage (
      id, disease, source, metric, granularity, geo_basis,
      uf, municipio_ibge, date_min, date_max
    )
    SELECT
      gen_random_uuid(),
      :disease, 'datasus_sim', 'obitos', 'municipio', :geo_basis,
      NULL, municipio_ibge, MIN(date_ref), MAX(date_ref)
    FROM epi_trusted_series
    WHERE source='datasus_sim'
      AND disease=:disease
      AND metric='obitos'
      AND granularity='municipio'
      AND geo_basis=:geo_basis
    GROUP BY municipio_ibge
    ON CONFLICT ON CONSTRAINT uq_epi_coverage_key
    DO UPDATE SET
      date_min = EXCLUDED.date_min,
      date_max = EXCLUDED.date_max,
      updated_at = now();
    """)
    await db.execute(coverage_sql, {"geo_basis": geo_basis, "disease": disease})
    await db.commit()

    return inserted