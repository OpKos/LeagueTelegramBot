"""Add optional player timezone

Revision ID: 2f6d8b1c4a90
Revises: 3ad2a61e9c47, c3d6c9b57a21
Create Date: 2026-10-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f6d8b1c4a90"
down_revision: str | Sequence[str] | None = ("3ad2a61e9c47", "c3d6c9b57a21")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("players", sa.Column("timezone", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "timezone")
