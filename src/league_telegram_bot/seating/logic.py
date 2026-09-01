import logging
import random
from collections import Counter

from .. import models
from ..services import GameService, TableService

logger = logging.getLogger()

FOUR_SEAT_ORDERS = [
    [0, 1, 2, 3],
    [1, 3, 0, 2],
    [2, 0, 3, 1],
    [3, 2, 1, 0],
]
SIX_SEAT_ORDERS = [
    [0, 2, 3, 1],
    [2, 0, 1, 3],
    [1, 4, 0, 5],
    [4, 1, 5, 0],
    [3, 5, 2, 4],
    [5, 3, 4, 2],
]


# ======================
# CORE GENERATION LOGIC
# ======================


def valid_triplet(n, x, y, z):
    vals = {0, x % n, (x + y) % n, (x + y + z) % n}
    return len(vals) == 4


def even_condition(x, y, z, n):
    vals = [(-x) % n, (-x - y) % n, (-x - y - z) % n]
    return sum(v % 2 == 0 for v in vals) == 1


def generate_tables(n, a, b, c):
    return [[i, (i + a) % n, (i + a + b) % n, (i + a + b + c) % n] for i in range(n)]


# ======================
# SCORING
# ======================


def compute_pair_counts(groups):
    pair_counts = Counter()

    for group in groups:
        for table in group:
            for i in range(4):
                for j in range(i + 1, 4):
                    a, b = sorted((table[i], table[j]))
                    pair_counts[(a, b)] += 1

    return pair_counts


def score_from_counts(pair_counts):
    return sum((v - 1) ** 2 for v in pair_counts.values() if v > 1)


# ======================
# REPAIR (IMPROVED)
# ======================


def repair_groups(groups, dummy, beam_width=6):
    states = [([], [])]

    for group in groups:
        new_states = []

        dummy_tables = [t for t in group if dummy in t]
        normal_tables = [t for t in group if dummy not in t]

        if len(dummy_tables) != 2:
            return None

        t1 = [p for p in dummy_tables[0] if p != dummy]
        t2 = [p for p in dummy_tables[1] if p != dummy]

        for partial_groups, leftovers in states:
            for x in t1:
                full = t2 + [x]
                rest = [p for p in t1 if p != x]

                if len(set(full)) < 4:
                    continue

                new_group = normal_tables + [full]

                new_states.append((partial_groups + [new_group], leftovers + rest))

        if not new_states:
            return None

        states = new_states[:beam_width]

    best_groups = None
    best_score = float("inf")

    for partial_groups, leftovers in states:
        if len(leftovers) != 8:
            continue

        if len(set(leftovers[2:])) < 6:
            continue

        for _ in range(10):
            random.shuffle(leftovers)
            t_a = leftovers[:4]
            t_b = leftovers[4:]

            if len(set(t_a)) < 4 or len(set(t_b)) < 4:
                continue

            groups_candidate = [g[:] for g in partial_groups]
            groups_candidate[0] = groups_candidate[0] + [t_a, t_b]

            pair_counts = compute_pair_counts(groups_candidate)
            score = score_from_counts(pair_counts)

            if score < best_score:
                best_score = score
                best_groups = groups_candidate

    return best_groups


# ======================
# BUILD
# ======================


def build_and_repair(n, params):
    a, b, c, d, e, f = params

    if n % 2 == 0:
        t1 = generate_tables(n, a, b, c)
        t2 = generate_tables(n, d, e, f)
        return [
            t1[::2],
            t1[1::2],
            t2[::2],
            t2[1::2],
        ]

    dummy = n
    n2 = n + 1

    t1 = generate_tables(n2, a, b, c)
    t2 = generate_tables(n2, d, e, f)

    groups = [
        t1[::2],
        t1[1::2],
        t2[::2],
        t2[1::2],
    ]

    return repair_groups(groups, dummy, n)


# ======================
# SEARCH
# ======================


def random_search(n, tries=50000):
    best_score = float("inf")
    best_groups = None
    best_params = None

    effective_n = n if n % 2 == 0 else n + 1

    for _ in range(tries):
        a, b, c = (random.randrange(1, effective_n) for _ in range(3))
        d, e, f = (random.randrange(1, effective_n) for _ in range(3))

        if not valid_triplet(effective_n, a, b, c):
            continue
        if not valid_triplet(effective_n, d, e, f):
            continue

        if not even_condition(a, b, c, effective_n):
            continue
        if not even_condition(d, e, f, effective_n):
            continue

        groups = build_and_repair(n, (a, b, c, d, e, f))
        if groups is None:
            continue

        pair_counts = compute_pair_counts(groups)
        score = score_from_counts(pair_counts)

        if score < best_score:
            best_score = score
            best_groups = groups
            best_params = (a, b, c, d, e, f)

            logger.info(f"New best score: {best_score} with params {best_params}")

            if score == 0:
                break

    return best_params, best_groups


# ======================
# MAIN ENTRY
# ======================


def create_seating(tables: TableService, games: GameService, event: models.Event):
    players = event.players()
    n = len(players)
    random.shuffle(players)

    params, groups = random_search(n)

    if groups is None:
        raise ValueError("Could not generate valid seating")

    number = 1
    for group_idx, group in enumerate(groups):
        group_tables = [[players[i] for i in table] for table in group]
        random.shuffle(group_tables)

        for table_order in group_tables:
            table = tables.create_table_with_players(
                event_id=event.event_id,
                table_name=f"{event.name}{number}",
                players=table_order,
                deadline_group=group_idx,
            )
            number += 1
            for order in FOUR_SEAT_ORDERS:
                game_order = [table_order[i] for i in order]
                games.create_game_with_players(table_id=table.table_id, players=game_order)


def add_table(
    tables: TableService,
    games: GameService,
    players: list[models.Player],
    event: models.Event,
    table_name: str,
    deadline_group: int = 0,
):
    table = tables.create_table_with_players(
        event_id=event.event_id,
        table_name=table_name,
        players=players,
        deadline_group=deadline_group,
    )
    schema = FOUR_SEAT_ORDERS
    if len(players) == 6:
        schema = SIX_SEAT_ORDERS
    for order in schema:
        game_order = [players[i] for i in order]
        games.create_game_with_players(table_id=table.table_id, players=game_order)
