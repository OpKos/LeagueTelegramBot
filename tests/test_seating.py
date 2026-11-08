from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from league_telegram_bot.handlers import admin as admin_handlers
from league_telegram_bot.handlers.admin import AdminHandlers
from league_telegram_bot.seating import logic

EIGHT_GAME_SEAT_ORDERS = [
    [0, 1, 2, 3],
    [1, 0, 3, 2],
    [0, 2, 1, 3],
    [1, 3, 2, 0],
    [3, 2, 0, 1],
    [2, 3, 1, 0],
    [3, 1, 0, 2],
    [2, 0, 3, 1],
]


def _players(count: int = 4) -> list[SimpleNamespace]:
    return [SimpleNamespace(p_id=index) for index in range(count)]


def _table_services():
    tables = Mock()
    tables.create_table.return_value = SimpleNamespace(table_id=12)
    games = Mock()
    return tables, games


def test_add_table_eight_games_uses_requested_orders_and_shuffles_players(monkeypatch) -> None:
    players = _players()
    original_players = players.copy()
    tables, games = _table_services()
    monkeypatch.setattr(logic.random, "shuffle", lambda items: items.reverse())

    logic.add_table(
        tables,
        games,
        players,
        SimpleNamespace(event_id=3),
        "T1",
        games_amount=8,
    )

    assert players == original_players
    expected_orders = [
        [original_players[3 - index].p_id for index in order] for order in EIGHT_GAME_SEAT_ORDERS
    ]
    assert [
        [player.p_id for player in call.kwargs["players"]]
        for call in games.create_game_with_players.call_args_list
    ] == expected_orders
    assert all(
        call.kwargs["table_id"] == 12 for call in games.create_game_with_players.call_args_list
    )


@pytest.mark.parametrize(
    ("player_count", "games_amount", "expected_game_count"),
    [(4, 4, 4), (6, 6, 6)],
)
def test_add_table_keeps_existing_supported_schedules(
    player_count: int, games_amount: int, expected_game_count: int
) -> None:
    tables, games = _table_services()

    logic.add_table(
        tables,
        games,
        _players(player_count),
        SimpleNamespace(event_id=3),
        "T1",
        games_amount=games_amount,
    )

    assert games.create_game_with_players.call_count == expected_game_count


@pytest.mark.parametrize(("player_count", "games_amount"), [(4, 6), (6, 4), (6, 8), (5, 5)])
def test_add_table_rejects_unsupported_player_and_game_counts(
    player_count: int, games_amount: int
) -> None:
    tables, games = _table_services()

    with pytest.raises(ValueError, match="Unsupported seating combination"):
        logic.add_table(
            tables,
            games,
            _players(player_count),
            SimpleNamespace(event_id=3),
            "T1",
            games_amount=games_amount,
        )

    tables.create_table.assert_not_called()
    games.create_game_with_players.assert_not_called()


def _admin_update(arguments: list[str]):
    handler = object.__new__(AdminHandlers)
    handler.is_admin = Mock(return_value=True)
    handler.events = Mock()
    handler.events.get_event.return_value = SimpleNamespace(event_id=9, pantheon_id=99)
    handler.players = Mock()
    handler.players.get_player.side_effect = lambda p_id: SimpleNamespace(p_id=p_id)
    handler.tables = Mock()
    handler.games = Mock()
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1, username="admin", full_name="Admin"),
        effective_chat=None,
        effective_message=message,
    )
    context = SimpleNamespace(args=arguments)
    return handler, update, context, message


def test_add_table_command_passes_game_amount_to_seating(monkeypatch) -> None:
    handler, update, context, _message = _admin_update(["9", "1", "4", "T1", "8"])
    client = Mock()
    monkeypatch.setattr(admin_handlers, "PantheonClient", Mock(return_value=client))
    monkeypatch.setattr(
        admin_handlers,
        "get_leaderboard_data",
        Mock(return_value=[[None, None, None, p_id] for p_id in range(4)]),
    )
    add_table = Mock()
    monkeypatch.setattr(admin_handlers, "add_table", add_table)

    asyncio.run(handler.add_table_command(update, context))

    assert add_table.call_args.kwargs["games_amount"] == 8
    assert add_table.call_args.kwargs["table_name"] == "T1"


def test_add_table_command_rejects_unsupported_combination_before_fetching_leaderboard() -> None:
    handler, update, context, message = _admin_update(["9", "1", "6", "T1", "8"])

    asyncio.run(handler.add_table_command(update, context))

    message.reply_text.assert_awaited_once()
    assert "Допустимые сочетания" in message.reply_text.await_args.args[0]
    handler.events.get_event.assert_not_called()


def test_add_table_command_requires_game_amount() -> None:
    handler, update, context, message = _admin_update(["9", "1", "4", "T1"])

    asyncio.run(handler.add_table_command(update, context))

    message.reply_text.assert_awaited_once()
    assert "<games>" in message.reply_text.await_args.args[0]
    handler.events.get_event.assert_not_called()
