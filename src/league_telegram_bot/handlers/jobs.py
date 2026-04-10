from __future__ import annotations

import datetime
import logging
import os

import pytz
from telegram import InputMediaPhoto
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..leaderboard import make_leaderboard
from .utils import timestring_from_timestamp

logger = logging.getLogger()


async def startup_job_callback(context: ContextTypes.DEFAULT_TYPE):
    handlers = context.job.data.get("handlers")
    tz = pytz.timezone("Europe/Moscow")
    daily_chat_callback_time = datetime.time(hour=10, minute=0, tzinfo=tz)
    context.job_queue.run_daily(
        send_daily_chat_message,
        time=daily_chat_callback_time,
        name="daily posts",
        data={"handlers": handlers},
    )
    morning_calllback_time = datetime.time(hour=10, minute=0, tzinfo=tz)
    evening_callback_time = datetime.time(hour=21, minute=0, tzinfo=tz)
    context.job_queue.run_daily(
        remind_tables,
        time=morning_calllback_time,
        name="morning reminders",
        data={"handlers": handlers},
    )
    context.job_queue.run_daily(
        remind_tables,
        time=evening_callback_time,
        name="evening reminders",
        data={"handlers": handlers},
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


async def remind_tables(context: ContextTypes.DEFAULT_TYPE) -> None:
    handlers = context.job.data.get("handlers")
    timezone = pytz.timezone("Europe/Moscow")
    now = datetime.datetime.now(tz=timezone)
    cutoff = now + datetime.timedelta(hours=15)
    cutoff = int(cutoff.timestamp())
    times = handlers.tables.get_all_relevant_table_times(
        right_cutoff=cutoff, left_cutoff=int(now.timestamp())
    )
    for time in times:
        if time.need_reminder == 0:
            continue
        message = f"Напоминание о назначенном времени:\n{timestring_from_timestamp(time.time, day=True, weekday=True)}"
        try:
            await context.bot.send_message(chat_id=time.table.chat_id, text=message)
            time.need_reminder = 0
        except Exception as e:
            logger.info(e)
    handlers.session_manager.session.commit()
