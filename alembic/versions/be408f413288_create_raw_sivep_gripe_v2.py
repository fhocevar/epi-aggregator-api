"""create raw_sivep_gripe_v2

Revision ID: be408f413288
Revises: 0cafb56065db
Create Date: 2026-02-24 11:29:48.475036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be408f413288'
down_revision: Union[str, Sequence[str], None] = '0cafb56065db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
