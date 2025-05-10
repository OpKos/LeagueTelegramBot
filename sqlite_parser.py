import logging
import sqlite3
import shutil
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class SqliteParser:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def register_player(self, telegram_id: int, telegram_name: str, tenhou_id: str):
        """
        Регистрирует нового игрока в системе.

        Args:
            telegram_id (int): Telegram ID игрока.
            telegram_name (str): Имя игрока в Telegram.
            tenhou_id (str): Tenhou ID игрока.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO players (telegram_id, telegram_name, tenhou_name, enable_seating)
                VALUES (?, ?, ?, 0)
            """, (telegram_id, telegram_name, tenhou_id))
            conn.commit()
    
    def get_games(self, stage: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT table_id, p1, p2, p3, p4 FROM games WHERE stage = ?", (stage, ))
            games = [{'table': row[0], 'players': [int(i) for i in row[1:]]} for row in cursor.fetchall()]
        return games
    
    def fill_player_data(self, p_id: int, irl_name:str, include_status: int):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE players SET irl_name = ?, enable_seating = ? WHERE p_id = ?", (irl_name, include_status, p_id))
        except sqlite3.Error as e:
            logger.error("Error in get_player_id_by_tg_id: %s", str(e))
    
    def get_player(self, telegram_id=None, tenhou_name=None, telegram_name=None, p_id=None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p_id, telegram_id, telegram_name, tenhou_name, irl_name FROM players WHERE \
                        telegram_id = ? OR tenhou_name = ? OR telegram_name = ? OR p_id = ?", (telegram_id,tenhou_name,telegram_name,p_id))
                player = cursor.fetchone()
                player = {
                    "p_id": player[0],
                    "telegram_id": player[1],
                    "telegram_name": player[2],
                    "tenhou_name": player[3],
                    "irl_name": player[4]
                }
                return player
        except sqlite3.Error as e:
            logger.error("Error in get_player: %s", str(e))
            return None
    
    def get_games_status(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM games WHERE started = 1")
                started = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM games")
                total = cursor.fetchone()[0]
                return started, total
        except sqlite3.Error as e:
            logger.error("Error in get_games_status: %s", str(e))
            return None
    
    def get_player_id_by_tg_id(self, telegram_id: int):
        """Возвращает p_id игрока по его telegram_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p_id FROM players WHERE telegram_id = ?", (telegram_id,))
                player = cursor.fetchone()
            return player[0] if player else None
        except sqlite3.Error as e:
            logger.error("Error in get_player_id_by_tg_id: %s", str(e))
            return None

    def get_player_id_by_tenhou_id(self, tenhou_id: str):
        """Возвращает p_id игрока по его telegram_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p_id FROM players WHERE tenhou_name = ?", (tenhou_id,))
                player = cursor.fetchone()
            return player[0] if player else None
        except sqlite3.Error as e:
            logger.error("Error in get_player_id_by_tenhou_id: %s", str(e))
            return None
        
    def get_player_id_by_telegram_name(self, telegram_name: str):
        """
        Возвращает p_id игрока по его telegram_name.
        
        Args:
            telegram_name (str): Имя игрока в Telegram (без @)
        
        Returns:
            int: ID игрока или None, если не найден
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT p_id FROM players WHERE telegram_name = ?", (telegram_name,))
            player = cursor.fetchone()
        return player[0] if player else None

    def get_all_player_games(self, p_id: int):
        """
        Получает все игры игрока (всех стадий) с полной информацией.
        
        Args:
            p_id (int): ID игрока
        
        Returns:
            list: Список кортежей (game_id, table_id, p1, p2, p3, p4, started, stage)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT game_id, table_id, p1, p2, p3, p4, started, stage 
                FROM games 
                WHERE p1 = ? OR p2 = ? OR p3 = ? OR p4 = ?
                ORDER BY stage, table_id
            """, (p_id, p_id, p_id, p_id))
            return cursor.fetchall()
    
    def get_player_games(self, p_id: int):
        """Возвращает список игр, в которых участвует игрок."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT game_id, started FROM games
                    WHERE p1 = ? OR p2 = ? OR p3 = ? OR p4 = ?
                """, (p_id, p_id, p_id, p_id))
                games = cursor.fetchall()
            return games
        except sqlite3.Error as e:
            logger.error("Error in get_player_games: %s", str(e))
            return []

    def get_telegram_name_by_pid(self, p_id: int):
        """Возвращает telegram_name игрока по его p_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT telegram_name FROM players WHERE p_id = ?", (p_id,))
                player = cursor.fetchone()
            return player[0] if player else None
        except sqlite3.Error as e:
            logger.error("Error in get_telegram_name_by_pid: %s", str(e))
            return None

    def get_player_games_grouped_by_table(self, p_id: int, stage: str):
        """
        Возвращает информацию об играх, сгруппированных по столам, для указанной стадии турнира.

        Args:
            p_id (int): ID игрока.
            stage (str): Стадия турнира.

        Returns:
            dict: Информация о столах и играх.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_id, p1, p2, p3, p4, started
                FROM games
                WHERE (p1 = ? OR p2 = ? OR p3 = ? OR p4 = ?) AND stage = ?
                ORDER BY table_id
            """, (p_id, p_id, p_id, p_id, stage))
            games = cursor.fetchall()

            tables = {}
            for game in games:
                table_id, p1, p2, p3, p4, started = game
                if table_id not in tables:
                    tables[table_id] = {
                        'players': [
                            (self.get_telegram_name_by_pid(p1), self.get_irl_name_by_pid(p1)),
                            (self.get_telegram_name_by_pid(p2), self.get_irl_name_by_pid(p2)),
                            (self.get_telegram_name_by_pid(p3), self.get_irl_name_by_pid(p3)),
                            (self.get_telegram_name_by_pid(p4), self.get_irl_name_by_pid(p4))
                        ],
                        'total_games': 0,
                        'started_games': 0
                    }
                tables[table_id]['total_games'] += 1
                if started:
                    tables[table_id]['started_games'] += 1

            return tables

    def get_tenhou_name_by_pid(self, p_id: int):
        """Возвращает tenhou_name игрока по его p_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT tenhou_name FROM players WHERE p_id = ?", (p_id,))
                player = cursor.fetchone()
            return player[0] if player else None
        except sqlite3.Error as e:
            logger.error("Error in get_tenhou_name_by_pid: %s", str(e))
            return None

    def get_irl_name_by_pid(self, p_id: int):
        """Возвращает настоящее имя игрока по его p_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT irl_name FROM players WHERE p_id = ?", (p_id,))
                player = cursor.fetchone()
            return player[0] if player else None
        except sqlite3.Error as e:
            logger.error("Error in get_irl_name_by_pid: %s", str(e))
            return None

    def get_games_by_table_id(self, table_id: int):
        """Возвращает список игр за указанным столом."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p1, p2, p3, p4, started, game_id FROM games WHERE table_id = ?", (table_id,))
                games = cursor.fetchall()
            return games
        except sqlite3.Error as e:
            logger.error("Error in get_games_by_table_id: %s", str(e))
            return []
        
    def get_game(self, game_id: int):
        """Возвращает игру по id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p1, p2, p3, p4, started, game_id, table_id FROM games WHERE game_id = ?", (game_id,))
                game = cursor.fetchone()
            return game
        except sqlite3.Error as e:
            logger.error("Error in get_game: %s", str(e))
            return []

    def get_unstarted_games_by_table_id(self, table_id: int):
        """Возвращает список неначатых игр за указанным столом."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT p1, p2, p3, p4, game_id FROM games WHERE table_id = ? AND started = 0", (table_id,))
                games = cursor.fetchall()
            return games
        except sqlite3.Error as e:
            logger.error("Error in get_unstarted_games_by_table_id: %s", str(e))
            return []

    def update_game_status(self, game_id: int, status: int) -> bool:
        """Обновляет статус игры по указанному game_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE games SET started = ? WHERE game_id = ?", (status, game_id))
                conn.commit()
            self.backup_database()
            return True
        except sqlite3.Error as e:
            logger.error("Error in update_game_status: %s", str(e))
            return False

    def backup_database(self):
        """Создает резервную копию базы данных с текущим временем в имени файла."""
        try:
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"{os.path.basename(self.db_path)}_{current_time}.backup")
            shutil.copyfile(self.db_path, backup_path)
            logger.info(f"Backup created at {backup_path}")
        except Exception as e:
            logger.error("Error in backup_database: %s", str(e))
            
    def get_game_message(self, game_id:int) -> int:
        """Возвращает id сообщения связанного с запуском игры"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                message = cursor.execute("SELECT message_id FROM games WHERE game_id = ?", (game_id,)).fetchall()
                if message:
                    return message[0][0]
        except sqlite3.Error as e:
            logger.error("Error in get_game_message: %s", str(e))
            return 0
    
    def set_game_message(self, game_id:int, message_id:int):
        """Выставляет id сообщения связанного с запуском игры"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE games SET message_id = ? WHERE game_id = ?", (message_id, game_id))
                return True
        except sqlite3.Error as e:
            logger.error("Error in get_game_message: %s", str(e))
            return False