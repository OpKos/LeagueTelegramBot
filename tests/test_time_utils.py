from __future__ import annotations

import datetime

from league_telegram_bot.time_utils import (
    datetime_from_timestamp,
    datetime_to_timestamp,
    timestring_from_timestamp,
)


def test_datetime_conversion_uses_requested_timezone() -> None:
    local_datetime = datetime.datetime(2026, 1, 2, 12, 30)

    timestamp = datetime_to_timestamp(local_datetime, timezone="Asia/Tokyo")
    converted = datetime_from_timestamp(timestamp, timezone="Asia/Tokyo")

    assert converted.replace(tzinfo=None) == local_datetime
    assert converted.utcoffset() == datetime.timedelta(hours=9)


def test_timestring_from_timestamp_uses_requested_timezone() -> None:
    timestamp = datetime_to_timestamp(datetime.datetime(2026, 1, 2, 12, 30), "Asia/Tokyo")

    assert timestring_from_timestamp(timestamp, "Asia/Tokyo", day=True) == "02.01 12:30"
    assert timestring_from_timestamp(timestamp, "Europe/Moscow", day=True) == "02.01 06:30"
