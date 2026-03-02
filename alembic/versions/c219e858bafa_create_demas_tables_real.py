from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c219e858bafa"
down_revision: Union[str, Sequence[str], None] = "4e065cbcb033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # demas_raw
    op.create_table(
        "demas_raw",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint_name", sa.String(length=120), nullable=False),
        sa.Column("request_year", sa.Integer(), nullable=True),
        sa.Column("request_limit", sa.Integer(), nullable=True),
        sa.Column("request_offset", sa.Integer(), nullable=True),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("endpoint_name", "record_hash", name="uq_demas_raw_endpoint_hash"),
    )
    op.create_index("ix_demas_raw_endpoint_name", "demas_raw", ["endpoint_name"], unique=False)
    op.create_index("ix_demas_raw_collected_at", "demas_raw", ["collected_at"], unique=False)

    # demas_municipio_dim
    op.create_table(
        "demas_municipio_dim",
        sa.Column("municipio_ibge", sa.String(length=16), primary_key=True),
        sa.Column("municipio_nome", sa.Text(), nullable=True),
        sa.Column("uf", sa.String(length=8), nullable=True),
        sa.Column("regiao_saude_codigo", sa.String(length=32), nullable=True),
        sa.Column("regiao_saude_nome", sa.Text(), nullable=True),
        sa.Column("macrorregiao_codigo", sa.String(length=32), nullable=True),
        sa.Column("macrorregiao_nome", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # demas_events  (atenção: seu model é __tablename__ = "demas_events")
    op.create_table(
        "demas_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dataset", sa.String(length=120), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("epiweek", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(length=8), nullable=True),
        sa.Column("municipio_ibge", sa.String(length=16), nullable=True),
        sa.Column("municipio_nome", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset", "fingerprint", name="uq_demas_events_dataset_fp"),
    )
    op.create_index("ix_demas_events_dataset", "demas_events", ["dataset"], unique=False)
    op.create_index("ix_demas_events_event_date", "demas_events", ["event_date"], unique=False)
    op.create_index("ix_demas_events_municipio_ibge", "demas_events", ["municipio_ibge"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_demas_events_municipio_ibge", table_name="demas_events")
    op.drop_index("ix_demas_events_event_date", table_name="demas_events")
    op.drop_index("ix_demas_events_dataset", table_name="demas_events")
    op.drop_table("demas_events")

    op.drop_table("demas_municipio_dim")

    op.drop_index("ix_demas_raw_collected_at", table_name="demas_raw")
    op.drop_index("ix_demas_raw_endpoint_name", table_name="demas_raw")
    op.drop_table("demas_raw")