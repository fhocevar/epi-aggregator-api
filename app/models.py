import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, Integer, Float, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # WHO_DON / INFODENGUE
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Bulletin(Base):
    __tablename__ = "bulletins"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_code: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    url: Mapped[str] = mapped_column(String(800), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (UniqueConstraint("source_code", "external_id", name="uq_bulletin_source_external"),)


class EpiAlert(Base):
    __tablename__ = "epi_alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_code: Mapped[str] = mapped_column(String(50), nullable=False)  # INFODENGUE ou GENERATED
    disease: Mapped[str] = mapped_column(String(50), nullable=False)      # dengue|zika|chikungunya
    geo_level: Mapped[str] = mapped_column(String(20), nullable=False)    # city/state/country
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)     # IBGE p/ city
    geo_name: Mapped[str] = mapped_column(String(200), nullable=True)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    epiweek: Mapped[int] = mapped_column(Integer, nullable=False)

    severity: Mapped[str] = mapped_column(String(20), nullable=False)     # info|warning|high|critical
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_code", "disease", "geo_code", "year", "epiweek", "title",
                         name="uq_epi_alert_identity"),
    )


class CasesWeekly(Base):
    __tablename__ = "cases_weekly"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_code: Mapped[str] = mapped_column(String(50), nullable=False)  # INFODENGUE
    disease: Mapped[str] = mapped_column(String(50), nullable=False)
    geo_level: Mapped[str] = mapped_column(String(20), nullable=False)
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    epiweek: Mapped[int] = mapped_column(Integer, nullable=False)

    cases: Mapped[int] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_code", "disease", "geo_code", "year", "epiweek",
                         name="uq_cases_weekly"),
    )


class IndicatorsWeekly(Base):
    __tablename__ = "indicators_weekly"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_code: Mapped[str] = mapped_column(String(50), nullable=False)
    disease: Mapped[str] = mapped_column(String(50), nullable=False)
    geo_level: Mapped[str] = mapped_column(String(20), nullable=False)
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    epiweek: Mapped[int] = mapped_column(Integer, nullable=False)

    incidence: Mapped[float] = mapped_column(Float, nullable=True)
    rt: Mapped[float] = mapped_column(Float, nullable=True)
    alert_level: Mapped[int] = mapped_column(Integer, nullable=True)  # nível do Infodengue (quando existir)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_code", "disease", "geo_code", "year", "epiweek",
                         name="uq_indicators_weekly"),
    )


class AlertDedup(Base):
    __tablename__ = "alert_dedup"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class IngestionTarget(Base):
    __tablename__ = "ingestion_targets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_code: Mapped[str] = mapped_column(String(50), nullable=False)  # INFODENGUE
    geo_code: Mapped[str] = mapped_column(String(50), nullable=False)     # IBGE city code
    disease: Mapped[str] = mapped_column(String(50), nullable=False)      # dengue|chikungunya|zika

    ey_start: Mapped[int] = mapped_column(Integer, nullable=False, default=2025)
    ey_end: Mapped[int] = mapped_column(Integer, nullable=False, default=2026)
    ew_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ew_end: Mapped[int] = mapped_column(Integer, nullable=False, default=53)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("source_code", "geo_code", "disease", name="uq_target_source_geo_disease"),
    )


class NotificationTarget(Base):
    __tablename__ = "notification_targets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    target_type: Mapped[str] = mapped_column(String(30), nullable=False)  # teams_webhook|generic_webhook
    target_url: Mapped[str] = mapped_column(String(800), nullable=False)
    min_severity: Mapped[str] = mapped_column(String(20), nullable=False, default="high")  # info|warning|high|critical
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # filtros opcionais
    disease_filter: Mapped[dict] = mapped_column(JSONB, nullable=True)  # {"in": ["dengue","zika"]}
    geo_filter: Mapped[dict] = mapped_column(JSONB, nullable=True)      # {"in": ["3304557","3550308"]}

class RawSivepGripe(Base):
    __tablename__ = "raw_sivep_gripe"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_date: Mapped[date] = mapped_column(Date, nullable=False)

    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False)  # residencia|notificacao
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=False)

    disease: Mapped[str] = mapped_column(String(50), nullable=False, default="srag")
    external_id: Mapped[str] = mapped_column(String(200), nullable=True)

    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint("geo_basis", "hash", name="uq_raw_sivep_gripe_hash"),
        Index("ix_raw_sivep_gripe_q1", "geo_basis", "municipio_ibge", "ref_date"),
        Index("ix_raw_sivep_gripe_q2", "year", "ref_date"),
    )

