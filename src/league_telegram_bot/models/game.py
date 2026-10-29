from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .game_player import GamePlayer
    from .table import Table


class Game(Base):
    __tablename__ = "games"
    game_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"))
    started: Mapped[int] = mapped_column(insert_default=0)
    table: Mapped[Table] = relationship(back_populates="games", lazy="subquery")
    players_seats: Mapped[list[GamePlayer]] = relationship(back_populates="game", lazy="subquery")

    def players(self):
        self.players_seats.sort(key=lambda p: p.seat)
        return [p.player for p in self.players_seats]

    def are_players_ready(self, ready_player_ids: set[int]) -> bool:
        return all(player.p_id in ready_player_ids for player in self.players())

    def ready_string(self, ready_player_ids: set[int]) -> str:
        return "\n".join(
            ("✅ " if player.p_id in ready_player_ids else "❌ ") + player.irl_name
            for player in self.players()
        )

    def info_string(self, translate: Callable[..., str]) -> str:
        status = translate("game_started") if self.started else translate("game_not_started")
        players = "\n".join(player.irl_name for player in self.players())
        return translate("game_info", game_id=self.game_id, status=status, players=players)
