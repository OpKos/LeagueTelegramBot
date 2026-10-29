from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from league_telegram_bot.handlers.tables import TableHandlers


def _game_and_update():
    players = [
        SimpleNamespace(
            p_id=index,
            tenhou_name=f"tenhou{index}",
            irl_name=f"Player {index}",
        )
        for index in range(4)
    ]
    game = SimpleNamespace(
        game_id=17,
        table=SimpleNamespace(name="T1"),
        players=lambda: players,
    )
    table = SimpleNamespace(table_id=4, name="T1")
    chat = SimpleNamespace(send_message=AsyncMock())
    query = SimpleNamespace(
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(chat=chat),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=None,
        effective_chat=None,
    )
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    handler = object.__new__(TableHandlers)
    handler.chat = -100

    def translate(_lang, key, **kwargs):
        if key == "start_game_done":
            return "Приятной игры!"
        if key == "start_game_announcement":
            return f"Игра за столом {kwargs['table']} запущена:\n{kwargs['players']}"
        if key == "start_game_missing_players":
            return f"Игроки не в лобби: {kwargs['players']}, статус готовности обновлён."
        raise AssertionError(f"Unexpected translation key: {key}")

    handler.tr = translate
    handler._ready_button_reply_markup = "ready-markup"
    handler.players = Mock()
    handler.ready = Mock()
    handler.games = Mock()
    handler.tenhou_client = Mock()
    return handler, game, table, players, update, context, chat


def test_game_start_success_updates_game_resets_players_and_notifies_chats() -> None:
    handler, game, table, players, update, context, _chat = _game_and_update()
    handler.tenhou_client.start_game.return_value = ("STARTED", [], True)

    asyncio.run(handler.game_start(game, table, update, context))

    handler.tenhou_client.start_game.assert_called_once_with(
        [player.tenhou_name for player in players]
    )
    handler.games.set_game_status.assert_called_once_with(game.game_id, 1)
    assert [call.args[0] for call in handler.ready.set_player_unready.call_args_list] == [
        player.p_id for player in players
    ]
    context.bot.send_message.assert_awaited_once()
    assert context.bot.send_message.await_args.kwargs["chat_id"] == -100
    update.callback_query.edit_message_text.assert_awaited_once_with(text="Приятной игры!")


def test_game_start_member_not_found_unreadies_missing_players_and_keeps_ready_ui() -> None:
    handler, game, table, _players, update, context, chat = _game_and_update()
    missing_player = SimpleNamespace(p_id=3)
    handler.tenhou_client.start_game.return_value = ("MEMBER NOT FOUND", ["tenhou3"], False)
    handler.players.get_player.return_value = missing_player
    handler.games.get_table_ready_string.return_value = "updated ready status"

    asyncio.run(handler.game_start(game, table, update, context))

    handler.ready.set_player_unready.assert_called_once_with(missing_player.p_id)
    update.callback_query.edit_message_text.assert_awaited_once_with(
        text="updated ready status", reply_markup="ready-markup"
    )
    chat.send_message.assert_awaited_once()
    assert "tenhou3" in chat.send_message.await_args.kwargs["text"]
    context.bot.send_message.assert_not_awaited()


def test_game_start_failure_notifies_table_without_changing_game_or_ready_state() -> None:
    handler, game, table, _players, update, context, chat = _game_and_update()
    handler.tenhou_client.start_game.return_value = ("LOBBY FULL", [], False)
    handler.tr = lambda _lang, key, **kwargs: f"start_game_failed: {kwargs['reason']}"

    asyncio.run(handler.game_start(game, table, update, context))

    handler.games.set_game_status.assert_not_called()
    handler.ready.set_player_unready.assert_not_called()
    chat.send_message.assert_awaited_once_with(text="start_game_failed: LOBBY FULL")
    context.bot.send_message.assert_not_awaited()
    update.callback_query.edit_message_text.assert_not_awaited()


def test_table_check_starts_first_ready_game_only() -> None:
    handler, game, _table, _players, update, context, _chat = _game_and_update()
    table = SimpleNamespace(table_id=4)
    handler.games.get_first_ready_game.return_value = game
    handler.game_start = AsyncMock()

    asyncio.run(handler.table_check_and_start_game(table, update, context))

    handler.games.get_first_ready_game.assert_called_once_with(table.table_id)
    handler.game_start.assert_awaited_once_with(game, table, update, context)


def test_table_check_does_not_start_when_no_game_is_ready() -> None:
    handler, _game, _table, _players, update, context, _chat = _game_and_update()
    table = SimpleNamespace(table_id=4)
    handler.games.get_first_ready_game.return_value = None
    handler.game_start = AsyncMock()

    asyncio.run(handler.table_check_and_start_game(table, update, context))

    handler.games.get_first_ready_game.assert_called_once_with(table.table_id)
    handler.game_start.assert_not_awaited()
