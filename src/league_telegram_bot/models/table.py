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
    from .table_time import TableTime


class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=True)
    visible: Mapped[int] = mapped_column(insert_default=1)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    chat_id: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger, insert_default=0, server_default=sqlalchemy.text("0")
    )
    reveal_cached: Mapped[int] = mapped_column(
        insert_default=0, server_default=sqlalchemy.text("0")
    )
    deadline_group: Mapped[int] = mapped_column(insert_default=0)
    event: Mapped[Event] = relationship(back_populates="tables", lazy="subquery")
    games: Mapped[list[Game]] = relationship(back_populates="table", lazy="subquery")
    players_seats: Mapped[list[TablePlayer]] = relationship(back_populates="table", lazy="subquery")
    table_times: Mapped[list[TableTime]] = relationship(back_populates="table", lazy="subquery")

    def unfinished_games(self):
        self.games.sort(key=lambda game: game.game_id)
        return [g for g in self.games if g.started == 0]

    def players(self):
        self.players_seats.sort(key=lambda tp: tp.seat)
        return [tp.player for tp in self.players_seats]

    def get_unfinished_players(self):
        games = self.unfinished_games()
        players = []
        for game in games:
            for player in game.players():
                if player not in players:
                    players.append(player)
        return players

    def get_event_players(self):
        res = []
        for player in self.players():
            for ep in player.player_events:
                if ep.event == self.event:
                    res.append(ep)
        return res

    def get_relevant_times(self, left_cutoff=None, right_cutoff=None) -> list[int]:
        relevant_times = [t_t.time for t_t in self.table_times]
        relevant_times.sort()
        if left_cutoff:
            relevant_times = [el for el in relevant_times if el >= left_cutoff]
        if right_cutoff:
            relevant_times = [el for el in relevant_times if el <= right_cutoff]
        return relevant_times
