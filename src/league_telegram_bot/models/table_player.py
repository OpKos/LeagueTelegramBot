from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .player import Player
    from .table import Table


class TablePlayer(Base):
    __tablename__ = "table_player_a"
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"))
    seat: Mapped[int] = mapped_column(primary_key=True)
    table: Mapped[Table] = relationship(back_populates="players_seats", lazy="subquery")
    player: Mapped[Player] = relationship(back_populates="tables_seats", lazy="subquery")
