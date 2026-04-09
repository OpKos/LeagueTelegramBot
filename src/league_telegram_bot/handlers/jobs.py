from __future__ import annotations

import datetime
import logging
import os

import pytz
from telegram import InputMediaPhoto
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..leaderboard import make_leaderboard

logger = logging.getLogger()


async def startup_job_callback(context: ContextTypes.DEFAULT_TYPE):
    handlers = context.job.data.get("handlers")
    tz = pytz.timezone("Europe/Moscow")
    callback_time = datetime.time(hour=10, minute=0, tzinfo=tz)
    context.job_queue.run_daily(
        send_daily_chat_message, time=callback_time, name="daily posts", data={"handlers": handlers}
    )


async def send_daily_chat_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    handlers = context.job.data.get("handlers")
    events = handlers.events.get_started_events()
    api_url = os.getenv("PANTHEON_GAME_API_URL", "https://gameapi.riichimahjong.org")
    client = PantheonClient(
        api_url,
        server_path_prefix="/v2",
    )
    image_links = []
    for event in events:
        result = client.get_rating_table(
            event_id_list=[event.pantheon_id], order="desc", order_by="rating"
        )
        if result.get("ok"):
            image_link = make_leaderboard(event=event, pantheon_data=result.get("players"))
            image_links.append(image_link)
            logger.info(f"Создана таблица {image_link} для события {event.event_id}")
        else:
            logger.info(
                f"Для события {event.event_id} ошибка {result.get("error", "неизвестная ошибка")}"
            )

    if len(image_links) == 1:
        await context.bot.send_photo(chat_id=handlers.chat, photo=image_links[0])
    elif len(image_links) > 1:
        media = []
        for link in image_links:
            with open(link, "rb") as image_file:
                media.append(InputMediaPhoto(media=image_file))
        await context.bot.send_media_group(chat_id=handlers.chat, media=media)
