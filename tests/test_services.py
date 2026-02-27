from __future__ import annotations

import pytest

from league_telegram_bot import models
from league_telegram_bot.models.base import Base
from league_telegram_bot.services import (
    EventService,
    GameService,
    PlayerService,
    ReadyService,
    RevealService,
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
    reveal = RevealService(manager, table_service=tables)
    yield manager, players, tables, events, ready, games, reveal
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
    manager, players, _tables, _events, _ready, _games, _reveal = services

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
    manager, players, tables, _events, _ready, games, _reveal = services

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
    manager, players, tables, _events, ready, games, _reveal = services

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


def test_reveal_service_reveals_table(services) -> None:
    manager, players, tables, events, _ready, _games, reveal = services

    event = models.Event(name="Reveal", started=1, global_minimum=1, global_maximum=1)
    manager.session.add(event)
    manager.session.commit()

    created = _create_players(players)
    for player in created:
        events.add_event_player(event.event_id, player.p_id)

    table = tables.create_table_with_players(event.event_id, "T1", created)
    manager.session.commit()

    revealed = reveal.try_reveal(event.event_id, cache=True)
    assert revealed is not False
    assert revealed.table_id == table.table_id

    table = manager.session.get(models.Table, table.table_id)
    assert table.visible == 1
    assert table.reveal_cached == 1
