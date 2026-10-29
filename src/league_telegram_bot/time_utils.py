from __future__ import annotations

import datetime
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
