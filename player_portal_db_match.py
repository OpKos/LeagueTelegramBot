import json
from sqlalchemy_parser import SqliteParser
import configparser


with open("table_data.json", "r")as f:
    data = json.load(f)
    
config = configparser.ConfigParser()
config.read("config.ini")
db_path = config.get("Settings", "database")
db = SqliteParser(db_path)
    
for player in data:
    name, nick, include = player
    player = db.get_player(tenhou_name=nick)
    if player:
        db.fill_player_data(player.p_id, name, include)
        print(f"player updated in database: {player}")
    else:
        print(f"player not found in database: {name}")
    