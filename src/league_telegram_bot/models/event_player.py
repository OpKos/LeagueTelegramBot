from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event import Event
    from .player import Player


class EventPlayer(Base):
    __tablename__ = "event_player_a"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"), primary_key=True)
    leaderboard_group: Mapped[int] = mapped_column(insert_default=0, server_default=text("0"))
    event: Mapped[Event] = relationship(back_populates="event_players", lazy="subquery")
    player: Mapped[Player] = relationship(back_populates="player_events", lazy="subquery")
