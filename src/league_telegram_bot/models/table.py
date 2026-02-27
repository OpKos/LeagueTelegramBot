from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event import Event
    from .game import Game
    from .table_player import TablePlayer


class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=True)
    visible: Mapped[int] = mapped_column(insert_default=0)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    time: Mapped[int] = mapped_column(insert_default=0)
    chat_id: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger, insert_default=0, server_default=sqlalchemy.text("0")
    )
    reveal_cached: Mapped[int] = mapped_column(
        insert_default=0, server_default=sqlalchemy.text("0")
    )
    event: Mapped[Event] = relationship(back_populates="tables", lazy="subquery")
    games: Mapped[list[Game]] = relationship(back_populates="table", lazy="subquery")
    players_seats: Mapped[list[TablePlayer]] = relationship(back_populates="table", lazy="subquery")

    def unfinished_games(self):
        return [g for g in self.games if g.started == 0]

    def players(self):
        self.players_seats.sort(key=lambda tp: tp.seat)
        return [tp.player for tp in self.players_seats]

    def get_event_players(self):
        res = []
        for player in self.players():
            for ep in player.player_events:
                if ep.event == self.event:
                    res.append(ep)
        return res

    def reveal_priority(self):
        if self.visible:
            return 0
        eps = self.get_event_players()
        for ep in eps:
            if ep.new_table_ready() == 0:
                return 0
        return sum(ep.new_table_priority() for ep in eps)
