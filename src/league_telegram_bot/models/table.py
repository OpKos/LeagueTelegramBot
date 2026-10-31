from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..time_utils import (
    RUSSIAN_WEEKDAYS,
    TableTimeInputError,
    timestring_from_timestamp,
)
from .base import Base

if TYPE_CHECKING:
    from .event import Event
    from .game import Game
    from .player import Player
    from .table_time import TableTime


class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    chat_id: Mapped[int] = mapped_column(
        sqlalchemy.BigInteger, insert_default=0, server_default=sqlalchemy.text("0")
    )
    deadline_group: Mapped[int] = mapped_column(insert_default=0)
    event: Mapped[Event] = relationship(back_populates="tables", lazy="subquery")
    games: Mapped[list[Game]] = relationship(back_populates="table", lazy="subquery")
    table_times: Mapped[list[TableTime]] = relationship(back_populates="table", lazy="subquery")

    def unfinished_games(self):
        self.games.sort(key=lambda game: game.game_id)
        return [g for g in self.games if g.started == 0]

    def game_counts(self, player: Player | None = None) -> tuple[int, int]:
        games = [
            game
            for game in self.games
            if player is None or any(seat.p_id == player.p_id for seat in game.players_seats)
        ]
        return sum(game.started != 0 for game in games), len(games)

    def get_all_players(self):
        players = []
        seen_player_ids = set()
        for game in sorted(self.games, key=lambda game: game.game_id):
            for player in game.players():
                if player.p_id not in seen_player_ids:
                    players.append(player)
                    seen_player_ids.add(player.p_id)
        return players

    def get_timezones(self, default_timezone: str) -> list[str]:
        timezones = {player.timezone or default_timezone for player in self.get_all_players()}
        return sorted(timezones or {default_timezone})

    def get_unfinished_players(self):
        players = []
        seen_player_ids = set()
        for game in self.unfinished_games():
            for player in game.players():
                if player.p_id not in seen_player_ids:
                    players.append(player)
                    seen_player_ids.add(player.p_id)
        return players

    def remaining_unassigned_games(self) -> int:
        scheduled_games = sum(table_time.games for table_time in self.table_times)
        return len(self.unfinished_games()) - scheduled_games

    def validate_scheduled_game_count(self, games: int) -> None:
        if games > self.remaining_unassigned_games():
            raise TableTimeInputError("too_many_games", "Указано больше игр, чем осталось.")

    def players_string(self, mention: bool = False) -> str:
        return "\n".join(
            f"{player.irl_name} ({player.dirty_mention()})" if mention else player.irl_name
            for player in self.get_all_players()
        )

    def ready_string(self, ready_player_ids: set[int]) -> str:
        return "\n".join(
            ("✅ " if player.p_id in ready_player_ids else "❌ ") + player.irl_name
            for player in self.get_unfinished_players()
        )

    def get_relevant_times(self, left_cutoff=None, right_cutoff=None) -> list[int]:
        relevant_times = [t_t.time for t_t in self.table_times]
        relevant_times.sort()
        if left_cutoff:
            relevant_times = [el for el in relevant_times if el >= left_cutoff]
        if right_cutoff:
            relevant_times = [el for el in relevant_times if el <= right_cutoff]
        return relevant_times

    def get_relevant_times_string(
        self,
        timezone: str,
        left_cutoff: int | None = None,
        right_cutoff: int | None = None,
        weekday_names: tuple[str, ...] | None = None,
    ) -> str:
        weekday_names = weekday_names or RUSSIAN_WEEKDAYS
        return "\n".join(
            timestring_from_timestamp(
                time,
                timezone=timezone,
                weekday=True,
                day=True,
                weekday_names=weekday_names,
            )
            for time in self.get_relevant_times(left_cutoff=left_cutoff, right_cutoff=right_cutoff)
        )
