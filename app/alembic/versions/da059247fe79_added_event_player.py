"""added event_player

Revision ID: da059247fe79
Revises: dffc783dec25
Create Date: 2025-12-02 15:27:18.517696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da059247fe79'
down_revision: Union[str, Sequence[str], None] = 'dffc783dec25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
