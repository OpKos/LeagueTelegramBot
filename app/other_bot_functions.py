import configparser
import json
import datetime
import logging
from logging.handlers import RotatingFileHandler

import pytz
from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from sqlalchemy_parser import SqlParser
from tenhou_parser import TenhouClient

from event_portal_update import event_portal_update
from seating_functions import create_seating
from seating_image import create_seating_image

with open("locales.json", "r", encoding="utf-8") as f:
    LOCALES = json.load(f)

config = configparser.ConfigParser()
config.read("config.ini")
lobby = config.get("Settings", "lobby")
db = SqlParser()
tenhou_client = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)
admins = [int(config.get("Admins", key)) for key in config["Admins"] if key.startswith("tg_id")]

logger = logging.getLogger()

def setup_logging():
    """Настраивает логирование в консоль и файл."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in admins


def tr(lang, key, **kwargs):
    template = LOCALES.get(key).get(lang)
    return template.format(**kwargs)


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Регистрирует нового игрока в системе.

    Args:
        update (Update): Объект Update от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
    """
    user = update.effective_user
    args = context.args
    assert update.effective_message
    assert user
    logger.info("User %s (%s) issued /register command with args: %s", user.username, user.id, args)

    if not args or len(args) != 1:
        logger.info("User %s (%s) used /register with invalid args: %s", user.username, user.id, args)
        await update.effective_message.reply_text(tr("en", "register_invalid_args"))
        return

    tenhou_name = args[0]

    # Проверяем, не зарегистрирован ли уже пользователь
    player = db.get_player(telegram_id=user.id)
    if player:
        lang = player.language
        old_name = player.tenhou_name
        if old_name == tenhou_name:
            await update.effective_message.reply_text(tr(lang, "already_registered", old=old_name, new=tenhou_name))
        else:
            db.update_tenhou_nick(p_id=player.p_id, tenhou_name=tenhou_name)
            await update.effective_message.reply_text(tr(lang, "nick_change", old=old_name, new=tenhou_name))
        logger.info("User %s (%s) already registered with Tenhou ID %s.", user.username, user.id, tenhou_name)
        return

    # Регистрируем нового игрока
    db.register_player(telegram_id=user.id, telegram_name=user.username, tenhou_id=tenhou_name)
    await update.effective_message.reply_text(
        tr("ru", "register_success") +
        "\n" + tr("en", "register_success") +
        "\nUse /set_language to change your language")
    logger.info("User %s (%s) registered with Tenhou ID %s.", user.username, user.id, tenhou_name)


async def start_game_with_players(context: ContextTypes.DEFAULT_TYPE, game_id: int):
    game = db.get_game(game_id)
    if not game:
        return (False, f"Игра {game_id} не найдена")

    # Проверяем, что стол видимый
    if not game.table.visible:
        return (False, f"Стол {game.table.table_id} скрыт")

    # Проверяем, готовы ли все игроки
    # not_ready_players = [p.irl_name for p in game.players if p.p_id not in ready_players]
    not_ready_players = []
    if not_ready_players:
        return (False, f"Не все игроки готовы: {', '.join(not_ready_players)}")

    # Запускаем игру в Tenhou
    player_nicks = [p.tenhou_name for p in game.players]
    result, missed_players, success = tenhou_client.start_game(player_nicks)  # pyright: ignore[reportGeneralTypeIssues]

    if success:
        db.set_game_status(game.game_id, 1)
        seat_winds_names = ["東", "南", "西", "北"]
        # Отправляем уведомление в группу
        text = f"Игра за столом {game.table.table_id} запущена:"
        for i, p in enumerate(game.players):
            text += f"\n{seat_winds_names[i]} {p.irl_name} ({p.tenhou_name})"
        await context.bot.send_message(
            chat_id="@kawaleague",
            text=text
        )

        logger.info(f"Игра за столом {game.table.table_id} успешно запущена")
        return (True, None)  # Возвращаем None в сообщении при успехе
    elif result == "MEMBER NOT FOUND":
        return (False, f"Игроки не найдены: {', '.join(missed_players)}")
    else:
        return (False, f"Не удалось запустить игру: {result}")


async def start_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает игру за указанным столом"""
    user = update.effective_user
    assert user
    assert update.effective_message

    logger.info(f"Пользователь {user.username} ({user.id}) вызвал /start_table с аргументами: {context.args}")

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /start_table <table_id>")
        return

    try:
        table_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("ID стола должен быть числом")
        return

    table = db.get_visible_table(table_id)
    if not table:
        await update.effective_message.reply_text(f"Стол {table_id} не найден")
        logger.info(f"Стол {table_id} не найден")
        return

    games = table.unfinished_games()
    if not games:
        await update.effective_message.reply_text(f"Нет неначатых игр за столом {table_id}")
        logger.info(f"Нет игр за столом {table_id}")
        return

    if len(games) > 1 and len(table.players()) > 4:
        await update.effective_message.reply_text(
            "Запуск игр для столов с >4 игроками доступен только через /start_game game_id.\n"
            "Используйте /table_info table_id для нахождения game_id нужной игры"
        )
        logger.info(f"Попытка запуска стола с >4 игроками через /start_table: {table_id}")
        return

    game = games[0]
    success, message = await start_game_with_players(context, game.game_id)

    if success:
        await update.effective_message.set_reaction("👍")
    else:
        assert message
        await update.effective_message.reply_text(message)
        logger.info(f"Ошибка запуска игры: {message}")


async def start_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает конкретную игру по ID (только для админов)"""
    user = update.effective_user
    assert user
    assert update.effective_message
    logger.info("User %s (%s) issued /start_game command with args: %s", user.username, user.id, context.args)
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /start_game <game_id>")
        return

    try:
        game_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("ID игры должен быть числом")
        return

    success, message = await start_game_with_players(context, game_id)

    if success:
        await update.effective_message.set_reaction("👍")
    elif message:
        await update.effective_message.reply_text(message)


async def next_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    logger.info("User %s (%s) issued /next_table command.", user.username, user.id)
    player = db.get_player(telegram_id=user.id)
    if not player:
        await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
        return
    lang = player.language
    if not db.set_target_tables(player.p_id, goal=1):
        await update.effective_message.reply_text(tr(lang, "next_table_fail"))
        return

    await update.effective_message.reply_text(tr(lang, "next_table_success"))

    for ep in player.player_events:
        nt = db.try_reveal(ep.event_id)
        while nt:
            await notify_table_revealed(context.bot, nt)
            nt = db.try_reveal(ep.event_id)


async def all_tables_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    logger.info("User %s (%s) issued /all_tables command.", user.username, user.id)
    player = db.get_player(telegram_id=user.id)
    if not player:
        await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
        return
    player.full_ready = 1
    db.session.commit()
    lang = player.language
    if not db.set_target_tables(player.p_id, full=True):
        await update.effective_message.reply_text(tr(lang, "all_tables_fail"))
        return

    await update.effective_message.reply_text(tr(lang, "all_tables_success"))

    for ep in player.player_events:
        if ep.event.started == 0:
            continue
        nt = db.try_reveal(ep.event_id)
        while nt:
            await notify_table_revealed(context.bot, nt)
            nt = db.try_reveal(ep.event_id)


async def notify_table_revealed(bot: Bot, table):
    player_names = [p.irl_name for p in table.players]
    message = (
            f"Раскрыт стол {table.name}!\n" +
            '\n'.join(player_names) + "\n"
    )
    await bot.send_message(chat_id="@kawaleague", text=message)


async def set_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет статус игры (только для администраторов)."""
    user = update.effective_user
    assert user
    assert update.effective_message

    if not context.args or len(context.args) != 3:
        await update.effective_message.reply_text(
            "Использование: /set_time <стол> <день> <время>\n"
            "День вводить без месяца, только само число.\n"
            "Время можно указывать как с минутами, так и без. При указании с минутами, разделитель не обязателен.\n"
            "Пример: 10 стол в 19:30 20 числа - /set_time 10 20 1930\n"
            "15 стол в 17:00 10 числа - /set_time 15 10 17"
        )
        return

    table_id, day, chosen_time = context.args
    table_id = int(table_id)
    table = db.get_visible_table(table_id)

    if not table:
        await update.effective_message.reply_text(f"Стол {table_id} не найден.")
        logger.info("Table %s not found.", table_id)
        return

    games = table.unfinished_games
    if not games:
        await update.effective_message.reply_text(f"Нет неначатых игр за столом {table_id}.")
        logger.info("No unstarted games at table %s.", table_id)
        return

    player = db.get_player(telegram_id=user.id)
    if player not in table.players:
        await update.effective_message.reply_text(f"Указывать время можно только за своим столом.")
        logger.info(f"{user.name} attempted using set_time with args {[context.args]}. Not found at table")
        return
    day = int(day)
    table_id = int(table_id)
    timezone = pytz.timezone("Europe/Moscow")
    now = datetime.datetime.now(tz=timezone)
    time_digits = ''.join(ch for ch in chosen_time if ch.isdigit())
    if len(time_digits) < 3:
        hour = int(time_digits)
        minute = 0
    else:
        hour = int(time_digits[:-2])
        minute = int(time_digits[-2:])
    month = now.month
    year = now.year
    if day < now.day:
        month += 1
    if month > 12:
        month -= 12
        year += 1
    try:
        prospective_start = timezone.localize(
            datetime.datetime(year=year, month=month, day=day, hour=hour, minute=minute))
    except ValueError:
        logger.info(
            f"{user.name} attempted using set_time with args {[context.args]}. Invalid time: {year}.{month}.{day} {hour}:{minute}")
        await update.effective_message.reply_text(f"Время не распознано {year}.{month}.{day} {hour}:{minute}")
        return
    db.set_table_time(table_id=table_id, timestamp=int(prospective_start.timestamp()))
    logger.info(f"{user.name} used set_time with args {[context.args]}. Time set: {year}.{month}.{day} {hour}:{minute}")
    await update.effective_message.reply_text(f"Время установлено: {prospective_start.strftime('%d.%m %H:%M')}")
    return


async def remove_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет статус игры (только для администраторов)."""
    user = update.effective_user
    assert user
    assert update.effective_message

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text(
            "Использование: /remove_time <стол>"
        )
        return

    table_id = context.args[0]
    table_id = int(table_id)
    table = db.get_visible_table(table_id)

    if not table:
        await update.effective_message.reply_text(f"Стол {table_id} не найден.")
        logger.info("Table %s not found.", table_id)
        return

    player = db.get_player(telegram_id=user.id)
    if player not in table.players and not is_admin(user.id):
        await update.effective_message.reply_text(f"Удалять время можно только за своим столом.")
        logger.info(f"{user.name} attempted using remove_time with args {[context.args]}. Not found at table")
        return
    db.set_table_time(table_id=table_id, timestamp=0)
    logger.info(f"{user.name} used remove_time with args {[context.args]}.")
    await update.effective_message.reply_text(f"Время удалено.")
    return


async def timetable_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    assert user
    assert update.effective_message

    logger.info("User %s (%s) issued /timetable command.", user.username, user.id)
    if update.effective_message.chat.type != "private":
        await update.effective_message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return

    now = datetime.datetime.now(tz=pytz.timezone("Europe/Moscow"))
    cutoff = now - datetime.timedelta(hours=3)
    tables = db.get_unfinished_visible_tables()
    tables.sort(key=lambda el: el.table_id)
    unknown_ids = [table.table_id for table in tables if not table.time or table.time < cutoff.timestamp()]
    known = [table for table in tables if table.time and table.time >= cutoff.timestamp()]
    known.sort(key=lambda el: el.time)
    known_str = "".join([table_string(i, explicit=True) for i in known])
    unknown_str = ", ".join(map(str, sorted(unknown_ids)))
    ans = known_str
    if unknown_str:
        ans += "Время неизвестно: " + unknown_str
    if ans == "":
        ans = "Игр нет"
    await update.effective_message.reply_text(ans, parse_mode=ParseMode.HTML)
    return


async def update_game_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет статус игры (только для администраторов)."""
    user = update.effective_user
    assert user
    assert update.effective_message

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    if not context.args or len(context.args) != 2:
        await update.effective_message.reply_text("Usage: /update_game_status <game_id> <status>")
        return

    game_id = int(context.args[0])
    status = int(context.args[1])

    if status not in [0, 1]:
        await update.effective_message.reply_text("Invalid status. Use '1' for started or '0' for not started.")
        return

    success = db.set_game_status(game_id, status)
    if success:
        status_text = "started" if status == "1" else "not started"
        await update.effective_message.reply_text(f"Статус игры с ID {game_id} успешно обновлен на '{status_text}'.")
        logger.info("Admin %s (%s) updated game status with game ID %s to %s.", user.username, user.id, game_id,
                    status_text)
    else:
        await update.effective_message.reply_text(f"Не удалось обновить статус игры с ID {game_id}.")
        logger.error("Admin %s (%s) failed to update game status with game ID %s to %s.", user.username, user.id,
                     game_id, status)


async def get_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет файл с логами администратору."""
    user = update.effective_user
    assert user
    assert update.effective_message

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    try:
        with open("bot.log", "rb") as log_file:
            await update.effective_message.reply_document(document=log_file)
        logger.info("Admin %s (%s) requested the log file.", user.username, user.id)
    except FileNotFoundError:
        await update.effective_message.reply_text("Файл с логами не найден.")
        logger.error("Log file not found for admin %s (%s).", user.username, user.id)
    except Exception as e:
        await update.effective_message.reply_text(f"Произошла ошибка при отправке логов: {e}")
        logger.error("Error sending log file to admin %s (%s): %s", user.username, user.id, e)


async def force_reveal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда раскрытия стола через стандартный метод"""
    user = update.effective_user
    assert user
    assert update.effective_message

    if not is_admin(user.id):
        await update.effective_message.reply_text("Только для админов")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /force_reveal <table_id>")
        return

    try:
        table_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("ID стола должен быть числом")
        return

    if db.reveal_table(table_id):
        table = db.get_table(table_id)
        assert table
        await notify_table_revealed(context.bot, table)
        await update.effective_message.reply_text(f"Стол {table_id} раскрыт")
    else:
        await update.effective_message.reply_text("Ошибка раскрытия стола")


def timestring_from_timestamp(timestamp: int, weekday=False, day=False) -> str:
    timezone = pytz.timezone("Europe/Moscow")
    res = ""
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    date = datetime.datetime.fromtimestamp(timestamp, tz=timezone)
    if weekday:
        res += weekdays[date.weekday()] + " "
    if day:
        res += f"{date.strftime('%d.%m')} "
    res += f"{date.strftime('%H:%M')}"
    return res


def table_string(table, mention: bool = False, explicit=True) -> str:
    ans = timestring_from_timestamp(table.time, weekday=explicit, day=explicit) + " - " + f"Стол {table.table_id}:\n"
    for i, player in enumerate(table.players):
        if mention:
            ans += player.clean_mention()
        else:
            ans += player.irl_name
        if i % 2 == 0:
            ans += ", "
        elif i < len(table.players) - 1:
            ans += ",\n"
        else:
            ans += ".\n\n"
    return ans


async def send_game_status_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    started, total = db.get_games_status()
    now = datetime.datetime.now()
    tommorow: datetime.datetime = now + datetime.timedelta(days=1)
    tables = db.get_unfinished_visible_tables()
    started, total = db.get_games_status()
    tables = [i for i in tables if i.time and i.time >= now.timestamp() and i.time < tommorow.timestamp()]
    tables.sort(key=lambda el: el.time)
    games = [table_string(table, mention=True, explicit=False) for table in tables]
    ans = f"Доброе утро, запущено игр: {started}/{total}"
    if games:
        ans += "\nСегодня играют:\n\n" + "".join(games)
    await context.bot.send_message(chat_id="@kawaleague", text=ans, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    assert user
    assert update.effective_message

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    await send_game_status_message(context)


async def start_status_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    assert user
    assert update.effective_message
    assert context.job_queue

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    chat_id = update.effective_message.chat_id
    tz = pytz.timezone("Europe/Moscow")
    callback_time = datetime.time(hour=10, minute=0, tzinfo=tz)
    context.job_queue.run_daily(send_game_status_message, time=callback_time, chat_id="@kawaleague",
                                name=str(chat_id))
    text = "Timer successfully set!"
    await update.effective_message.reply_text(text)


async def get_player_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Получает информацию об игроке
    """
    user = update.effective_user
    assert user
    assert update.effective_message

    if update.effective_message.chat.type != "private":
        await update.effective_message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return

    if not context.args:
        player = db.get_player(telegram_id=user.id)

    elif len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /player_info <telegram_name>")
        return
    else:
        telegram_name = context.args[0]
        if telegram_name[0] == "@":
            telegram_name = telegram_name[1:]
        player = db.get_player(telegram_name=telegram_name)

    if not player:
        await update.effective_message.reply_text("Пользователь не зарегистрирован.")
        return

    message = ""
    if is_admin(user.id):
        message += f"ID в базе: {player.p_id}\n" \
                   f"Telegram ID: {player.telegram_id}\n"

    message += f"Telegram хэндл: @{player.telegram_name}\n" \
               f"Tenhou ник: {player.tenhou_name}\n" \
               f"Имя: {player.irl_name}\n\n"

    for table in player.visible_tables():
        message += f"Стол {table.name}\n"
        for i in table.players():
            message += f"{i.irl_name} ({i.dirty_mention()})\n"
        if table.unfinished_games and table.time:
            message += f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}\n"
        message += f"Сыграно: {len(table.games) - len(table.unfinished_games())} из {len(table.games)} игр\n\n"

    if player.invisible_tables() and is_admin(user.id):
        ids = [i.name for i in player.invisible_tables()]
        message += f"Скрытые столы: {ids}\n\n"
    await update.effective_message.reply_text(message)
    logger.info("Person %s requested info for player %s", user.full_name, player.irl_name)


async def get_table_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Получает информацию о столе
    """
    user = update.effective_user
    assert user
    assert update.effective_message

    if update.effective_message.chat.type != "private":
        await update.effective_message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /table_info <table_id>")
        return

    table_id = int(context.args[0])
    table = db.get_table(table_id)
    if not table:
        await update.effective_message.reply_text("Стол не найден.")
        return
    if not table.visible and not is_admin(user.id):
        await update.effective_message.reply_text("Стол скрыт.")
        return

    message = f"Стол {table.table_id}\n" \
              f"{'Стол скрыт 🔒' if not table.visible else ''}\n"
    for i in table.players:
        message += f"{i.irl_name} ({i.dirty_mention()})\n"
    message += f"Сыграно: {len(table.games) - len(table.unfinished_games)} из {len(table.games)} игр\n"
    if table.time:
        message += f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}"
    message += "\n\n"

    games = table.games
    for game in games:
        message += f"ID игры: {game.game_id}\n" \
                   f"{'🟢 Запущена' if game.started else '🔴 Не запущена'}\n"
        for player in game.players:
            message += f"{player.irl_name}\n"
        message += f"\n"

    await update.effective_message.reply_text(message)
    logger.info("Person %s requested info for table %s", user.full_name, table.table_id)


async def lobby_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_message
    lobby = config.get("Settings", "lobby")
    await update.effective_message.reply_text(f"https://tenhou.net/3/?{lobby[:9]}")
    return


async def pantheon_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_message
    pantheon = config.get("Settings", "pantheon")
    await update.effective_message.reply_text(pantheon)
    return


async def reload_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to reload database session"""
    user = update.effective_user
    assert user
    assert update.effective_message
    if not is_admin(user.id):
        await update.effective_message.reply_text("🔒 Admin only command")
        return

    if db.reload_session():
        await update.effective_message.reply_text("🔄 Database session reloaded")
    else:
        await update.effective_message.reply_text("❌ Failed to reload session")


async def get_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет текущий файл настроек администратору."""
    user = update.effective_user
    assert user
    assert update.effective_message
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    with open("config.ini", "rb") as settings_file:
        await update.effective_message.reply_document(document=settings_file)
    logger.info("Admin %s (%s) requested the settings file.", user.username, user.id)


async def set_language(update, context):
    user_id = update.effective_user.id
    if not context.args or context.args[0] not in ("ru", "en"):
        await update.message.reply_text("Usage: /set_language ru|en")
        return

    lang = context.args[0]
    p_id = db.get_player(telegram_id=user_id).p_id

    if not p_id:
        await update.message.reply_text(tr(lang, "not_registered"))
        return

    db.set_language(p_id, lang)
    await update.message.reply_text(tr(lang, "language_set"))


async def update_event_players_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    assert user
    assert update.effective_message
    assert context.job_queue

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    logger.info("Admin %s (%s) updated players in events.", user.username, user.id)

    events = db.get_signup_events()

    for event in events:
        db.clear_event_players(event.event_id)
        res = event_portal_update(db, event)
        await update.effective_message.reply_text(f"Event {event.event_id}\n{res}")
        logger.info("Updated event %s", event.event_id)


async def create_seating_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    event = db.get_event(int(context.args[0]))
    logger.info("Admin %s (%s) created seating for event %s", user.username, user.id, event.event_id)
    create_seating(db, event)
    await update.effective_message.reply_text("Seating created")


async def reveal_new_tables(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    event = db.get_event(int(context.args[0]))
    new_min = int(context.args[1])
    new_max = int(context.args[2])
    logger.info("Admin %s (%s) revealed new tables with new_min = %s and new_max = %s", user.username, event.event_id, new_min, new_max)
    logger.info("Admin %s (%s) revealed new tables", user.username, event.event_id)
    event.global_maximum = new_max
    nt = db.try_reveal(event.event_id, cache=True)
    while nt:
        nt = db.try_reveal(event.event_id, cache=True)
    event.global_minimum = new_min
    nt = db.try_reveal(event.event_id, cache=True)
    while nt:
        nt = db.try_reveal(event.event_id, cache=True)
    cached = db.get_event_cached_tables(event_id=event.event_id)
    await update.effective_message.reply_text(f"Event {event.event_id} cached tables\n{' '.join(t.name for t in cached)}")


async def seating_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    event = db.get_event(int(context.args[0]))
    logger.info("Admin %s (%s) requested image for event %s", user.username, user.id, event.event_id)
    create_seating_image(db, event)
    with open("seating.png", "rb") as image_file:
        await update.effective_message.reply_document(document=image_file)

