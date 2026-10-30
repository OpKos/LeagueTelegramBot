"""Add ready player timestamp

Revision ID: 3ad2a61e9c47
Revises: f6ccbb0b370a
Create Date: 2026-10-31 01:17:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3ad2a61e9c47"
down_revision: str | Sequence[str] | None = "f6ccbb0b370a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ready_players",
        sa.Column("timestamp", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ready_players", "timestamp")
