from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

RUSSIAN_WEEKDAYS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)

WEEKDAYS = {
    "пн": 0,
    "вт": 1,
    "ср": 2,
    "чт": 3,
    "пт": 4,
    "сб": 5,
    "вс": 6,
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


@dataclass(frozen=True)
class ParsedTableTime:
    timestamp: int
    games: int
    display: str


class TableTimeInputError(ValueError):
    def __init__(self, reason: str, message: str, **params: str):
        super().__init__(message)
        self.reason = reason
        self.params = params


def parse_table_time(
    day_arg: str,
    time_arg: str,
    games_arg: str,
    now: datetime.datetime,
    timezone: str,
) -> ParsedTableTime:
    try:
        games = int(games_arg)
    except ValueError as error:
        raise TableTimeInputError(
            "invalid_game_count", "Количество игр должно быть положительным."
        ) from error
    if games <= 0:
        raise TableTimeInputError(
            "nonpositive_game_count", "Количество игр должно быть положительным."
        )

    time_digits = "".join(ch for ch in time_arg if ch.isdigit())
    if not time_digits:
        raise TableTimeInputError("invalid_time", f"Время не распознано {time_arg}", time=time_arg)
    if len(time_digits) < 3:
        hour = int(time_digits)
        minute = 0
    else:
        hour = int(time_digits[:-2])
        minute = int(time_digits[-2:])

    if day_arg.isnumeric():
        day = int(day_arg)
        month = now.month
        year = now.year
        if day < now.day:
            month += 1
            if month > 12:
                month = 1
                year += 1
    else:
        weekday_name = day_arg.lower().rstrip(".")
        if weekday_name not in WEEKDAYS:
            raise TableTimeInputError(
                "weekday_not_found",
                f"День недели не найден {weekday_name}.",
                day=weekday_name,
            )
        weekday = WEEKDAYS[weekday_name]
        shift = (weekday - now.weekday()) % 7
        prospective_date = now + datetime.timedelta(days=shift)
        day = prospective_date.day
        month = prospective_date.month
        year = prospective_date.year

    try:
        prospective_start = datetime.datetime(
            year=year, month=month, day=day, hour=hour, minute=minute
        )
        timestamp = datetime_to_timestamp(prospective_start, timezone)
    except ValueError as error:
        raise TableTimeInputError(
            "invalid_time",
            f"Время не распознано {year}.{month}.{day} {hour}:{minute}",
            time=f"{year}.{month}.{day} {hour}:{minute}",
        ) from error

    return ParsedTableTime(
        timestamp=timestamp,
        games=games,
        display=prospective_start.strftime("%d.%m %H:%M") + f" (игр: {games})",
    )


def get_timezone(timezone: str) -> datetime.tzinfo:
    return ZoneInfo(timezone)


def now_in_timezone(timezone: str) -> datetime.datetime:
    return datetime.datetime.now(tz=get_timezone(timezone))


def datetime_to_timestamp(value: datetime.datetime, timezone: str) -> int:
    target_timezone = get_timezone(timezone)
    if value.tzinfo is None:
        localized = value.replace(tzinfo=target_timezone)
    else:
        localized = value.astimezone(target_timezone)
    return int(localized.timestamp())


def datetime_from_timestamp(timestamp: int, timezone: str) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(timestamp, tz=get_timezone(timezone))


def time_in_timezone(hour: int, minute: int, timezone: str) -> datetime.time:
    return datetime.time(hour=hour, minute=minute, tzinfo=get_timezone(timezone))


def timestring_from_timestamp(
    timestamp: int,
    timezone: str,
    weekday: bool = False,
    day: bool = False,
    weekday_names: list[str] = RUSSIAN_WEEKDAYS,
) -> str:
    date = datetime_from_timestamp(timestamp, timezone)
    result = ""
    if weekday:
        result += weekday_names[date.weekday()] + " "
    if day:
        result += f"{date.strftime('%d.%m')} "
    return result + date.strftime("%H:%M")
