from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .event_player import EventPlayer
    from .table import Table


class Event(Base):
    __tablename__ = "events"
    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    link: Mapped[str] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(nullable=True)
    signup: Mapped[int] = mapped_column(nullable=True, insert_default=1)
    started: Mapped[int] = mapped_column(nullable=True, insert_default=0)
    global_minimum: Mapped[int] = mapped_column(nullable=True, insert_default=0)
    global_maximum: Mapped[int] = mapped_column(nullable=True, insert_default=0)
    pantheon_id: Mapped[int] = mapped_column(nullable=True)
    leaderboard_name: Mapped[str] = mapped_column(nullable=True)
    short_name: Mapped[str] = mapped_column(nullable=True)
    leaderboard_specs: Mapped[str] = mapped_column(nullable=True)
    event_players: Mapped[list[EventPlayer]] = relationship(back_populates="event", lazy="subquery")
    tables: Mapped[list[Table]] = relationship(back_populates="event", lazy="subquery")

    def players(self):
        return [ep.player for ep in self.event_players]

    def pantheon_link(self):
        return f"https://rating.riichimahjong.org/event/{self.pantheon_id}/order/rating"
