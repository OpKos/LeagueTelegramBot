from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import logging, os, shutil
from datetime import datetime

import settings
import models

logger = logging.getLogger(__name__)

class SqliteParser:
    def __init__(self, db_path: str):
        self.engine = create_engine(f'postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}@db/{settings.DB_NAME}')
        logger.log(f'postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}@db/{settings.DB_NAME}')
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
        player = models.Player(
            telegram_id=telegram_id,
            telegram_name=telegram_name,
            tenhou_name=tenhou_id,
            enable_seating=0
        )
        self.session.add(player)
        self.backup_database()
        self.session.commit()

    def fill_player_data(self, p_id: int, irl_name: str, include_status: int):
        player = self.session.get(models.Player, p_id)
        assert player
        player.irl_name = irl_name
        player.enable_seating = bool(include_status)
        self.backup_database()
        self.session.commit()
                
    def update_tenhou_nick(self, p_id: int, tenhou_name: str):
        player = self.session.get(models.Player, p_id)
        assert player
        player.tenhou_name = tenhou_name
        self.backup_database()
        self.session.commit()
            
    def get_player(self, p_id=None, telegram_id=None, telegram_name=None, tenhou_name=None):
        query = self.session.query(models.Player)
        if p_id:
            query = query.filter(models.Player.p_id==p_id)
        if telegram_id:
            query = query.filter(models.Player.telegram_id==telegram_id)
        if telegram_name:
            query = query.filter(models.Player.telegram_name==telegram_name)
        if tenhou_name:
            query = query.filter(models.Player.tenhou_name==tenhou_name)
        return query.first()

    def get_all_games(self):
        return self.session.query(models.Game).all()

    def set_game_status(self, game_id: int, status: int):
        game = self.session.get(models.Game, game_id)
        assert game
        game.started = status
        self.backup_database()
        self.session.commit()
    
    def get_games_status(self):
        started = self.session.query(models.Game).filter(models.Game.started != 0).count()
        total = self.session.query(models.Game).count()
        return started, total

    def get_game(self, game_id: int):
        return self.session.get(models.Game, game_id)

    def get_table(self, table_id: int):
        return self.session.get(models.Table, table_id)
    
    def get_visible_table(self, table_id: int):
        table = self.session.get(models.Table, table_id)
        if table and table.visible:
            return table
        return None
    
    def set_table_time(self, table_id: int, timestamp: int):
        table = self.session.get(models.Table, table_id)
        if table is None:
            return False
        table.time = timestamp
        self.backup_database()
        self.session.commit()
        return True

    def get_all_tables(self):
        return self.session.query(models.Table).all()
    
    def get_visible_tables(self):
        return self.session.query(models.Table).filter(models.Table.visible > 0).all()
        
    def get_unfinished_visible_tables(self):
        tables = self.session.query(models.Table).all()
        return [table for table in tables if table.unfinished_games and table.visible]

    def set_target_tables(self, p_id: int, goal: int = 1):
        """Помечает игрока как готового к следующему столу"""
        player = self.session.get(models.Player, p_id)
        if player:
            goal = min(goal, len(player.invisible_tables()))
            player.target_tables =len(player.visible_tables())+goal
            self.backup_database()
            self.session.commit()
            return True
        return False

    def check_table_reveal_ready(self, table_id: int):
        """Проверяет, готов ли стол к раскрытию"""
        table = self.session.get(models.Table, table_id)
        
        if not table or table.visible:
            return False
            
        return all(p.player.next_table_ready for p in table.players_seats)

    def reveal_table(self, table_id: int):
        """Раскрывает стол и снимает пометки о готовности"""
        table = self.session.get(models.Table, table_id)
        
        if not table or table.visible:
            return False

        # Получаем максимальный текущий порядок раскрытия
        max_order = self.session.query(func.max(models.Table.reveal_order)).scalar() or 0
            
        # Раскрываем стол с новым порядком
        table.visible = True
        table.reveal_order = max_order + 1
        self.backup_database()
        self.session.commit()
        return True
    
    def get_table_by_reveal_order(self, reveal_order: int):
        query = self.session.query(models.Table).filter(models.Table.reveal_order==reveal_order)
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
