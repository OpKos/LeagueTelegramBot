from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy import ForeignKey
from .base import Base


class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=True)
    visible: Mapped[int] = mapped_column(insert_default=0)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    time: Mapped[int] = mapped_column(insert_default=0)
    event: Mapped["Event"] = relationship(back_populates="tables", lazy="subquery")
    games: Mapped[list["Game"]] = relationship(back_populates="table", lazy="subquery")
    players_seats: Mapped[list["TablePlayer"]] = relationship(back_populates="table", lazy="subquery")

    def unfinished_games(self):
        return [g for g in self.games if g.started == 0]

    def players(self):
        self.players_seats.sort(key=lambda tp: tp.seat)
        return [tp.player for tp in self.players_seats]
