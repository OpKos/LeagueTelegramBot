from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from league_telegram_bot.handlers import tables as table_handlers
from league_telegram_bot.handlers.core import BaseHandlers
from league_telegram_bot.handlers.tables import (
    TableHandlers,
    parse_table_time,
)
from league_telegram_bot.models import Game, Table, TableTime
from league_telegram_bot.time_utils import TableTimeInputError, datetime_to_timestamp


def test_parse_table_time_with_numeric_day_and_colonless_minutes() -> None:
    now = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC)

    result = parse_table_time("2", "1930", "2", now, "Europe/Moscow")

    assert result.display == "02.01 19:30 (игр: 2)"
    assert result.games == 2
    assert result.timestamp == 1767371400


def test_parse_table_time_with_weekday_and_hour_only() -> None:
    now = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC)

    result = parse_table_time("пт", "17", "1", now, "Europe/Moscow")

    assert result.display == "02.01 17:00 (игр: 1)"


@pytest.mark.parametrize(
    ("weekday", "expected_day"),
    [
        ("mon", 5),
        ("monday", 5),
        ("tue", 6),
        ("tues", 6),
        ("tuesday", 6),
        ("wed", 7),
        ("wednesday", 7),
        ("thu", 1),
        ("thur", 1),
        ("thurs", 1),
        ("thursday", 1),
        ("fri", 2),
        ("friday", 2),
        ("sat", 3),
        ("saturday", 3),
        ("sun", 4),
        ("sunday", 4),
        ("Fri.", 2),
        ("FRIDAY", 2),
    ],
)
def test_parse_table_time_accepts_english_weekday_names(weekday: str, expected_day: int) -> None:
    now = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC)

    result = parse_table_time(weekday, "17", "1", now, "Europe/Moscow")

    assert result.display == f"{expected_day:02d}.01 17:00 (игр: 1)"


@pytest.mark.parametrize(
    ("day_arg", "time_arg", "games_arg", "reason"),
    [
        ("not-a-day", "17", "1", "weekday_not_found"),
        ("2", "not-a-time", "1", "invalid_time"),
        ("2", "17", "0", "nonpositive_game_count"),
        ("2", "17", "games", "invalid_game_count"),
        ("2", "2561", "1", "invalid_time"),
    ],
)
def test_parse_table_time_rejects_invalid_input(
    day_arg: str,
    time_arg: str,
    games_arg: str,
    reason: str,
) -> None:
    now = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC)

    with pytest.raises(TableTimeInputError) as error:
        parse_table_time(day_arg, time_arg, games_arg, now, "Europe/Moscow")

    assert error.value.reason == reason


def test_validate_scheduled_game_count_subtracts_existing_allocations() -> None:
    table = Table(
        table_times=[TableTime(games=2)],
        games=[Game(game_id=game_id, started=0) for game_id in range(3)],
    )

    assert table.remaining_unassigned_games() == 1
    table.validate_scheduled_game_count(1)

    with pytest.raises(TableTimeInputError) as error:
        table.validate_scheduled_game_count(2)

    assert error.value.reason == "too_many_games"


def test_set_time_command_appends_one_time_without_clearing_existing_times(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    player = SimpleNamespace(p_id=12, language="ru")
    second_player = SimpleNamespace(p_id=13, timezone="Asia/Tokyo", language="en")
    table = SimpleNamespace(
        table_id=5,
        name="T1",
        table_times=[SimpleNamespace(games=2)],
        unfinished_games=lambda: [object(), object(), object()],
        get_unfinished_players=lambda: [player],
        get_all_players=lambda: [player, second_player],
        get_timezones=lambda _default: ["Asia/Tokyo", "Europe/Moscow", "UTC"],
        validate_scheduled_game_count=Mock(),
    )
    scheduled_times = Mock()
    scheduled_times.get_table.return_value = table
    scheduled_times.add_table_time.return_value = True
    scheduled_times.clear_table_times = Mock()
    chat = SimpleNamespace(send_poll=AsyncMock())
    message = SimpleNamespace(
        chat_id=300,
        reply_text=AsyncMock(),
        reply_document=AsyncMock(),
        chat=chat,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="player", full_name="Player"),
        effective_chat=SimpleNamespace(id=300),
        effective_message=message,
    )
    context = SimpleNamespace(args=["fri", "17", "1"])
    now = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    monkeypatch.setattr(table_handlers, "now_in_timezone", lambda _timezone: now)

    handlers = object.__new__(TableHandlers)
    handlers.tables = scheduled_times
    handlers.players = Mock()
    handlers.players.get_player.return_value = player
    handlers.timezone = "UTC"
    handlers.timezone_for_user = lambda _user_id: "Europe/Moscow"
    templates = {
        "set_time_success": {
            "ru": "Время установлено ({games}).",
            "en": "Time set ({games}).",
        },
        "timezone_time": "{timezone}: {time}",
        "games_amount_ru_one": "{count} ханчан",
        "game_amount_one_en": "{count} game",
        "set_time_poll": {
            "ru": "Согласен играть в это время.",
            "en": "Agree to play at that time.",
        },
        "set_time_calendar_title": {
            "ru": "Кава, стол {table} ({games})",
            "en": "Kawa Table {table} ({games})",
        },
    }

    def translate(_lang: str, key: str, **kwargs: str) -> str:
        template = templates[key]
        if isinstance(template, dict):
            template = template[_lang]
        return template.format(**kwargs)

    handlers.tr = translate
    handlers.translate = lambda lang: lambda key, **kwargs: handlers.tr(lang, key, **kwargs)
    handlers.languages_for_table = BaseHandlers.languages_for_table.__get__(handlers)
    handlers.tr_for_table = BaseHandlers.tr_for_table.__get__(handlers)

    asyncio.run(handlers.set_time_command(update, context))

    table.validate_scheduled_game_count.assert_called_once_with(1)

    expected_timestamp = datetime_to_timestamp(
        datetime.datetime(2026, 1, 2, 17, 0), "Europe/Moscow"
    )
    scheduled_times.add_table_time.assert_called_once_with(
        table_id=table.table_id,
        timestamp=expected_timestamp,
        games=1,
        reminder_cutoff=int((now + datetime.timedelta(hours=12)).timestamp()),
    )
    scheduled_times.clear_table_times.assert_not_called()
    message.reply_text.assert_awaited_once()
    confirmation = message.reply_text.await_args.args[0]
    assert confirmation == (
        "Время установлено (1 ханчан).\n"
        "Time set (1 game).\n"
        "<b>UTC: 02.01 14:00</b>\n"
        "Europe/Moscow: 02.01 17:00\n"
        "Asia/Tokyo: 02.01 23:00"
    )
    assert message.reply_text.await_args.kwargs["parse_mode"] == "HTML"
    assert message.reply_document.await_count == 2
    filenames = [call.kwargs["filename"] for call in message.reply_document.await_args_list]
    assert filenames == ["Kawa_Table_T1_ru.ics", "Kawa_Table_T1_en.ics"]
    russian_calendar = (tmp_path / filenames[0]).read_text(encoding="utf-8")
    english_calendar = (tmp_path / filenames[1]).read_text(encoding="utf-8")
    assert "SUMMARY:Кава, стол T1 (1 ханчан)" in russian_calendar
    assert "SUMMARY:Kawa Table T1 (1 game)" in english_calendar
    chat.send_poll.assert_awaited_once()
    poll_question = chat.send_poll.await_args.kwargs["question"]
    assert "<b>UTC: 02.01 14:00</b>" in poll_question
    assert chat.send_poll.await_args.kwargs["question_parse_mode"] == "HTML"
    assert "Asia/Tokyo: 02.01 23:00" in poll_question
    assert "Europe/Moscow: 02.01 17:00" in poll_question
    assert chat.send_poll.await_args.kwargs["options"] == [
        "Согласен играть в это время./Agree to play at that time."
    ]
