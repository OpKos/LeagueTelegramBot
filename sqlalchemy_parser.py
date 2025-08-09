import logging
import os
import shutil
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Integer, String, Boolean, ForeignKey, select, and_, or_, func, BigInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

class Player(Base):
    __tablename__ = "players"
    p_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(unique=True)
    telegram_name: Mapped[str] = mapped_column(nullable=True)
    tenhou_name: Mapped[str] = mapped_column(unique=True)
    irl_name: Mapped[str] = mapped_column(nullable=True)
    enable_seating: Mapped[int] = mapped_column(insert_default=0)
    next_table_ready: Mapped[int] = mapped_column(insert_default=0)
    games_seats: Mapped[list["GamePlayer"]] = relationship(back_populates="player", lazy="subquery")
    tables_seats: Mapped[list["TablePlayer"]] = relationship(back_populates="player", lazy="subquery")
    
    @property
    def visible_tables(self):
        return [i.table for i in self.tables_seats if i.table.visible]
    
    @property
    def invisible_tables(self):
        return [i.table for i in self.tables_seats if not i.table.visible]
    
    @property
    def all_tables(self):
        return [i.table for i in self.tables_seats]
    
    def __str__(self):
        return self.irl_name
    
class Game(Base):
    __tablename__ = "games"
    game_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"))
    started: Mapped[int] = mapped_column(insert_default=0)
    table: Mapped["Table"] = relationship(back_populates="games", lazy="subquery")
    players_seats: Mapped[list["GamePlayer"]] = relationship(back_populates="game", lazy="subquery")
    
    @property
    def players(self):
        return [p.player for p in self.players_seats]
    
class GamePlayer(Base):
    __tablename__ = "game_player_a"
    game_id: Mapped[int] = mapped_column(ForeignKey("games.game_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"))
    seat: Mapped[int] = mapped_column(primary_key=True)
    game: Mapped[Game] = relationship(back_populates="players_seats", lazy="subquery")
    player: Mapped[Player] = relationship(back_populates="games_seats", lazy="subquery")
        
class Table(Base):
    __tablename__ = "tables"
    table_id: Mapped[int] = mapped_column(primary_key=True)
    visible: Mapped[int] = mapped_column(insert_default=0)
    reveal_order: Mapped[int] = mapped_column(insert_default=0)
    time: Mapped[int] = mapped_column(insert_default=0)
    games: Mapped[list[Game]] = relationship(back_populates="table", lazy="subquery")
    players_seats: Mapped[list["TablePlayer"]] = relationship(back_populates="table", lazy="subquery")
    
    @property
    def unfinished_games(self):
        return [i for i in self.games if i.started == 0]
    
    @property
    def players(self):
        return [p.player for p in (self.players_seats)]
    
class TablePlayer(Base):
    __tablename__ = "table_player_a"
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"), primary_key=True)
    p_id: Mapped[int] = mapped_column(ForeignKey("players.p_id"))
    seat: Mapped[int] = mapped_column(primary_key=True)
    table: Mapped[Table] = relationship(back_populates="players_seats", lazy="subquery")
    player: Mapped[Player] = relationship(back_populates="tables_seats", lazy="subquery")

class SqliteParser:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', future=True)
        Base.metadata.create_all(self.engine)

    def _session(self):
        return Session(self.engine)

    def register_player(self, telegram_id: int, telegram_name: str|None, tenhou_id: str):
        with self._session() as session:
            player = Player(
                telegram_id=telegram_id,
                telegram_name=telegram_name,
                tenhou_name=tenhou_id,
                enable_seating=False
            )
            session.add(player)
            session.commit()

    def fill_player_data(self, p_id: int, irl_name: str, include_status: int):
        with self._session() as session:
            player = session.get(Player, p_id)
            assert player
            player.irl_name = irl_name
            player.enable_seating = bool(include_status)
            session.commit()
                
    def update_tenhou_nick(self, p_id: int, tenhou_name: str):
        with self._session() as session:
            player = session.get(Player, p_id)
            assert player
            player.tenhou_name = tenhou_name
            session.commit
            
    #TODO: rewrite this
    def get_player(self, p_id=None, telegram_id=None, tenhou_name=None):
        with self._session() as session:
            player = session.query(Player).filter((Player.p_id==p_id) | (Player.telegram_id==telegram_id) | (Player.tenhou_name==tenhou_name)).first()
            return player

    def get_all_games(self):
        with self._session() as session:
            return session.query(Game).all()

    def set_game_status(self, game_id: int, status: int):
        with self._session() as session:
            game = session.get(Game, game_id)
            assert game
            game.started = status
            session.commit()
    
    def get_games_status(self):
        with self._session() as session:
            started = session.query(Game).filter(Game.started != 0).count()
            total = session.query(Game).count()
            return started, total

    def get_game(self, game_id: int):
        with self._session() as session:
            return session.get(Game, game_id)

    def get_table(self, table_id: int):
        with self._session() as session:
            return session.get(Table, table_id)
    
    def get_visible_table(self, table_id: int):
        with self._session() as session:
            table = session.get(Table, table_id)
            if table and table.visible:
                return table
            else:
                return None
    
    def set_table_time(self, table_id: int, timestamp: int):
        with self._session() as session:
            table = session.get(Table, table_id)
            if table is None:
                return False
            table.time = timestamp
            session.commit()
            return True

    def get_all_tables(self):
        with self._session() as session:
            return session.query(Table).all()
    
    def get_visible_tables(self):
        with self._session() as session:
            return session.query(Table).filter(Table.visible > 0).all()
        
    def get_unfinished_visible_tables(self):
        with self._session() as session:
            tables = session.query(Table).all()
            return [table for table in tables if table.unfinished_games and table.visible]

    def backup_database(self):
        try:
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"{os.path.basename(self.db_path)}_{current_time}.db")
            shutil.copyfile(self.db_path, backup_path)
            logger.info(f"Backup created at {backup_path}")
        except Exception as e:
            logger.error("Error in backup_database: %s", str(e))
