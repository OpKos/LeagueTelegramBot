from app.sqlalchemy_parser import SqliteParser, Player, Table, TablePlayer, Game, GamePlayer

import configparser

FOUR_SEAT_ORDERS = [
    [0, 1, 2, 3],  # ABCD
    [1, 3, 0, 2],  # BDAC
    [2, 0, 3, 1],  # CADB
    [3, 2, 1, 0],  # DCBA
]

def main(db_path: str):
    db = SqliteParser(db_path)
    nicks = open("ranks_nicks.txt", "r", encoding="utf-8").readlines()
    players = []
    for nick in nicks:
        nick = nick.strip("\n")
        p = db.get_player(tenhou_name=nick)
        if not isinstance(p, Player):
            print(p)
            print(nick, "not found")
            quit()
        players.append(p)
    players = players[::2]+list(reversed(players[1::2]))

    n = len(players)
    tables = []
    for i in range(0,n,2):
        idxs = [i, (i + 1) % n, (i + 3) % n, (i + 4) % n]
        tables.append([players[j] for j in idxs])

    new_tables = []
    for i in range(0,n//4):
        new_tables.append(tables[i])
        new_tables.append(tables[n//2-i-1])
    tables = new_tables

    for table_players in tables:
        table = Table(visible=False)
        db.session.add(table)
        db.session.flush()
        db.reveal_table(table.table_id)

        # seats
        for seat, player in enumerate(table_players):
            db.session.add(TablePlayer(table_id=table.table_id, p_id=player.p_id, seat=seat))

        # Игры
        orders = FOUR_SEAT_ORDERS

        for order in orders:
            game = Game(table_id=table.table_id, started=0)
            db.session.add(game)

            db.session.flush()
            for seat, player_idx in enumerate(order):
                db.session.add(GamePlayer(game_id=game.game_id,
                                              p_id=table_players[player_idx].p_id,
                                              seat=seat))

    db.session.commit()



if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")
    db_path = config.get("Settings", "database")
    main(db_path)
