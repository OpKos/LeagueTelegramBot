"""remove table visibility and reveal state

Revision ID: a18d60c6b052
Revises: 7900b798994a
Create Date: 2026-10-28

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a18d60c6b052"
down_revision: str | Sequence[str] | None = "7900b798994a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tables", "visible")
    op.drop_column("tables", "reveal_cached")
    op.drop_column("event_player_a", "table_minimum")
    op.drop_column("event_player_a", "reveal_enabled")
    op.drop_column("events", "global_minimum")
    op.drop_column("events", "global_maximum")
    op.drop_column("players", "full_ready")


def downgrade() -> None:
    op.add_column(
        "players",
        sa.Column("full_ready", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("events", sa.Column("global_maximum", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("global_minimum", sa.Integer(), nullable=True))
    op.add_column(
        "event_player_a",
        sa.Column("reveal_enabled", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "event_player_a",
        sa.Column("table_minimum", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "tables",
        sa.Column("reveal_cached", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "tables", sa.Column("visible", sa.Integer(), server_default=sa.text("1"), nullable=False)
    )
    op.alter_column("tables", "visible", server_default=None)
