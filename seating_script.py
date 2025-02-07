# seating_script.py
import sqlite3
import random
from itertools import combinations

# Глобальные переменные
STAGE = 1  # Текущая стадия турнира
NUM_ITERATIONS = 100000  # Количество итераций для поиска лучшей рассадки

def get_players(db_path: str):
    """Возвращает список игроков, включённых в рассадку."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT p_id FROM players WHERE enable_seating = 1")
        players = [row[0] for row in cursor.fetchall()]
    return players

def get_previous_pairs(db_path: str):
    """
    Возвращает историю пар игроков, которые уже играли вместе.

    Args:
        db_path (str): Путь к базе данных.

    Returns:
        set: Множество кортежей (player1, player2), отсортированных по возрастанию.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT p1, p2, p3, p4 FROM games")
        games = cursor.fetchall()

    previous_pairs = set()
    for game in games:
        # Получаем все пары игроков в игре
        pairs = combinations(sorted(game), 2)
        for pair in pairs:
            previous_pairs.add(pair)
    return previous_pairs

def create_seating(players: list):
    """
    Создаёт рассадку игроков по столам.

    Args:
        players (list): Список ID игроков.

    Returns:
        list: Список столов, где каждый стол — это список из 4 игроков.
    """
    num_players = len(players)
    tables = []
    for i in range(num_players):
        table = [
            players[i],
            players[(i - 1) % num_players],
            players[(i - 3) % num_players],
            players[(i - 7) % num_players],
        ]
        tables.append(table)
    return tables

def calculate_repeats(tables: list, previous_pairs: set):
    """
    Вычисляет количество повторных встреч игроков в рассадке.

    Args:
        tables (list): Список столов.
        previous_pairs (set): Множество пар игроков, которые уже играли вместе.

    Returns:
        int: Количество повторных встреч.
    """
    repeat_count = 0
    for table in tables:
        # Все возможные пары игроков за столом
        table_pairs = combinations(sorted(table), 2)
        for pair in table_pairs:
            if pair in previous_pairs:
                repeat_count += 1
    return repeat_count

def generate_best_seating(db_path: str):
    """
    Генерирует лучшую рассадку, минимизируя повторные встречи.

    Args:
        db_path (str): Путь к базе данных.

    Returns:
        tuple: Лучшая рассадка (список столов) и количество повторных встреч.
    """
    players = get_players(db_path)
    previous_pairs = get_previous_pairs(db_path)

    best_seating = None
    min_repeats = float('inf')

    for iteration in range(NUM_ITERATIONS):
        random.shuffle(players)
        seating = create_seating(players)
        repeats = calculate_repeats(seating, previous_pairs)
        if repeats < min_repeats:
            min_repeats = repeats
            best_seating = seating

        # Выводим прогресс каждые 10000 итераций
        if (iteration + 1) % 10000 == 0:
            print(f"Осталось итераций: {NUM_ITERATIONS - iteration - 1}")

    return best_seating, min_repeats

def create_games(db_path: str, tables: list):
    """
    Создаёт игры для каждого стола.

    Args:
        db_path (str): Путь к базе данных.
        tables (list): Список столов.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Получаем максимальный номер стола
        cursor.execute("SELECT MAX(table_id) FROM games")
        max_table_id = cursor.fetchone()[0] or 0

        for table in tables:
            max_table_id += 1
            # Создаём 3 игры для каждого стола: ABCD, BDAC, CADB
            games = [
                (max_table_id, table[0], table[1], table[2], table[3]),  # ABCD
                (max_table_id, table[1], table[3], table[0], table[2]),  # BDAC
                (max_table_id, table[2], table[0], table[3], table[1]),  # CADB
            ]
            for game in games:
                cursor.execute("""
                    INSERT INTO games (table_id, p1, p2, p3, p4, started, stage)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (*game, STAGE))
        conn.commit()

def main():
    db_path = "season1.db"

    # Генерируем лучшую рассадку
    best_seating, repeats = generate_best_seating(db_path)
    print("Лучшая рассадка:", best_seating)
    print("Количество повторных встреч:", repeats)

    # Создаём игры для лучшей рассадки
    create_games(db_path, best_seating)
    print("Игры успешно созданы.")

if __name__ == "__main__":
    main()