import json
from sqlite_parser import SqliteParser

with open("table_data.json", "r")as f:
    data = json.load(f)
    
db = SqliteParser("season1.db")
    
for player in data:
    name, nick, include = player
    p_id = db.get_player_id_by_tenhou_id(nick)
    if p_id:
        db.fill_player_data(p_id, name, include)
        print(f"player updated in database: {player}")
    else:
        print(f"player not found in database: {player}")
    