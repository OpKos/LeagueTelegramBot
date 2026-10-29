from __future__ import annotations

import datetime
import logging
import os

from telegram import InputMediaPhoto
from telegram.ext import ContextTypes

from ..integrations.pantheon import PantheonClient
from ..leaderboard import get_leaderboard_image
from ..time_utils import now_in_timezone, time_in_timezone, timestring_from_timestamp
from .timetable_image import create_timetable_image

logger = logging.getLogger()


async def startup_job_callback(context: ContextTypes.DEFAULT_TYPE):
    handlers = context.job.data.get("handlers")
    timezone = handlers.timezone
    daily_chat_callback_time = time_in_timezone(10, 0, timezone)
    context.job_queue.run_daily(
        send_daily_chat_message,
        time=daily_chat_callback_time,
        name="daily posts",
        data={"handlers": handlers},
    )
    morning_calllback_time = time_in_timezone(10, 0, timezone)
    evening_callback_time = time_in_timezone(21, 0, timezone)
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

    now = now_in_timezone(handlers.timezone)
    cutoff = now + datetime.timedelta(hours=30)
    cutoff = int(cutoff.timestamp())
    timetable = handlers.tables.get_all_relevant_table_times(
        right_cutoff=cutoff, left_cutoff=int(now.timestamp())
    )
    if timetable:
        tt_image = create_timetable_image(timetable, "timetable.png", handlers.timezone)
        image_links.append(tt_image)

    for event in events:
        result = client.get_rating_table(
            event_id_list=[event.pantheon_id], order="desc", order_by="rating"
        )
        if result.get("ok"):
            image_link = get_leaderboard_image(
                event=event, pantheon_data=result.get("players"), timezone=handlers.timezone
            )
            image_links.append(image_link)
            logger.info(f"Создана таблица {image_link} для события {event.event_id}")
        else:
            logger.info(
                f"Для события {event.event_id} ошибка {result.get('error', 'неизвестная ошибка')}"
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
    now = now_in_timezone(handlers.timezone)
    cutoff = now + datetime.timedelta(hours=15)
    cutoff = int(cutoff.timestamp())
    times = handlers.tables.get_all_relevant_table_times(
        right_cutoff=cutoff, left_cutoff=int(now.timestamp())
    )
    for time in times:
        if time.need_reminder == 0:
            continue
        message = (
            "Напоминание о назначенном времени:\n"
            f"{timestring_from_timestamp(time.time, day=True, weekday=True, timezone=handlers.timezone)}"
        )
        try:
            await context.bot.send_message(chat_id=time.table.chat_id, text=message)
            time.need_reminder = 0
        except Exception as e:
            logger.info(e)
    handlers.session_manager.session.commit()
