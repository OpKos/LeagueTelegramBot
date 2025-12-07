import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Player(Base):
    __tablename__ = "players"
    p_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(sqlalchemy.BigInteger, unique=True)
    telegram_name: Mapped[str] = mapped_column(nullable=True)
    tenhou_name: Mapped[str] = mapped_column(unique=True)
    irl_name: Mapped[str] = mapped_column(nullable=True)
    full_ready: Mapped[int] = mapped_column(insert_default=0, server_default=sqlalchemy.text("0"))
    language: Mapped[str] = mapped_column(insert_default="ru", server_default="ru")
    games_seats: Mapped[list["GamePlayer"]] = relationship(back_populates="player", lazy="subquery")
    tables_seats: Mapped[list["TablePlayer"]] = relationship(back_populates="player", lazy="subquery")
    player_events: Mapped[list["EventPlayer"]] = relationship(back_populates="player", lazy="subquery")

    def visible_tables(self):
        return [tp.table for tp in self.tables_seats if tp.table.visible == 1 and tp.table.event.started == 1]

    def invisible_tables(self):
        return [tp.table for tp in self.tables_seats if tp.table.visible == 0 and tp.table.event.started == 1]

    def all_tables(self):
        return [tp.table for tp in self.tables_seats if tp.table.event.started == 1]

    def dirty_mention(self) -> str:
        return f"@{self.telegram_name}"

    def clean_mention(self) -> str:
        """
        Only works with ParseMode.HTML
        """
        return f"<a href=\'tg://user?id={self.telegram_id}\'>{self.irl_name}</a>"

    def __str__(self):
        return self.irl_name or self.telegram_name
