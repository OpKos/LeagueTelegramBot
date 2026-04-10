from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from ..models import TableTime

ready_button_reply_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Готов", callback_data="RBReady"),
            InlineKeyboardButton("❌ Не готов", callback_data="RBUnready"),
            InlineKeyboardButton("Отмена", callback_data="RBCancel"),
        ]
    ]
)


def timestring_from_timestamp(timestamp: int, weekday: bool = False, day: bool = False) -> str:
    timezone = pytz.timezone("Europe/Moscow")
    res = ""
    weekdays = [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]
    date = datetime.datetime.fromtimestamp(timestamp, tz=timezone)
    if weekday:
        res += weekdays[date.weekday()] + " "
    if day:
        res += f"{date.strftime('%d.%m')} "
    res += f"{date.strftime('%H:%M')}"
    return res


def table_time_string(table_time: TableTime, mention: bool = False, explicit: bool = True) -> str:
    table = table_time.table
    ans = (
        timestring_from_timestamp(table_time.time, weekday=explicit, day=explicit)
        + " - "
        + f"Стол {table.name} (ханчанов: {table_time.games}):\n"
    )
    for i, player in enumerate(table.players()):
        if mention:
            ans += player.clean_mention()
        else:
            ans += player.irl_name
        if i % 2 == 0:
            ans += ", "
        elif i < len(table.players()) - 1:
            ans += ",\n"
        else:
            ans += ".\n\n"
    return ans
