from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ReadyPlayer(Base):
    __tablename__ = "ready_players"
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"), primary_key=True)
    timestamp: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
