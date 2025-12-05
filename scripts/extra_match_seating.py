from app.sqlalchemy_parser import SqlParser, Player, Table, TablePlayer, Game, GamePlayer

import configparser


FOUR_SEAT_ORDERS = [
    [0, 1, 2, 3],  # ABCD
    [1, 3, 0, 2],  # BDAC
    [2, 0, 3, 1],  # CADB
    [3, 2, 1, 0],  # DCBA
    [0, 1, 3, 2],  # ABDC
    [1, 0, 2, 3],  # BACD
    [2, 3, 1, 0],  # CDBA
    [3, 2, 0, 1],  # DCAB
]

def main(db_path: str):
    db = SqlParser(db_path)
    ids = open("extra_ids.txt", "r", encoding="utf-8").readlines()
    players = []
    for id in ids:
        id = int(id.strip("\n"))
        p = db.get_player(p_id=id)
        if not isinstance(p, Player):
            print(p)
            print(nick, "not found")
            quit()
        players.append(p)

    n = len(players)
    tables = []
    for i in range(0,n,4):
        idxs = [i, (i + 1) % n, (i + 2) % n, (i + 3) % n]
        tables.append([players[j] for j in idxs])

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
    config.read("app/config.ini")
    db_path = config.get("Settings", "database")
    main(db_path)
