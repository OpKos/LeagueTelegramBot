from __future__ import annotations

import logging
from collections.abc import Callable
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
    lang: str,
    translate: Callable[..., str],
    weekday_names: tuple[str, ...],
    mention: bool = False,
    explicit: bool = True,
) -> str:
    table = table_time.table
    timestamp = timestring_from_timestamp(
        table_time.time,
        timezone=timezone,
        weekday=explicit,
        day=explicit,
        weekday_names=weekday_names,
    )
    player_list = []
    for player in table.get_unfinished_players():
        player_list.append(player.clean_mention() if mention else player.irl_name)
    amount = game_amount_string(table_time.games, lang, translate)
    return translate(
        "table_time_string",
        time=timestamp,
        table=table.name,
        games=amount,
        players=",\n".join(player_list),
    )


def game_amount_string(games: int, lang: str, translate: Callable[..., str]) -> str:
    if lang == "en":
        key = "game_amount_one_en" if games == 1 else "game_amount_many_en"
        return translate(key, count=games)
    remainder_100 = games % 100
    if 11 <= remainder_100 <= 14:
        form = "many"
    elif games % 10 == 1:
        form = "one"
    elif 2 <= games % 10 <= 4:
        form = "few"
    else:
        form = "many"
    return translate(f"games_amount_ru_{form}", count=games)
