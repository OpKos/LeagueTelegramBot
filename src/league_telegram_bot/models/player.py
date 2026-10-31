from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event_player import EventPlayer
    from .game_player import GamePlayer


class Player(Base):
    __tablename__ = "players"
    p_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(sqlalchemy.BigInteger, unique=True)
    telegram_name: Mapped[str] = mapped_column(nullable=True)
    tenhou_name: Mapped[str] = mapped_column(unique=True)
    irl_name: Mapped[str] = mapped_column(nullable=True)
    language: Mapped[str] = mapped_column(insert_default="ru", server_default="ru")
    timezone: Mapped[str | None] = mapped_column(nullable=True)
    pantheon_id: Mapped[int] = mapped_column(nullable=True)
    is_admin: Mapped[int] = mapped_column(insert_default=0, server_default=sqlalchemy.text("0"))
    games_seats: Mapped[list[GamePlayer]] = relationship(back_populates="player", lazy="subquery")
    player_events: Mapped[list[EventPlayer]] = relationship(
        back_populates="player", lazy="subquery"
    )

    def all_tables(self):
        tables = []
        seen_table_ids = set()
        for game_player in self.games_seats:
            table = game_player.game.table
            if table.table_id not in seen_table_ids and table.event.started == 1:
                tables.append(table)
                seen_table_ids.add(table.table_id)
        return tables

    def dirty_mention(self) -> str:
        return f"@{self.telegram_name}"

    def clean_mention(self) -> str:
        """
        Only works with ParseMode.HTML
        """
        return f"<a href='tg://user?id={self.telegram_id}'>{self.irl_name}</a>"

    def __str__(self):
        return self.irl_name or self.telegram_name
