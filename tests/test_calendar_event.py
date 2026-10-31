from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from league_telegram_bot.handlers.utils import generate_calendar_event


def test_generate_calendar_event_writes_utc_event(tmp_path: Path) -> None:
    filename = tmp_path / "table.ics"
    start_time = datetime.fromisoformat("2026-10-31T12:30:00+03:00")

    generate_calendar_event("Kawa Table A", start_time, timedelta(hours=2), str(filename))

    lines = filename.read_text(encoding="utf-8").splitlines()

    assert lines[:4] == [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Python Calendar Generator//EN",
        "BEGIN:VEVENT",
    ]
    assert lines[4].startswith("UID:") and lines[4][4:]
    datetime.strptime(lines[5].removeprefix("DTSTAMP:"), "%Y%m%dT%H%M%SZ")
    assert lines[6:] == [
        "DTSTART:20261031T093000Z",
        "DTEND:20261031T113000Z",
        "SUMMARY:Kawa Table A",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
