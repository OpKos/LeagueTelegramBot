from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base
from .game import Game
from .player import Player

class GamePlayer(Base):
    __tablename__ = "game_player_a"
    game_id: Mapped[int] = mapped_column(ForeignKey("games.game_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"))
    seat: Mapped[int] = mapped_column(primary_key=True)
    game: Mapped[Game] = relationship(back_populates="players_seats", lazy="subquery")
    player: Mapped[Player] = relationship(back_populates="games_seats", lazy="subquery")
