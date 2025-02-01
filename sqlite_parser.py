import logging
import sqlite3
import shutil
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class SqliteParser:
    def __init__(self, db_path: str):
        self.db_path = db_path

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

    def get_player_games_grouped_by_table(self, p_id: int, stage: int):
        """Возвращает информацию об играх, сгруппированных по столам, с именами игроков из Telegram и их настоящими именами."""
        try:
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
                        player_names = [
                            (self.get_telegram_name_by_pid(p1), self.get_irl_name_by_pid(p1)),
                            (self.get_telegram_name_by_pid(p2), self.get_irl_name_by_pid(p2)),
                            (self.get_telegram_name_by_pid(p3), self.get_irl_name_by_pid(p3)),
                            (self.get_telegram_name_by_pid(p4), self.get_irl_name_by_pid(p4)),
                        ]
                        tables[table_id] = {
                            'players': player_names,
                            'total_games': 0,
                            'started_games': 0
                        }
                    tables[table_id]['total_games'] += 1
                    if started:
                        tables[table_id]['started_games'] += 1

                return tables
        except sqlite3.Error as e:
            logger.error("Error in get_player_games_grouped_by_table: %s", str(e))
            return {}

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
