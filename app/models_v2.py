import uuid
from datetime import datetime, date

from sqlalchemy import (
    String, DateTime, Date, Integer, Numeric, Text, Boolean,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class EpiDimDisease(Base):
    __tablename__ = "epi_dim_disease"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_source: Mapped[str] = mapped_column(String(50), nullable=False)
    default_period: Mapped[str] = mapped_column(String(20), nullable=False, default="semanal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

class EpiDimSource(Base):
    __tablename__ = "epi_dim_source"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    update_frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="semanal")
    base_url: Mapped[str] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    license: Mapped[str] = mapped_column(String(200), nullable=True)

class RawSivepGripeV2(Base):
    """
    Armazena dados RAW (staging) do SIVEP-Gripe.
    O normalizer agrega por municipio/semana e popula epi_trusted_series.
    geo_basis:
      - residencia: municipio de residencia
      - notificacao: municipio de notificacao/internacao (depende do campo)
    """
    __tablename__ = "raw_sivep_gripe_v2"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_date: Mapped[date] = mapped_column(Date, nullable=False)
    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=False)
    disease: Mapped[str] = mapped_column(String(50), nullable=False, default="srag")
    external_id: Mapped[str] = mapped_column(String(200), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint("geo_basis", "hash", name="uq_raw_sivep_v2_hash"),
        Index("ix_raw_sivep_q1", "geo_basis", "municipio_ibge", "ref_date"),
        Index("ix_raw_sivep_q2", "year", "ref_date"),
    )

class EpiTrustedSeries(Base):
    """
    Tabela unificada (Trusted) para séries epidemiológicas (v2).
    Chave única para idempotência.
    """
    __tablename__ = "epi_trusted_series"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    disease: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)

    granularity: Mapped[str] = mapped_column(String(20), nullable=False)
    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False, default="residencia")
    uf: Mapped[str] = mapped_column(String(2), nullable=True)
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=True)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    epiweek: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    date_ref: Mapped[date] = mapped_column(Date, nullable=False)

    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="integer")

    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "disease", "source", "metric", "granularity", "geo_basis",
            "uf", "municipio_ibge", "year", "epiweek",
            name="uq_epi_trusted_series_key",
        ),
        Index("ix_epi_trusted_q1", "disease", "source", "metric", "date_ref"),
        Index("ix_epi_trusted_q2", "geo_basis", "municipio_ibge", "date_ref"),
    )


class EpiTrustedCoverage(Base):
    __tablename__ = "epi_trusted_coverage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    disease: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    granularity: Mapped[str] = mapped_column(String(20), nullable=False)
    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False, default="residencia")

    uf: Mapped[str] = mapped_column(String(2), nullable=True)
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=True)

    date_min: Mapped[date] = mapped_column(Date, nullable=True)
    date_max: Mapped[date] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint("disease", "source", "metric", "granularity", "geo_basis", "uf", "municipio_ibge",
                         name="uq_epi_coverage_key"),
        Index("ix_epi_coverage_q1", "disease", "source", "metric"),
    )

class RawSinan(Base):
    """
    RAW SINAN (staging).
    disease: ex "malaria", "febre_amarela", "dengue", "hepatite", etc.
    geo_basis:
      - residencia: municipio de residencia
      - notificacao: municipio de notificacao
    """
    __tablename__ = "raw_sinan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_date: Mapped[date] = mapped_column(Date, nullable=False)
    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=False)
    disease: Mapped[str] = mapped_column(String(50), nullable=False)

    external_id: Mapped[str] = mapped_column(String(200), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint("geo_basis", "hash", name="uq_raw_sinan_hash"),
        Index("ix_raw_sinan_q1", "geo_basis", "municipio_ibge", "ref_date"),
        Index("ix_raw_sinan_q2", "disease", "ref_date"),
        Index("ix_raw_sinan_q3", "year", "ref_date"),
    )

class RawSim(Base):
    """
    RAW SIM (staging) - Mortalidade.
    disease aqui pode ser:
      - um "grupo" (ex: "all_cause")
      - ou um "icd10_group" (ex: "A00-B99", "J09-J18")
      - ou uma doença/condição derivada (ex: "covid19") se você mapear por CID.
    geo_basis:
      - residencia: municipio de residencia (padrão no SIM)
      - notificacao: pode ser usado se você quiser algum outro recorte, mas normalmente será residencia
    """
    __tablename__ = "raw_sim"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_date: Mapped[date] = mapped_column(Date, nullable=False)
    geo_basis: Mapped[str] = mapped_column(String(20), nullable=False)  # residencia|notificacao
    municipio_ibge: Mapped[str] = mapped_column(String(50), nullable=False)
    disease: Mapped[str] = mapped_column(String(50), nullable=False)

    icd10: Mapped[str] = mapped_column(String(10), nullable=True)  # opcional (se vier no raw)
    external_id: Mapped[str] = mapped_column(String(200), nullable=True)

    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        UniqueConstraint("geo_basis", "hash", name="uq_raw_sim_hash"),
        Index("ix_raw_sim_q1", "geo_basis", "municipio_ibge", "ref_date"),
        Index("ix_raw_sim_q2", "disease", "ref_date"),
        Index("ix_raw_sim_q3", "year", "ref_date"),
    )