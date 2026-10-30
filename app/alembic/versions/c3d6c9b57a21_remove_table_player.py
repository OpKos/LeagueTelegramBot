"""remove redundant table-player association

Revision ID: c3d6c9b57a21
Revises: a18d60c6b052
Create Date: 2026-10-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d6c9b57a21"
down_revision: Union[str, Sequence[str], None] = "a18d60c6b052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("table_player_a")


def downgrade() -> None:
    op.create_table(
        "table_player_a",
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("p_id", sa.Integer(), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["p_id"], ["players.p_id"]),
        sa.ForeignKeyConstraint(["table_id"], ["tables.table_id"]),
        sa.PrimaryKeyConstraint("table_id", "seat"),
    )
