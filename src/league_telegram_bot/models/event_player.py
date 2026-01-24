from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base

class EventPlayer(Base):
    __tablename__ = "event_player_a"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"), primary_key=True)
    table_minimum: Mapped[int] = mapped_column(insert_default=0, server_default=text("0"))
    reveal_enabled: Mapped[int] = mapped_column(insert_default=1, server_default=text("1"))
    event: Mapped["Event"] = relationship(back_populates="event_players", lazy="subquery")
    player: Mapped["Player"] = relationship(back_populates="player_events", lazy="subquery")

    def tables(self):
        return [table for table in self.event.tables if self.player in table.players()]

    def visible_tables(self):
        return [table for table in self.tables() if table.visible == 1]

    def invisible_tables(self):
        return [table for table in self.tables() if table.visible == 0]

    def new_table_ready(self):
        if self.reveal_enabled == 0:
            return 0
        if len(self.visible_tables()) < max(self.table_minimum, self.event.global_maximum):
            return 1
        return 0

    def new_table_priority(self):
        if self.new_table_ready() == 0:
            return 0
        if len(self.visible_tables()) < max(self.table_minimum, self.event.global_minimum):
            return 1
        return 0
