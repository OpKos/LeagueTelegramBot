from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from ..time_utils import timestring_from_timestamp

if TYPE_CHECKING:
    from ..models import TableTime

_COMMAND_EVENT_LEVELS = {
    "started": logging.INFO,
    "finished": logging.INFO,
    "succeeded": logging.INFO,
    "rejected": logging.WARNING,
    "failed": logging.ERROR,
}


def log_command_event(
    update: Update,
    command: str,
    event: str,
    *,
    logger: logging.Logger | None = None,
    exc_info: bool = False,
    **details: object,
) -> None:
    level = _COMMAND_EVENT_LEVELS[event]
    user = update.effective_user
    chat = update.effective_chat
    identity = (
        f"user_id={user.id} username={(user.username or user.full_name)!r}"
        if user
        else "user_id=unknown username=unknown"
    )
    chat_id = chat.id if chat else "unknown"
    detail_text = " ".join(f"{key}={value!r}" for key, value in details.items())
    message = f"Command /{command} {event} {identity} chat_id={chat_id}"
    if detail_text:
        message = f"{message} {detail_text}"
    (logger or logging.getLogger(__name__)).log(level, message, exc_info=exc_info)


ready_button_reply_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Готов", callback_data="RBReady"),
            InlineKeyboardButton("❌ Не готов", callback_data="RBUnready"),
            InlineKeyboardButton("Отмена", callback_data="RBCancel"),
        ]
    ]
)


def table_time_string(
    table_time: TableTime,
    timezone: str,
    mention: bool = False,
    explicit: bool = True,
) -> str:
    table = table_time.table
    ans = (
        timestring_from_timestamp(
            table_time.time, weekday=explicit, day=explicit, timezone=timezone
        )
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


def game_amount_string(games: int):
    forms = ["ханчан", "ханчана", "ханчанов"]
    if games % 10 == 1:
        return f"{games} {forms[0]}"
    elif 4 >= games % 10 >= 2:
        return f"{games} {forms[1]}"
    else:
        return f"{games} {forms[2]}"
