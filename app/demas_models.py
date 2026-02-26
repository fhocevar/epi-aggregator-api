from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DemasRaw(Base):
    __tablename__ = "demas_raw"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint_name: Mapped[str] = mapped_column(String(120), nullable=False)
    request_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("endpoint_name", "record_hash", name="uq_demas_raw_endpoint_hash"),)


class DemasMunicipioDim(Base):
    __tablename__ = "demas_municipio_dim"

    municipio_ibge: Mapped[str] = mapped_column(String(16), primary_key=True)
    municipio_nome: Mapped[str | None] = mapped_column(Text, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(8), nullable=True)

    regiao_saude_codigo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    regiao_saude_nome: Mapped[str | None] = mapped_column(Text, nullable=True)

    macrorregiao_codigo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    macrorregiao_nome: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class DemasEvent(Base):
    __tablename__ = "demas_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(120), nullable=False)

    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    epiweek: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uf: Mapped[str | None] = mapped_column(String(8), nullable=True)
    municipio_ibge: Mapped[str | None] = mapped_column(String(16), nullable=True)
    municipio_nome: Mapped[str | None] = mapped_column(Text, nullable=True)

    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    normalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("dataset", "fingerprint", name="uq_demas_events_dataset_fp"),)