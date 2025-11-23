#!/usr/bin/env python3
import configparser
import datetime
import logging
import os
from logging.handlers import RotatingFileHandler

import pytz
from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from sqlalchemy_parser import SqlParser
from tenhou_parser import TenhouClient

# Настройка логирования
def setup_logging():
    """Настраивает логирование в консоль и файл."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Логирование в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Логирование в файл
    file_handler = RotatingFileHandler("bot.log", maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Вызываем настройку логирования при запуске
setup_logging()

logger = logging.getLogger(__name__)

# Загрузка конфигурации
config = configparser.ConfigParser()
config.read("config.ini")

db_path = config.get("Settings", "database")
lobby = config.get("Settings", "lobby")

db = SqlParser()
tenhou_client = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)

# Загрузка ID администраторов
admins = [int(config.get("Admins", key)) for key in config["Admins"] if key.startswith("tg_id")]

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in admins

# Глобальная переменная для хранения ID готовых игроков
ready_players = set()

def restart_services():
    """Перезапускает SqlParser и TenhouClient с новыми настройками."""
    global db, tenhou_client
    logger.info("Перезапуск сервисов...")
    # Перезагружаем конфигурацию
    config.read("config.ini")

    # Обновляем параметры лобби
    lobby = config.get("Settings", "lobby")

    # Перезапускаем SqlParser
    db = SqlParser()

    # Перезапускаем TenhouClient
    tenhou_client = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)

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
        await update.effective_message.reply_text("Использование: /register <tenhou_id>")
        return

    tenhou_name = args[0]

    # Проверяем, не зарегистрирован ли уже пользователь
    player = db.get_player(telegram_id=user.id)
    if player:
        old_name = player.tenhou_name
        if old_name == tenhou_name:
            await update.effective_message.reply_text("Вы уже зарегистрированы в системе.")
        else:
            db.update_tenhou_nick(p_id=player.p_id, tenhou_name=tenhou_name)
            await update.effective_message.reply_text(f"Ник изменён с {old_name} на {tenhou_name}.")
        logger.info("User %s (%s) already registered with Tenhou ID %s.", user.username, user.id, tenhou_name)
        return

    # Регистрируем нового игрока
    db.register_player(telegram_id=user.id, telegram_name=user.username, tenhou_id=tenhou_name)
    await update.effective_message.reply_text("Вы успешно зарегистрированы!")
    logger.info("User %s (%s) registered with Tenhou ID %s.", user.username, user.id, tenhou_name)

async def ready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмечает пользователя как готового к игре."""
    user = update.effective_user
    assert user
    assert update.effective_message
    logger.info("User %s (%s) issued /ready command.", user.username, user.id)
    player = db.get_player(telegram_id=user.id)
    
    if not player:
        logger.warning("Attempted action by unregistered user: %s (%s)", user.full_name, user.id)
        await update.effective_message.reply_text("Вы не зарегистрированы.")
        return

    ready_players.add(player.p_id)
    await update.effective_message.set_reaction("👍")
    logger.info("User %s (%s) marked as ready.", player.p_id, user.full_name)

async def unready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Снимает отметку готовности пользователя."""
    user = update.effective_user
    assert user
    assert update.effective_message
    logger.info("User %s (%s) issued /unready command.", user.username, user.id)
    player = db.get_player(telegram_id=user.id)
    
    if not player:
        await update.effective_message.reply_text("Вы не зарегистрированы.")
        return

    if player.p_id in ready_players:
        ready_players.remove(player.p_id)
        logger.info("User %s (%s) unmarked as ready.", player.p_id, user.full_name)
        await update.effective_message.set_reaction("👍")
    else:
        logger.info("User %s (%s) was not marked as ready.", player.p_id, user.full_name)
        await update.effective_message.reply_text("Вы не были помечены как готовые.")

async def start_game_with_players(context: ContextTypes.DEFAULT_TYPE, game_id: int):
    """Общая функция для запуска игры по game_id с проверкой видимости стола"""
    game = db.get_game(game_id)
    if not game:
        return (False, f"Игра {game_id} не найдена")
    
    # Проверяем, что стол видимый
    if not game.table.visible:
        return (False, f"Стол {game.table.table_id} скрыт")
    
    # Проверяем, готовы ли все игроки
    not_ready_players = [p.irl_name for p in game.players if p.p_id not in ready_players]
    if not_ready_players:
        return (False, f"Не все игроки готовы: {', '.join(not_ready_players)}")

    # Запускаем игру в Tenhou
    player_nicks = [p.tenhou_name for p in game.players]
    result, missed_players, success = tenhou_client.start_game(player_nicks) # pyright: ignore[reportGeneralTypeIssues]
    
    if success:
        db.set_game_status(game.game_id, 1)
        seat_winds_names = ["東", "南", "西", "北"]
        # Отправляем уведомление в группу
        text=f"Игра за столом {game.table.table_id} запущена:"
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

    games = table.unfinished_games
    if not games:
        await update.effective_message.reply_text(f"Нет неначатых игр за столом {table_id}")
        logger.info(f"Нет игр за столом {table_id}")
        return

    # Проверка для столов с более чем 4 игроками
    if len(games) > 1 and len(table.players) > 4:
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
    """Помечает игрока как готового к следующему столу"""
    user = update.effective_user
    if not user or not update.effective_message:
        return
    logger.info("User %s (%s) issued /next_table command.", user.username, user.id)
    player = db.get_player(telegram_id=user.id)
    if not player:
        await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
        return
    if not context.args:
        goal = 1
    elif len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /next_table <amount>")
        return
    else:
        goal = int(context.args[0])
    
    if goal < 0:
        await update.effective_message.reply_text("Отрицательные значения не принимаются.")
        return
    
    if not player.invisible_tables:
        await update.effective_message.reply_text("У вас нет скрытых столов.")
        return
    
    # Помечаем игрока как готового
    if not db.set_target_tables(player.p_id, goal=goal):
        await update.effective_message.reply_text("Ошибка обновления статуса.")
        return

    await update.effective_message.reply_text(f"Принято, целевое число столов: {player.target_tables}.")

    # Ищем стол для раскрытия
    tables_to_check = [t for t in player.all_tables if not t.visible]
    
    for table in tables_to_check:
        if db.check_table_reveal_ready(table.table_id):
            if db.reveal_table(table.table_id):
                await notify_table_revealed(context.bot, table)
            break

async def notify_table_revealed(bot: Bot, table, additional_info=""):
    """Уведомляет о раскрытии стола с порядком"""
    player_names = [p.irl_name for p in table.players]
    message = (
        f"Раскрыт стол {table.table_id}!\n"+
        '\n'.join(player_names)+"\n"
    )
    
    await bot.send_message(chat_id="@kawaleague", text=message)
    # Персональные уведомления
    for p in table.players:
        if p.telegram_id:
            try:
                await bot.send_message(
                    chat_id=p.telegram_id,
                    text=message
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления {p.irl_name}: {e}")
        
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
        prospective_start = timezone.localize(datetime.datetime(year=year, month=month, day=day, hour=hour, minute=minute))
    except ValueError:
        logger.info(f"{user.name} attempted using set_time with args {[context.args]}. Invalid time: {year}.{month}.{day} {hour}:{minute}")
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
    tables.sort(key = lambda el: el.table_id)
    unknown_ids = [table.table_id for table in tables if not table.time or table.time < cutoff.timestamp()]
    known = [table for table in tables if table.time and table.time >= cutoff.timestamp()]
    known.sort(key=lambda el: el.time)
    known_str = "".join([table_string(i, explicit=True) for i in known])
    unknown_str = ", ".join(map(str, sorted(unknown_ids)))
    ans = known_str
    if unknown_str:
        ans += "Время неизвестно: "+unknown_str
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
        logger.info("Admin %s (%s) updated game status with game ID %s to %s.", user.username, user.id, game_id, status_text)
    else:
        await update.effective_message.reply_text(f"Не удалось обновить статус игры с ID {game_id}.")
        logger.error("Admin %s (%s) failed to update game status with game ID %s to %s.", user.username, user.id, game_id, status)

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

async def force_ready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда для пометки игрока как готового."""
    user = update.effective_user
    assert user
    assert update.effective_message
    
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /force_ready <telegram_name>")
        return

    telegram_name = context.args[0]
    if telegram_name[0] == "@":
        telegram_name = telegram_name[1:]
    player = db.get_player(telegram_name=telegram_name)

    if not player:
        await update.effective_message.reply_text("Пользователь не зарегистрирован.")
        return

    ready_players.add(player.p_id)
    await update.effective_message.reply_text(f"Игрок {player.irl_name} помечен как готовый.")

async def force_unready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда для снятия готовности игрока."""
    user = update.effective_user
    assert user
    assert update.effective_message
    
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text("Использование: /force_unready <telegram_name>")
        return

    telegram_name = context.args[0]
    if telegram_name[0] == "@":
        telegram_name = telegram_name[1:]
    player = db.get_player(telegram_name=telegram_name)

    if not player:
        await update.effective_message.reply_text("Пользователь не зарегистрирован.")
        return

    if player.p_id in ready_players:
        ready_players.remove(player.p_id)
        await update.effective_message.reply_text(f"Игрок {player.irl_name} снят с готовности.")
    else:
        await update.effective_message.reply_text(f"Игрок {player.irl_name} не был помечен как готов.")
        

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
        await notify_table_revealed(context.bot, table, "Админ раскрыл стол")
        await update.effective_message.reply_text(f"Стол {table_id} раскрыт")
    else:
        await update.effective_message.reply_text("Ошибка раскрытия стола")

async def force_next_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда установки готовности через стандартный метод"""
    user = update.effective_user
    assert user
    assert update.effective_message
    
    if not is_admin(user.id):
        await update.effective_message.reply_text("Только для админов")
        return

    if not context.args or len(context.args) != 2:
        await update.effective_message.reply_text("Использование: /force_next <telegram_name> <amount>")
        return

    player = db.get_player(telegram_name=context.args[0])
    if not player:
        await update.effective_message.reply_text("Игрок не найден")
        return
    goal = int(context.args[1])
    if db.set_target_tables(player.p_id, goal=goal):
        await update.effective_message.reply_text(f"Игрок @{context.args[0]} готов к следующему столу")
    else:
        await update.effective_message.reply_text("Ошибка обновления статуса")

def timestring_from_timestamp(timestamp: int, weekday=False, day=False) -> str:
    timezone = pytz.timezone("Europe/Moscow")
    res = ""
    weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    date = datetime.datetime.fromtimestamp(timestamp, tz=timezone)
    if weekday:
        res += weekdays[date.weekday()]+" "
    if day:
        res += f"{date.strftime('%d.%m')} "
    res += f"{date.strftime('%H:%M')}"
    return res

def table_string(table, mention: bool = False, explicit = True) -> str:
    ans = timestring_from_timestamp(table.time, weekday=explicit, day=explicit)+" - "+f"Стол {table.table_id}:\n"
    for i, player in enumerate(table.players):
        if mention:
            ans += player.clean_mention()
        else:
            ans += player.irl_name
        if i%2 == 0:
            ans += ", "
        elif i < len(table.players)-1:
            ans += ",\n"
        else:
            ans += ".\n\n"
    return ans

async def send_game_status_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    started, total = db.get_games_status()
    now = datetime.datetime.now()
    tommorow:datetime.datetime = now + datetime.timedelta(days=1)
    tables = db.get_unfinished_visible_tables()
    started, total = db.get_games_status()
    tables = [i for i in tables if i.time and i.time >= now.timestamp() and i.time < tommorow.timestamp()]
    tables.sort(key=lambda el: el.time)
    games = [table_string(table, mention=True, explicit=False) for table in tables]
    ans = f"Доброе утро, запущено игр: {started}/{total}"
    if games:
        ans += "\nСегодня играют:\n\n"+"".join(games)
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
    context.job_queue.run_daily(send_game_status_message, time=callback_time, chat_id="@kawaleague", name=str(chat_id)) # pyright: ignore[reportArgumentType]
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
        player = player = db.get_player(telegram_id=user.id)
    
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
        message += f"ID в базе: {player.p_id}\n"\
              f"Telegram ID: {player.telegram_id}\n"\
              f"Таргет столов: {player.target_tables}\n"
    
    
    message += f"Telegram хэндл: @{player.telegram_name}\n"\
              f"Tenhou ник: {player.tenhou_name}\n"\
              f"Имя: {player.irl_name}\n\n"

    for table in player.visible_tables:
        message += f"Стол {table.table_id}\n"
        for i in table.players:
            message += f"{i.irl_name} ({i.dirty_mention()})\n"
        if table.unfinished_games and table.time:
            message += f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}\n"
        message += f"Сыграно: {len(table.games)-len(table.unfinished_games)} из {len(table.games)} игр\n\n"
    
    if player.invisible_tables and is_admin(user.id):
        ids = [i.table_id for i in player.invisible_tables]
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

    message = f"Стол {table.table_id}\n"\
              f"{'Стол скрыт 🔒' if not table.visible else ''}\n"
    for i in table.players:
        message += f"{i.irl_name} ({i.dirty_mention()})\n"
    message += f"Сыграно: {len(table.games) - len(table.unfinished_games)} из {len(table.games)} игр\n"
    if table.time:
        message += f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}"
    message += "\n\n"
    
    games = table.games
    for game in games:
        message+=f"ID игры: {game.game_id}\n"\
                 f"{'🟢 Запущена' if game.started else '🔴 Не запущена'}\n"
        for player in game.players:
            message+=f"{player.irl_name}\n"
        message+=f"\n"
    
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

# Глобальные переменные для режима ожидания
awaiting_settings_upload = False

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

async def set_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Загружает новый файл настроек и перезапускает сервисы (только для администраторов)."""
    global awaiting_settings_upload

    user = update.effective_user
    assert user
    assert update.effective_message
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    awaiting_settings_upload = True
    await update.effective_message.reply_text("Пожалуйста, загрузите файл настроек.")
    logger.info("Admin %s (%s) initiated settings upload.", user.username, user.id)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает загруженные документы (базу данных или настройки)."""
    global awaiting_db_upload, awaiting_settings_upload

    user = update.effective_user
    assert user
    assert update.effective_message
    assert update.effective_message.document
    
    if not is_admin(user.id):
        await update.effective_message.reply_text("Эта команда доступна только администраторам.")
        return

    document = update.effective_message.document
    file_path = await document.get_file()

    if awaiting_settings_upload:
        new_settings_path = "config.ini.new"
        await file_path.download_to_drive(custom_path=new_settings_path)

        # Заменяем текущий файл настроек новым
        os.replace(new_settings_path, "config.ini")

        # Перезагружаем конфигурацию
        config.read("config.ini")
        
        restart_services()

        awaiting_settings_upload = False
        await update.effective_message.reply_text("Новый файл настроек успешно загружен и конфигурация перезагружена.")
        logger.info("Admin %s (%s) uploaded a new settings file and reloaded the configuration.", user.username, user.id)
    else:
        await update.effective_message.reply_text("Неожиданно получен файл. Пожалуйста, используйте команду для загрузки перед отправкой файла.")
        logger.info("Unexpected file received from user %s (%s).", user.username, user.id)

def main() -> None:
    """Запускает бота."""
    with open("token.txt", "r") as file:
        token = file.read().strip()
    
    application = Application.builder().token(token).write_timeout(30).read_timeout(30).connect_timeout(300).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("ready", ready_command))
    application.add_handler(CommandHandler("unready", unready_command))
    application.add_handler(CommandHandler("start_table", start_table_command))
    application.add_handler(CommandHandler("start_game", start_game_command))
    application.add_handler(CommandHandler("next_table", next_table_command))
    application.add_handler(CommandHandler("update_game_status", update_game_status_command))
    application.add_handler(CommandHandler("reload_db", reload_session_command))
    application.add_handler(CommandHandler("get_settings", get_settings_command))
    application.add_handler(CommandHandler("set_settings", set_settings_command))
    application.add_handler(CommandHandler("get_logs", get_logs_command))
    application.add_handler(CommandHandler("force_ready", force_ready_command))
    application.add_handler(CommandHandler("force_unready", force_unready_command))
    application.add_handler(CommandHandler("force_reveal", force_reveal_command))
    application.add_handler(CommandHandler("force_next", force_next_command))
    application.add_handler(CommandHandler(["player_info", "my_games"], get_player_info_command))
    application.add_handler(CommandHandler("table_info", get_table_info_command))
    application.add_handler(CommandHandler("start_status_message", start_status_message_command))
    application.add_handler(CommandHandler("set_time", set_time_command))
    application.add_handler(CommandHandler("remove_time", remove_time_command))
    application.add_handler(CommandHandler("timetable", timetable_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("lobby", lobby_command))
    application.add_handler(CommandHandler("pantheon", pantheon_command))
    
    
    
    application.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
