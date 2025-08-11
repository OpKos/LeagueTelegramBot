from sqlalchemy import create_engine, select, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship, sessionmaker
import logging, os, shutil
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class Base(DeclarativeBase): pass

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
        return [tp.table for tp in self.tables_seats if getattr(tp.table, "visible", 0)]
    
    @property
    def invisible_tables(self): 
        return [tp.table for tp in self.tables_seats if not getattr(tp.table, "visible", 0)]
    
    @property
    def all_tables(self): 
        return [tp.table for tp in self.tables_seats]
    
    def dirty_mention(self) -> str:
        return f"@{self.telegram_name}"
    
    def clean_mention(self) -> str:
        """
        Only works with ParseMode.HTML
        """
        return f"<a href=\'tg://user?id={self.telegram_id}\'>{self.irl_name}</a>"
    
    def __str__(self): 
        return self.irl_name or self.telegram_name

class Game(Base):
    __tablename__ = "games"
    game_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.table_id"))
    started: Mapped[int] = mapped_column(insert_default=0)
    table: Mapped["Table"] = relationship(back_populates="games", lazy="subquery")
    players_seats: Mapped[list["GamePlayer"]] = relationship(back_populates="game", lazy="subquery")
    @property
    def players(self): return [p.player for p in self.players_seats]

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
    def unfinished_games(self): return [g for g in self.games if g.started == 0]
    @property
    def players(self): return [tp.player for tp in self.players_seats]

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
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        
    def __del__(self):
        """Clean up the session when the parser is destroyed"""
        if hasattr(self, 'session'):
            self.session.close()
    
    def reload_session(self):
        """Close and reopen a fresh session"""
        self.session.close()
        self.session = self.Session()
        return True
    
    def register_player(self, telegram_id: int, telegram_name: str|None, tenhou_id: str):
        player = Player(
            telegram_id=telegram_id,
            telegram_name=telegram_name,
            tenhou_name=tenhou_id,
            enable_seating=False
        )
        self.session.add(player)
        self.session.commit()

    def fill_player_data(self, p_id: int, irl_name: str, include_status: int):
        player = self.session.get(Player, p_id)
        assert player
        player.irl_name = irl_name
        player.enable_seating = bool(include_status)
        self.session.commit()
                
    def update_tenhou_nick(self, p_id: int, tenhou_name: str):
        player = self.session.get(Player, p_id)
        assert player
        player.tenhou_name = tenhou_name
        self.session.commit()
            
    def get_player(self, p_id=None, telegram_id=None, telegram_name=None, tenhou_name=None):
        query = self.session.query(Player)
        if p_id:
            query = query.filter(Player.p_id==p_id)
        if telegram_id:
            query = query.filter(Player.telegram_id==telegram_id)
        if telegram_name:
            query = query.filter(Player.telegram_name==telegram_name)
        if tenhou_name:
            query = query.filter(Player.tenhou_name==tenhou_name)
        return query.first()

    def get_all_games(self):
        return self.session.query(Game).all()

    def set_game_status(self, game_id: int, status: int):
        game = self.session.get(Game, game_id)
        assert game
        game.started = status
        self.session.commit()
    
    def get_games_status(self):
        started = self.session.query(Game).filter(Game.started != 0).count()
        total = self.session.query(Game).count()
        return started, total

    def get_game(self, game_id: int):
        return self.session.get(Game, game_id)

    def get_table(self, table_id: int):
        return self.session.get(Table, table_id)
    
    def get_visible_table(self, table_id: int):
        table = self.session.get(Table, table_id)
        if table and table.visible:
            return table
        return None
    
    def set_table_time(self, table_id: int, timestamp: int):
        table = self.session.get(Table, table_id)
        if table is None:
            return False
        table.time = timestamp
        self.session.commit()
        return True

    def get_all_tables(self):
        return self.session.query(Table).all()
    
    def get_visible_tables(self):
        return self.session.query(Table).filter(Table.visible > 0).all()
        
    def get_unfinished_visible_tables(self):
        tables = self.session.query(Table).all()
        return [table for table in tables if table.unfinished_games and table.visible]

    def set_next_table_ready(self, p_id: int, ready: bool = True):
        """Помечает игрока как готового к следующему столу"""
        player = self.session.get(Player, p_id)
        if player:
            player.next_table_ready = ready
            self.session.commit()
            return True
        return False

    def check_table_reveal_ready(self, table_id: int):
        """Проверяет, готов ли стол к раскрытию"""
        table = self.session.get(Table, table_id)
        
        if not table or table.visible:
            return False
            
        return all(p.player.next_table_ready for p in table.players_seats)

    def reveal_table(self, table_id: int):
        """Раскрывает стол и снимает пометки о готовности"""
        table = self.session.get(Table, table_id)
        
        if not table or table.visible:
            return False

        # Получаем максимальный текущий порядок раскрытия
        max_order = self.session.query(func.max(Table.reveal_order)).scalar() or 0
        
        # Снимаем пометки о готовности
        for tp in table.players_seats:
            tp.player.next_table_ready = False
            
        # Раскрываем стол с новым порядком
        table.visible = True
        table.reveal_order = max_order + 1
        self.session.commit()
        return True
    
    def get_table_by_reveal_order(self, reveal_order: int):
        query = self.session.query(Table).filter(Table.reveal_order==reveal_order)
        return query.first()

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
