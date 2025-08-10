# stage1_seating.py
import random
from sqlalchemy_parser import SqliteParser, Player, Table, TablePlayer, Game, GamePlayer
import configparser

# Сид можно задать для воспроизводимости
RANDOM_SEED = 30

# Маппинг мест в играх
FOUR_SEAT_ORDERS = [
    [0, 1, 2, 3],  # ABCD
    [1, 3, 0, 2],  # BDAC
    [2, 0, 3, 1],  # CADB
    [3, 2, 1, 0],  # DCBA
]

SIX_SEAT_ORDERS = [
    [0, 2, 3, 1],  # ACDB
    [2, 0, 3, 1],  # CADB
    [1, 4, 0, 5],  # BEAF
    [4, 1, 5, 0],  # EBFA
    [5, 3, 2, 4],  # DFCE
    [3, 5, 4, 2],  # FDEC
]

def main(db_path):
    parser = SqliteParser(db_path)

    # 1) Берём всех игроков с enable_seating = 1
    players = parser.session.query(Player).filter(Player.enable_seating == True).all()
    if not players:
        print("Нет игроков для рассадки")
        return

    # 2) Перемешиваем
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)
    random.shuffle(players)

    N = len(players)
    tables = []

    # 3) Столы по схеме (i, i-1, i-4, i-6)
    for i in range(N):
        idxs = [i, (i - 1) % N, (i - 4) % N, (i - 6) % N]
        tables.append([players[j] for j in idxs])

    # 4) Чётные/нечётные N
    if N % 2 == 0:
        # 4.1) (i, i-7, i-14, i-23) для чётных i
        for i in range(0, N, 2):
            idxs = [i, (i - 7) % N, (i - 14) % N, (i - 23) % N]
            tables.append([players[j] for j in idxs])
    else:
        # 4.1) (0, 7, 14, 21, 28, 35)
        special6 = [0, 7, 14, 21, 28, 35]
        tables.append([players[j] for j in special6])

        # 4.2) фиксированные шестёрки
        fixed = [
            (0, 8, 26, 34),
            (7, 17, 27, 34),
            (14, 2, 26, 33),
            (21, 1, 9, 33),
            (28, 1, 8, 17),
            (35, 2, 9, 27),
        ]
        used_indices = set()
        for idxs in fixed:
            used_indices.update(idxs)
            tables.append([players[j] for j in idxs])

        # 4.3) Убираем 9 игроков
        remaining = [p for idx, p in enumerate(players) if idx not in used_indices]

        # 4.4) (i, i-7, i-14, i-23) для чётных i (в новом массиве)
        M = len(remaining)
        for i in range(0, M, 2):
            idxs = [i, (i - 7) % M, (i - 14) % M, (i - 23) % M]
            tables.append([remaining[j] for j in idxs])

    # Запись в БД
    for table_players in tables:
        table = Table(visible=False)
        parser.session.add(table)
        parser.session.flush()  # Чтобы появился table_id

        # seats
        for seat, player in enumerate(table_players):
            parser.session.add(TablePlayer(table_id=table.table_id, p_id=player.p_id, seat=seat))

        # Игры
        if len(table_players) == 4:
            orders = FOUR_SEAT_ORDERS
        elif len(table_players) == 6:
            orders = SIX_SEAT_ORDERS
        else:
            raise ValueError(f"Неподдерживаемое количество игроков за столом: {len(table_players)}")

        for order in orders:
            game = Game(table_id=table.table_id, started=0)
            parser.session.add(game)
            parser.session.flush()
            for seat, player_idx in enumerate(order):
                parser.session.add(GamePlayer(game_id=game.game_id,
                                              p_id=table_players[player_idx].p_id,
                                              seat=seat))
    parser.session.commit()
    print(f"Создано {len(tables)} столов")

if __name__ == "__main__":
        
    config = configparser.ConfigParser()
    config.read("config.ini")
    db_path = config.get("Settings", "database")
    main(db_path)
