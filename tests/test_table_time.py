from __future__ import annotations

import datetime

import pytest

from league_telegram_bot.handlers.tables import (
    TableTimeInputError,
    parse_table_time,
    validate_scheduled_game_count,
)


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
    class TableStub:
        table_times = [type("TimeStub", (), {"games": 2})()]

        @staticmethod
        def unfinished_games():
            return [object(), object(), object()]

    validate_scheduled_game_count(TableStub(), 1)

    with pytest.raises(TableTimeInputError) as error:
        validate_scheduled_game_count(TableStub(), 2)

    assert error.value.reason == "too_many_games"
