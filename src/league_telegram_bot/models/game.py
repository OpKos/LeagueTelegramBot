from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base
from .table import Table


class Game(Base):
    __tablename__ = "games"
    game_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"))
    started: Mapped[int] = mapped_column(insert_default=0)
    table: Mapped["Table"] = relationship(back_populates="games", lazy="subquery")
    players_seats: Mapped[list["GamePlayer"]] = relationship(back_populates="game", lazy="subquery")

    def players(self):
        self.players_seats.sort(key=lambda p: p.seat)
        return [p.player for p in self.players_seats]
