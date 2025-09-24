# table_picker.py
import json
import os
import random
from collections import Counter, defaultdict
from app.sqlalchemy_parser import SqliteParser, Table
import configparser

config = configparser.ConfigParser()
config.read("config.ini")
DB_PATH = config.get("Settings", "database")
TARGET = int(config.get("Settings", "tables"))
SAVE_FILE = "tables.json"

def load_best():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tables": [], "penalty": float("inf")}

def save_best(data):
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def calc_penalty(counts):
    penalty = 0
    for c in counts.values():
        if c > TARGET:
            excess = c - TARGET
            penalty += excess ** 2
    return penalty

def describe_result(table_ids, player_tables):
    counts = Counter(len(tables) for tables in player_tables.values())
    sorted_counts = dict(sorted(counts.items()))  # сортируем по кол-ву столов
    penalty = calc_penalty({pid: len(tables) for pid, tables in player_tables.items()})
    return f"Tables: {len(table_ids)}, Penalty: {penalty}, Distribution: {sorted_counts}"

def pick_tables(parser: SqliteParser):
    all_tables = parser.session.query(Table).filter(Table.visible == False).all()
    all_players = {tp.player.p_id for table in all_tables for tp in table.players_seats}

    player_tables = defaultdict(set)
    chosen_tables = []
    remaining_tables = all_tables[:]
    random.shuffle(remaining_tables)

    # 1. Набираем минимум
    while True:
        need_more = [pid for pid in all_players if len(player_tables[pid]) < TARGET]
        if not need_more:
            break
        if not remaining_tables:
            break
        table = remaining_tables.pop()
        chosen_tables.append(table)
        for tp in table.players_seats:
            player_tables[tp.player.p_id].add(table.table_id)

    # 2+3. Улучшаем заменами/удалениями до тех пор, пока есть прогресс
    available_tables = [t for t in all_tables if t not in chosen_tables]
    improved = True
    best_penalty = calc_penalty({pid: len(tbls) for pid, tbls in player_tables.items()})

    while improved:
        improved = False
        for old_table in chosen_tables[:]:
            # Попробовать удалить стол
            tmp_player_tables = {pid: set(tbls) for pid, tbls in player_tables.items()}
            for tp in old_table.players_seats:
                tmp_player_tables[tp.player.p_id].discard(old_table.table_id)
            if all(len(tbls) >= TARGET for tbls in tmp_player_tables.values()):
                new_penalty = calc_penalty({pid: len(tbls) for pid, tbls in tmp_player_tables.items()})
                if new_penalty < best_penalty:
                    chosen_tables.remove(old_table)
                    player_tables = tmp_player_tables
                    available_tables.append(old_table)
                    best_penalty = new_penalty
                    improved = True
                    continue  # переходим к следующему столу

            # Попробовать заменить на другой
            for new_table in available_tables:
                tmp_player_tables = {pid: set(tbls) for pid, tbls in player_tables.items()}
                # убрать старый
                for tp in old_table.players_seats:
                    tmp_player_tables[tp.player.p_id].discard(old_table.table_id)
                # добавить новый
                for tp in new_table.players_seats:
                    tmp_player_tables[tp.player.p_id].add(new_table.table_id)
                if any(len(tbls) < TARGET for tbls in tmp_player_tables.values()):
                    continue
                new_penalty = calc_penalty({pid: len(tbls) for pid, tbls in tmp_player_tables.items()})
                if new_penalty < best_penalty:
                    chosen_tables.remove(old_table)
                    chosen_tables.append(new_table)
                    player_tables = tmp_player_tables
                    available_tables.remove(new_table)
                    available_tables.append(old_table)
                    best_penalty = new_penalty
                    improved = True
                    break  # выходим, так как заменили этот стол

    return [t.table_id for t in chosen_tables], best_penalty, player_tables

def main():
    parser = SqliteParser(DB_PATH)
    best = load_best()
    best_penalty = best["penalty"]

    print(f"Starting best penalty: {best_penalty}")

    try:
        while True:
            table_ids, penalty, player_tables = pick_tables(parser)
            if penalty < best_penalty:
                best_penalty = penalty
                best = {
                    "tables": table_ids,
                    "penalty": penalty,
                }
                save_best(best)
                print("New best!")
                print(describe_result(table_ids, player_tables))
    except KeyboardInterrupt:
        print("Stopped.")

if __name__ == "__main__":
    main()
