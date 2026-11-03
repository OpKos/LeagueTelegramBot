from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from league_telegram_bot.handlers import jobs, registration
from league_telegram_bot.handlers.core import BaseHandlers
from league_telegram_bot.handlers.registration import RegistrationHandlers
from league_telegram_bot.handlers.tables import TableHandlers
from league_telegram_bot.models import Table
from league_telegram_bot.time_utils import datetime_to_timestamp


def test_set_timezone_saves_choice_and_shows_local_time(monkeypatch) -> None:
    player = SimpleNamespace(p_id=10)
    handlers = object.__new__(RegistrationHandlers)
    handlers.players = Mock()
    handlers.players.get_player.return_value = player
    handlers.language_for_user = lambda _user_id: "en"
    handlers.tr = lambda _lang, _key, **values: (
        f"Timezone set to {values['timezone']} at {values['time']}"
    )
    local_now = datetime.datetime(2026, 10, 31, 12, 34, tzinfo=ZoneInfo("Europe/Moscow"))
    monkeypatch.setattr(registration, "now_in_timezone", lambda _timezone: local_now)
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="tester", full_name="Tester"),
        effective_chat=SimpleNamespace(id=42),
        effective_message=message,
    )

    asyncio.run(handlers.set_timezone(update, SimpleNamespace(args=["Europe/Moscow"])))

    handlers.players.set_timezone.assert_called_once_with(10, "Europe/Moscow")
    message.reply_text.assert_awaited_once_with("Timezone set to Europe/Moscow at 2026-10-31 12:34")


@pytest.mark.parametrize("args", [[], ["Not/A_Timezone"], ["Europe/Moscow", "extra"]])
def test_set_timezone_invalid_arguments_include_timezone_list(args: list[str]) -> None:
    handlers = object.__new__(RegistrationHandlers)
    handlers.language_for_user = lambda _user_id: "ru"
    response = "Usage: /set_timezone <timezone>. List: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
    handlers.tr = lambda _lang, _key, **_values: response
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="tester", full_name="Tester"),
        effective_chat=SimpleNamespace(id=42),
        effective_message=message,
    )

    asyncio.run(handlers.set_timezone(update, SimpleNamespace(args=args)))

    message.reply_text.assert_awaited_once_with(response)


def test_timezone_for_user_falls_back_to_configured_timezone() -> None:
    handlers = object.__new__(BaseHandlers)
    handlers.timezone = "Europe/Moscow"
    handlers.players = Mock()
    handlers.players.get_player.return_value = SimpleNamespace(timezone=None)
    assert handlers.timezone_for_user(42) == "Europe/Moscow"
    handlers.players.get_player.return_value = SimpleNamespace(timezone="Asia/Tokyo")
    assert handlers.timezone_for_user(42) == "Asia/Tokyo"


def test_table_get_timezones_uses_player_timezones_and_default() -> None:
    table = Table()
    table.get_all_players = lambda: [
        SimpleNamespace(timezone=None),
        SimpleNamespace(timezone="Asia/Tokyo"),
        SimpleNamespace(timezone="Asia/Tokyo"),
    ]

    assert table.get_timezones("Europe/Moscow") == ["Asia/Tokyo", "Europe/Moscow"]

    table.get_all_players = lambda: []
    assert table.get_timezones("Europe/Moscow") == ["Europe/Moscow"]


def test_languages_for_table_uses_all_player_languages_and_russian_fallback() -> None:
    handlers = object.__new__(BaseHandlers)
    table = SimpleNamespace(
        get_all_players=lambda: [
            SimpleNamespace(language="en"),
            SimpleNamespace(language="ru"),
            SimpleNamespace(language="en"),
        ]
    )

    assert handlers.languages_for_table(table) == ["ru", "en"]
    table.get_all_players = lambda: [SimpleNamespace(language="unknown")]
    assert handlers.languages_for_table(table) == ["ru"]


def test_timetable_uses_viewer_timezone_and_labels_it() -> None:
    timezone = "Asia/Tokyo"
    table = SimpleNamespace(name="T1", get_unfinished_players=lambda: [])
    table_time = SimpleNamespace(
        table=table,
        time=datetime_to_timestamp(datetime.datetime(2026, 1, 2, 17), "Europe/Moscow"),
        games=1,
    )
    handlers = object.__new__(TableHandlers)
    handlers.timezone = "Europe/Moscow"
    handlers.timezone_for_user = lambda _user_id: timezone
    handlers.language_for_user = lambda _user_id: "en"
    handlers.tables = Mock()
    handlers.tables.get_all_relevant_table_times.return_value = [table_time]
    templates = {
        "table_time_string": "{time} table {table} ({games}): {players}",
        "game_amount_one_en": "{count} game",
        "timezone_note": "Times are shown in {timezone}. Change with /set_timezone",
        "timetable_empty": "No games",
    }

    def translate(_lang: str, key: str, **values: str) -> str:
        return templates[key].format(**values)

    handlers.tr = translate
    handlers.translate = lambda lang: lambda key, **values: translate(lang, key, **values)
    handlers.weekday_names = lambda _lang: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    message = SimpleNamespace(
        chat=SimpleNamespace(type="private"),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="tester", full_name="Tester"),
        effective_chat=SimpleNamespace(id=42),
        effective_message=message,
    )

    asyncio.run(handlers.timetable_command(update, SimpleNamespace(args=[])))

    response = message.reply_text.await_args.args[0]
    assert "02.01 23:00" in response
    assert "Asia/Tokyo" in response
    assert "Europe/Moscow" not in response


def test_table_reminder_includes_each_player_timezone(monkeypatch) -> None:
    timestamp = datetime_to_timestamp(datetime.datetime(2026, 1, 2, 17), "Europe/Moscow")
    scheduled = SimpleNamespace(
        need_reminder=1,
        time=timestamp,
        table=SimpleNamespace(
            chat_id=123,
            get_timezones=lambda _default: ["Asia/Tokyo", "Europe/Moscow"],
            get_all_players=lambda: [
                SimpleNamespace(language="ru"),
                SimpleNamespace(language="en"),
            ],
        ),
    )
    handlers = SimpleNamespace(
        timezone="Europe/Moscow",
        tables=SimpleNamespace(get_all_relevant_table_times=Mock(return_value=[scheduled])),
        weekday_names=lambda _lang: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        languages_for_table=lambda _table: ["ru", "en"],
        tr=lambda lang, key, **values: (
            f"{values['timezone']}: {values['time']}"
            if key == "timezone_time"
            else (
                f"Напоминание о назначенном времени (через {values['countdown']})"
                if key == "reminder_message" and lang == "ru"
                else (
                    f"Reminder of the scheduled time (in {values['countdown']})"
                    if key == "reminder_message"
                    else f"{values['hours']} ч {values['minutes']} мин"
                    if key == "reminder_countdown_minutes" and lang == "ru"
                    else (
                        f"{values['hours']} hours {values['minutes']} minutes"
                        if key == "reminder_countdown_minutes"
                        else f"{values['hours']} ч"
                        if key == "reminder_countdown_hours" and lang == "ru"
                        else f"{values['hours']} hours"
                        if key == "reminder_countdown_hours"
                        else f"{values['minutes']} мин"
                        if key == "reminder_countdown_minutes_only" and lang == "ru"
                        else f"{values['minutes']} minutes"
                        if key == "reminder_countdown_minutes_only"
                        else str(values.get("minutes", ""))
                    )
                )
            )
        ),
        session_manager=SimpleNamespace(session=SimpleNamespace(commit=Mock())),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        job=SimpleNamespace(data={"handlers": handlers}),
        bot=bot,
    )
    now = datetime.datetime(2026, 1, 2, 10, 30, 20, tzinfo=datetime.UTC)
    monkeypatch.setattr(jobs, "now_in_timezone", lambda _timezone: now)

    asyncio.run(jobs.remind_tables(context))

    message = bot.send_message.await_args.kwargs["text"]
    assert "через 3 ч 30 мин" in message
    assert "in 3 hours 30 minutes" in message
    assert "Asia/Tokyo: 02.01 23:00" in message
    assert "Europe/Moscow: 02.01 17:00" in message
    assert "Fri" not in message
    assert message.count("Asia/Tokyo") == 1
    assert message.count("Europe/Moscow") == 1
    assert scheduled.need_reminder == 0
    handlers.session_manager.session.commit.assert_called_once()
