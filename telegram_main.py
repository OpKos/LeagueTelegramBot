# telegram_main.py
import os
import logging
import configparser
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from tenhou_parser import TenhouClient
from sqlite_parser import SqliteParser

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

db = SqliteParser(db_path)
c = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)

# Загрузка ID администраторов
admins = [int(config.get("Admins", key)) for key in config["Admins"] if key.startswith("tg_id")]

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in admins

# Глобальная переменная для хранения ID готовых игроков
ready_players = set()

def restart_services():
    """Перезапускает SqliteParser и TenhouClient с новыми настройками."""
    global db, c

    # Перезагружаем конфигурацию
    config.read("config.ini")

    # Обновляем путь к базе данных и параметры лобби
    db_path = config.get("Settings", "database")
    lobby = config.get("Settings", "lobby")

    # Перезапускаем SqliteParser
    db = SqliteParser(db_path)

    # Перезапускаем TenhouClient
    c = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение при команде /help."""
    user = update.effective_user
    logger.info("User %s (%s) issued /help command.", user.username, user.id)
    await update.message.reply_text("Help!")

async def my_games_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Получает и отображает игры пользователя, сгруппированные по столам, только для текущей стадии турнира.

    Args:
        update (Update): Объект Update от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
    """
    user_id = update.effective_user.id
    user = update.effective_user
    logger.info("User %s (%s) issued /my_games command.", user.username, user.id)

    if update.message.chat.type != "private":
        await update.message.reply_text("Эта команда доступна только в личных сообщениях с ботом.")
        return
    
    p_id = db.get_player_id_by_tg_id(user_id)
    
    if not p_id:
        await update.message.reply_text("Вы не зарегистрированы в системе.")
        logger.info("User %s (%s) is not registered in the system.", user.username, user.id)
        return
    
    # Получаем текущую стадию турнира из конфигурации
    current_stage = config.get("Settings", "stage", fallback="1")
    
    # Получаем игры только для текущей стадии турнира
    tables = db.get_player_games_grouped_by_table(p_id, current_stage)
    if not tables:
        await update.message.reply_text("У вас нет активных игр на текущей стадии турнира.")
        logger.info("User %s (%s) has no active games on the current stage.", user.username, user.id)
        return
    
    message = "Ваши игры на текущей стадии турнира:\n"
    for table_id, table_info in tables.items():
        message += f"Стол {table_id}:\n"
        for name in table_info['players']:
            if name:
                message += f"Игрок: @{name[0]} ({name[1]})\n"
        started_games = table_info['started_games']
        total_games = table_info['total_games']
        message += f"Сыграно игр: {started_games} из {total_games}\n\n"
    
    await update.message.reply_text(message)
    logger.info("User %s (%s) games: %s", user.username, user.id, message)

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Регистрирует нового игрока в системе.

    Args:
        update (Update): Объект Update от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
    """
    user = update.effective_user
    args = context.args

    if len(args) != 1:
        await update.message.reply_text("Использование: /register <tenhou_id>")
        return

    tenhou_id = args[0]

    # Проверяем, не зарегистрирован ли уже пользователь
    p_id = db.get_player_id_by_tg_id(user.id)
    if p_id:
        await update.message.reply_text("Вы уже зарегистрированы в системе.")
        return

    # Регистрируем нового игрока
    db.register_player(user.id, user.full_name, tenhou_id)
    await update.message.reply_text("Вы успешно зарегистрированы!")
    logger.info("User %s (%s) registered with Tenhou ID %s.", user.username, user.id, tenhou_id)

async def ready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмечает пользователя как готового к игре."""
    user = update.effective_user
    tenhou_name = db.get_tenhou_name_by_pid(db.get_player_id_by_tg_id(user.id))

    if not tenhou_name:
        logger.warning("Attempted action by unregistered user: %s (%s)", update.effective_user.username, update.effective_user.id)
        await update.message.reply_text("Вы не зарегистрированы.")
        return

    ready_players.add(tenhou_name)
    await update.message.reply_text("Вы готовы к игре!")
    logger.info("User %s (%s) marked as ready.", tenhou_name, user.full_name)

async def unready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Снимает отметку готовности пользователя."""
    user = update.effective_user
    tenhou_name = db.get_tenhou_name_by_pid(db.get_player_id_by_tg_id(user.id))

    
    if not tenhou_name:
        await update.message.reply_text("Вы не зарегистрированы.")
        return

    if tenhou_name in ready_players:
        ready_players.remove(tenhou_name)
        logger.info("User %s (%s) unmarked as ready.", tenhou_name, user.full_name)
        await update.message.reply_text("Вы больше не готовы к игре.")
    else:
        logger.info("User %s (%s) was not marked as ready.", tenhou_name, user.full_name)
        await update.message.reply_text("Вы не были помечены как готовые.")

async def start_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает игру за указанным столом, если все игроки готовы."""
    user = update.effective_user
    logger.info("User %s (%s) issued /start_table command with args: %s", user.username, user.id, context.args)

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /start_table <table_id>")
        return

    table_id = context.args[0]

    # Получаем неначатые игры за указанным столом
    games = db.get_unstarted_games_by_table_id(table_id)
    if not games:
        await update.message.reply_text(f"Нет неначатых игр за столом {table_id}.")
        logger.info("No unstarted games at table %s.", table_id)
        return

    # Проверяем, готовы ли все игроки
    game = games[0]
    p1, p2, p3, p4, game_id = game
    player_ids = [p1, p2, p3, p4]

    player_names = [
        db.get_tenhou_name_by_pid(p1),
        db.get_tenhou_name_by_pid(p2),
        db.get_tenhou_name_by_pid(p3),
        db.get_tenhou_name_by_pid(p4)
    ]
    
    not_ready_players = [player_nick for player_nick in player_names if player_nick not in ready_players]
    if not_ready_players:
        await update.message.reply_text(f"Не все игроки за столом {table_id} готовы: {', '.join(not_ready_players)}")
        logger.info("Not all players at table %s are ready: %s", table_id, not_ready_players)
        print(ready_players)
        return

    result, missed_players, success = c.start_game(player_names)
    if success:
        await update.message.reply_text(f"Игра за столом {table_id} начата!")
        logger.info("Game at table %s started with players: %s", table_id, player_names)

        # Обновляем статус игры в базе данных
        db.update_game_status(game_id, 1)
    elif result == "MEMBER NOT FOUND":
        await update.message.reply_text(f"Игра не может быть начата. Не найдены игроки: {', '.join(missed_players)}")
        logger.info("Game at table %s could not be started. Members not found: %s", table_id, missed_players)
    else:
        await update.message.reply_text(f"Не удалось начать игру за столом {table_id}.")
        logger.error("Failed to start game at table %s. Result: %s", table_id, result)

async def update_game_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновляет статус игры (только для администраторов)."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /update_game_status <game_id> <status>")
        return

    game_id = context.args[0]
    status = context.args[1]

    if status not in ["1", "0"]:
        await update.message.reply_text("Invalid status. Use '1' for started or '0' for not started.")
        return

    success = db.update_game_status(game_id, int(status))
    if success:
        status_text = "started" if status == "1" else "not started"
        await update.message.reply_text(f"Статус игры с ID {game_id} успешно обновлен на '{status_text}'.")
        logger.info("Admin %s (%s) updated game status with game ID %s to %s.", user.username, user.id, game_id, status_text)
    else:
        await update.message.reply_text(f"Не удалось обновить статус игры с ID {game_id}.")
        logger.error("Admin %s (%s) failed to update game status with game ID %s to %s.", user.username, user.id, game_id, status)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создает резервную копию базы данных (только для администраторов)."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    db.backup_database()
    await update.message.reply_text("Резервная копия базы данных успешно создана.")
    logger.info("Admin %s (%s) created a database backup.", user.username, user.id)

async def get_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет файл с логами администратору."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    try:
        with open("bot.log", "rb") as log_file:
            await update.message.reply_document(document=log_file)
        logger.info("Admin %s (%s) requested the log file.", user.username, user.id)
    except FileNotFoundError:
        await update.message.reply_text("Файл с логами не найден.")
        logger.error("Log file not found for admin %s (%s).", user.username, user.id)
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка при отправке логов: {e}")
        logger.error("Error sending log file to admin %s (%s): %s", user.username, user.id, e)

async def force_ready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда для пометки игрока как готового."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /force_ready <telegram_id>")
        return

    telegram_id = int(context.args[0])
    tenhou_name = db.get_tenhou_name_by_pid(db.get_player_id_by_tg_id(telegram_id))

    if not tenhou_name:
        await update.message.reply_text("Пользователь не зарегистрирован.")
        return

    ready_players.add(tenhou_name)
    await update.message.reply_text(f"Игрок {tenhou_name} помечен как готов.")

async def force_unready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админская команда для снятия готовности игрока."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /force_unready <telegram_id>")
        return

    telegram_id = int(context.args[0])
    tenhou_name = db.get_tenhou_name_by_pid(db.get_player_id_by_tg_id(telegram_id))

    if not tenhou_name:
        await update.message.reply_text("Пользователь не зарегистрирован.")
        return

    if tenhou_name in ready_players:
        ready_players.remove(tenhou_name)
        await update.message.reply_text(f"Игрок {tenhou_name} снят с готовности.")
    else:
        await update.message.reply_text(f"Игрок {tenhou_name} не был помечен как готов.")
        
# Глобальные переменные для режима ожидания
awaiting_db_upload = False
awaiting_settings_upload = False

async def get_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет текущую базу данных администратору."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    with open(db.db_path, "rb") as db_file:
        await update.message.reply_document(document=db_file)
    logger.info("Admin %s (%s) requested the database.", user.username, user.id)

async def set_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Загружает новую базу данных (только для администраторов)."""
    global awaiting_db_upload

    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    awaiting_db_upload = True
    await update.message.reply_text("Пожалуйста, загрузите файл базы данных.")
    logger.info("Admin %s (%s) initiated database upload.", user.username, user.id)

async def get_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет текущий файл настроек администратору."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    with open("config.ini", "rb") as settings_file:
        await update.message.reply_document(document=settings_file)
    logger.info("Admin %s (%s) requested the settings file.", user.username, user.id)

async def set_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Загружает новый файл настроек и перезапускает сервисы (только для администраторов)."""
    global awaiting_settings_upload

    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    awaiting_settings_upload = True
    await update.message.reply_text("Пожалуйста, загрузите файл настроек.")
    logger.info("Admin %s (%s) initiated settings upload.", user.username, user.id)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает загруженные документы (базу данных или настройки)."""
    global awaiting_db_upload, awaiting_settings_upload

    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    document = update.message.document
    file_path = await document.get_file()

    if awaiting_db_upload:
        new_db_path = f"{db.db_path}.new"
        await file_path.download_to_drive(custom_path=new_db_path)

        # Создаем резервную копию текущей базы данных
        db.backup_database()

        # Заменяем текущую базу данных новой
        os.replace(new_db_path, db.db_path)
        awaiting_db_upload = False
        await update.message.reply_text("Новая база данных успешно загружена.")
        logger.info("Admin %s (%s) uploaded a new database.", user.username, user.id)

    elif awaiting_settings_upload:
        new_settings_path = "config.ini.new"
        await file_path.download_to_drive(custom_path=new_settings_path)

        # Заменяем текущий файл настроек новым
        os.replace(new_settings_path, "config.ini")

        # Перезагружаем конфигурацию
        config.read("config.ini")
        
        restart_services()

        awaiting_settings_upload = False
        await update.message.reply_text("Новый файл настроек успешно загружен и конфигурация перезагружена.")
        logger.info("Admin %s (%s) uploaded a new settings file and reloaded the configuration.", user.username, user.id)
    else:
        await update.message.reply_text("Неожиданно получен файл. Пожалуйста, используйте команду для загрузки перед отправкой файла.")
        logger.info("Unexpected file received from user %s (%s).", user.username, user.id)

def main() -> None:
    """Запускает бота."""
    with open("token.txt", "r") as file:
        token = file.read().strip()
    
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("my_games", my_games_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("ready", ready_command))
    application.add_handler(CommandHandler("unready", unready_command))
    application.add_handler(CommandHandler("start_table", start_table_command))
    application.add_handler(CommandHandler("update_game_status", update_game_status_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("get_db", get_db_command))
    application.add_handler(CommandHandler("set_db", set_db_command))
    application.add_handler(CommandHandler("get_settings", get_settings_command))
    application.add_handler(CommandHandler("set_settings", set_settings_command))
    application.add_handler(CommandHandler("get_logs", get_logs_command))
    application.add_handler(CommandHandler("force_ready", force_ready_command))
    application.add_handler(CommandHandler("force_unready", force_unready_command))
    application.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()