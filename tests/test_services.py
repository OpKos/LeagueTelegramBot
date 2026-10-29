from __future__ import annotations

import pytest

from league_telegram_bot import models
from league_telegram_bot.models.base import Base
from league_telegram_bot.services import (
    EventService,
    GameService,
    PlayerService,
    ReadyService,
    SessionManager,
    TableService,
)


@pytest.fixture()
def services():
    manager = SessionManager(database_url="sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(manager.engine)
    players = PlayerService(manager)
    tables = TableService(manager)
    events = EventService(manager)
    ready = ReadyService(manager)
    games = GameService(manager, ready_service=ready)
    yield manager, players, tables, events, ready, games
    manager.session.close()


def _create_players(players: PlayerService, count: int = 4) -> list[models.Player]:
    created: list[models.Player] = []
    for i in range(count):
        players.register_player(
            telegram_id=1000 + i,
            telegram_name=f"user{i}",
            tenhou_id=f"tenhou{i}",
        )
        created.append(players.get_player(telegram_id=1000 + i))
    return created


def test_player_service_register_and_update(services) -> None:
    manager, players, _tables, _events, _ready, _games = services

    players.register_player(telegram_id=1, telegram_name="alice", tenhou_id="tenhou_alice")

    player = players.get_player(telegram_id=1)
    assert player is not None
    assert player.tenhou_name == "tenhou_alice"

    players.update_tenhou_nick(player.p_id, "tenhou_alice2")
    player = players.get_player(p_id=player.p_id)
    assert player.tenhou_name == "tenhou_alice2"

    players.fill_player_data(player.p_id, "Alice")
    player = players.get_player(p_id=player.p_id)
    assert player.irl_name == "Alice"

    manager.session.commit()


def test_table_and_game_creation(services) -> None:
    manager, players, tables, _events, _ready, games = services

    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)

    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()

    table = manager.session.get(models.Table, table.table_id)
    assert table is not None
    assert len(table.players()) == 4

    games.create_game_with_players(table.table_id, created)
    game = manager.session.query(models.Game).first()
    assert game is not None
    assert len(game.players()) == 4


def test_ready_and_game_status(services) -> None:
    manager, players, tables, _events, ready, games = services

    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)
    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()
    games.create_game_with_players(table.table_id, created)

    game = manager.session.query(models.Game).first()
    assert game is not None
    assert games.check_game_ready(game.game_id) is False

    for player in created:
        ready.set_player_ready(player.p_id)

    assert games.check_game_ready(game.game_id) is True

    ready.set_player_unready(created[0].p_id)
    assert games.check_game_ready(game.game_id) is False


def test_get_first_ready_game_returns_first_ready_unfinished_game(services) -> None:
    manager, players, tables, _events, ready, games = services
    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players, count=8)
    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()
    games.create_game_with_players(table.table_id, created[:4])
    games.create_game_with_players(table.table_id, created[4:])

    first_game, second_game = sorted(
        manager.session.query(models.Game).all(), key=lambda game: game.game_id
    )
    for player in created[4:]:
        ready.set_player_ready(player.p_id)

    assert games.get_first_ready_game(table.table_id).game_id == second_game.game_id

    for player in created[:4]:
        ready.set_player_ready(player.p_id)

    assert games.get_first_ready_game(table.table_id).game_id == first_game.game_id


def test_game_and_table_presentation_methods(services) -> None:
    manager, players, tables, _events, ready, games = services
    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)
    for index, player in enumerate(created):
        players.fill_player_data(player.p_id, f"Player {index}")
    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()
    games.create_game_with_players(table.table_id, created)

    game = manager.session.query(models.Game).first()
    assert game is not None
    table = manager.session.get(models.Table, table.table_id)
    assert table is not None

    assert table.players_string() == "Player 0\nPlayer 1\nPlayer 2\nPlayer 3"
    assert table.players_string(mention=True) == "\n".join(
        f"Player {index} (@user{index})" for index in range(4)
    )
    assert table.ready_string(set()) == "\n".join(f"❌ Player {index}" for index in range(4))
    assert game.ready_string({created[0].p_id}) == "\n".join(
        ["✅ Player 0", "❌ Player 1", "❌ Player 2", "❌ Player 3"]
    )
    assert game.are_players_ready({player.p_id for player in created}) is True
    translations = {
        "game_started": "Started",
        "game_not_started": "Not started",
        "game_info": "Game {game_id}\n{status}\n{players}\n\n",
    }
    assert game.info_string(lambda key, **kwargs: translations[key].format(**kwargs)) == (
        f"Game {game.game_id}\nNot started\nPlayer 0\nPlayer 1\nPlayer 2\nPlayer 3\n\n"
    )


def test_table_relevant_time_string(services) -> None:
    manager, players, tables, _events, _ready, _games = services
    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)
    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.add(
        models.TableTime(
            table_id=table.table_id,
            time=1767357000,
            games=1,
            need_reminder=0,
        )
    )
    manager.session.commit()
    table = manager.session.get(models.Table, table.table_id)
    assert table is not None

    assert table.get_relevant_times_string("Asia/Tokyo") == "Пятница 02.01 21:30"
    assert table.get_relevant_times_string("Asia/Tokyo", left_cutoff=1767357001) == ""


def test_table_service_adds_and_clears_scheduled_times(services) -> None:
    manager, players, tables, _events, _ready, _games = services
    event = models.Event(name="Event", started=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)
    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()

    assert tables.add_table_time(table.table_id, 100, 2, reminder_cutoff=150)
    assert tables.add_table_time(table.table_id, 200, 1, reminder_cutoff=150)

    table = tables.get_table(table_id=table.table_id)
    assert table is not None
    assert [(entry.time, entry.games, entry.need_reminder) for entry in table.table_times] == [
        (100, 2, 0),
        (200, 1, 1),
    ]

    assert tables.clear_table_times(table.table_id)
    assert tables.get_table(table_id=table.table_id).table_times == []


def test_player_tables_include_all_started_event_tables(services) -> None:
    manager, players, tables, _events, _ready, _games = services
    started_event = models.Event(name="Started", started=1)
    unstarted_event = models.Event(name="Unstarted", started=0)
    manager.session.add_all([started_event, unstarted_event])
    manager.session.commit()

    created = _create_players(players)
    started_table = tables.create_table_with_players(
        started_event.event_id, "Started table", created
    )
    tables.create_table_with_players(unstarted_event.event_id, "Unstarted table", created)
    manager.session.commit()

    player = manager.session.get(models.Player, created[0].p_id)
    assert player is not None
    assert player.all_tables() == [started_table]
