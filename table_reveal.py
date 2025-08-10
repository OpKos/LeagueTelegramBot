# table_reveal.py
import json
import os
from sqlalchemy_parser import SqliteParser
import configparser

config = configparser.ConfigParser()
config.read("config.ini")
DB_PATH = config.get("Settings", "database")
SAVE_FILE = "tables.json"

def main():
    if not os.path.exists(SAVE_FILE):
        print(f"Файл {SAVE_FILE} не найден")
        return

    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    table_ids = data.get("tables", [])
    if not table_ids:
        print("Нет столов для раскрытия")
        return

    parser = SqliteParser(DB_PATH)
    revealed = []
    skipped = []

    for table_id in table_ids:
        if parser.reveal_table(table_id):
            revealed.append(table_id)
        else:
            skipped.append(table_id)

    print(f"Раскрыто {len(revealed)} столов: {revealed}")
    if skipped:
        print(f"Пропущено {len(skipped)} столов (уже раскрыты или не найдены): {skipped}")

if __name__ == "__main__":
    main()
