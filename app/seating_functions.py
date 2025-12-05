import random
import models
import csv

from sqlalchemy_parser import SqlParser

FOUR_SEAT_ORDERS = [
    [0, 1, 2, 3],  # ABCD
    [1, 3, 0, 2],  # BDAC
    [2, 0, 3, 1],  # CADB
    [3, 2, 1, 0],  # DCBA
]

def create_seating(db: SqlParser, event: models.Event):
    players = event.players()
    n = len(players)
    random.shuffle(players)
    seating: list[list[int]] = []
    with open(f'seating_files/best_N{n}.csv', 'r') as csvfile:
        seating_file = csv.reader(csvfile, delimiter=',')
        for row in seating_file:
            random.shuffle(row)
            seating.append([int(i) for i in row])
    random.shuffle(seating)
    tables = [[players[i] for i in j] for j in seating]
    for number, table_order in enumerate(tables, 1):
        table = db.create_table_with_players(
            event_id=event.event_id,
            table_name=event.name+str(number),
            players=table_order
        )
        orders = FOUR_SEAT_ORDERS
        for order in orders:
            game_order = [table_order[order[i]] for i in range(len(table_order))]
            db.create_game_with_players(
                table_id=table.table_id,
                players=game_order
            )





