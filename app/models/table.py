from sqlalchemy.orm import relationship, backref, mapped_column, Mapped
from .base import Base


class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True)
    visible: Mapped[int] = mapped_column(insert_default=0)
    reveal_order: Mapped[int] = mapped_column(insert_default=0)
    time: Mapped[int] = mapped_column(insert_default=0)
    games: Mapped[list["Game"]] = relationship(back_populates="table", lazy="subquery")
    players_seats: Mapped[list["TablePlayer"]] = relationship(back_populates="table", lazy="subquery")

    @property
    def unfinished_games(self):
        return [g for g in self.games if g.started == 0]

    @property
    def players(self):
        self.players_seats.sort(key=lambda tp: tp.seat)
        return [tp.player for tp in self.players_seats]