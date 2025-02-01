# telegram_main.py
import os
import logging
import configparser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from tenhou_parser import TenhouClient
from sqlite_parser import SqliteParser

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

# Load configuration
config = configparser.ConfigParser()
config.read("config.ini")

db_path = config.get("Settings", "database", fallback="season1.db")
lobby = config.get("Settings", "lobby", fallback="C1053882869114720")

db = SqliteParser(db_path)
c = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)


# Load admin IDs
admins = [int(config.get("Admins", key)) for key in config["Admins"] if key.startswith("tg_id")]

# Check if the user is an admin
def is_admin(user_id: int) -> bool:
    return user_id in admins

def restart_services():
    """
    Перезапускает SqliteParser и TenhouClient с новыми настройками.
    """
    global db, c

    # Перезагружаем конфигурацию
    config.read("config.ini")

    # Обновляем путь к базе данных и лобби
    db_path = config.get("Settings", "database", fallback="season1.db")
    lobby = config.get("Settings", "lobby", fallback="C1053882869114720")

    # Перезапускаем SqliteParser
    db = SqliteParser(db_path)

    # Перезапускаем TenhouClient
    c = TenhouClient(lobby=lobby, game_type="0009", is_enable=True)


# Глобальная переменная для хранения id готовых игроков
ready_players = set()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    user = update.effective_user
    logger.info("User %s (%s) issued /help command.", user.username, user.id)
    await update.message.reply_text("Help!")

async def my_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch and display a user's games grouped by table with Telegram names and real names."""
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
    
    tables = db.get_player_games_grouped_by_table(p_id)
    if not tables:
        await update.message.reply_text("У вас нет активных игр.")
        logger.info("User %s (%s) has no active games.", user.username, user.id)
        return
    
    message = "Ваши игры:\n"
    for table_id, table_info in tables.items():
        players = ", ".join([f"@{name[0]} ({name[1]})" for name in table_info['players'] if name])
        started_games = table_info['started_games']
        total_games = table_info['total_games']
        message += (
            f"Стол {table_id}:\n"
            f"Игроки: {players}\n"
            f"Сыграно игр: {started_games} из {total_games}\n\n"
        )
    
    await update.message.reply_text(message)
    logger.info("User %s (%s) games: %s", user.username, user.id, message)

async def ready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marks the user as ready."""
    user_id = update.effective_user.id
    user = update.effective_user
    ready_players.add(user_id)
    await update.message.reply_text("Вы готовы к игре!")
    logger.info("User %s (%s) marked as ready.", user.username, user.id)

async def unready_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marks the user as not ready."""
    user_id = update.effective_user.id
    user = update.effective_user
    if user_id in ready_players:
        ready_players.remove(user_id)
        await update.message.reply_text("Вы больше не готовы к игре.")
        logger.info("User %s (%s) marked as not ready.", user.username, user.id)
    else:
        await update.message.reply_text("Вы не были в списке готовых игроков.")
        logger.info("User %s (%s) was not in the list of ready players.", user.username, user.id)

async def start_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a game at a specific table if all players are ready."""
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

    # Проверяем, готовы ли все игроки сразу
    game = games[0]
    p1, p2, p3, p4, game_id = game
    player_ids = [p1, p2, p3, p4]

    not_ready_players = [player_id for player_id in player_ids if player_id not in ready_players]
    if not_ready_players:
        not_ready_names = [db.get_irl_name_by_pid(player_id) for player_id in not_ready_players]
        await update.message.reply_text(f"Не все игроки за столом {table_id} готовы: {', '.join(not_ready_names)}")
        logger.info("Not all players at table %s are ready: %s", table_id, not_ready_names)
        return

    # Используем ники Tenhou при вызове TenhouClient
    player_names = [
        db.get_tenhou_name_by_pid(p1),
        db.get_tenhou_name_by_pid(p2),
        db.get_tenhou_name_by_pid(p3),
        db.get_tenhou_name_by_pid(p4)
    ]

    result, missed_players, success = c.start_game(player_names)
    if success:
        await update.message.reply_text(f"Игра за столом {table_id} начата!")
        logger.info("Game at table %s started with players: %s", table_id, player_names)

        # Обновляем статус игры в базе данных
        db.update_game_status(game_id, "started")
    elif result == "MEMBER NOT FOUND":
        await update.message.reply_text(f"Игра не может быть начата. Не найдены игроки: {', '.join(missed_players)}")
        logger.info("Game at table %s could not be started. Members not found: %s", table_id, missed_players)
    else:
        await update.message.reply_text(f"Не удалось начать игру за столом {table_id}.")
        logger.error("Failed to start game at table %s. Result: %s", table_id, result)

# Command to update game status
async def update_game_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update the status of a game (admin only)."""
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
    """Create a backup of the database (admin only)."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    db.backup_database()
    await update.message.reply_text("Резервная копия базы данных успешно создана.")
    logger.info("Admin %s (%s) created a database backup.", user.username, user.id)

# Глобальные переменные для режима ожидания
awaiting_db_upload = False
awaiting_settings_upload = False

# Команда для получения текущей базы данных
async def get_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    with open(db.db_path, 'rb') as db_file:
        await update.message.reply_document(document=db_file)
    logger.info("Admin %s (%s) requested the database.", user.username, user.id)

# Команда для загрузки новой базы данных
async def set_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global awaiting_db_upload

    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    awaiting_db_upload = True
    await update.message.reply_text("Пожалуйста, загрузите файл базы данных.")
    logger.info("Admin %s (%s) initiated database upload.", user.username, user.id)

# Команда для получения текущих настроек
async def get_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    with open("config.ini", 'rb') as settings_file:
        await update.message.reply_document(document=settings_file)
    logger.info("Admin %s (%s) requested the settings file.", user.username, user.id)

async def set_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Загружает новый файл настроек и перезапускает сервисы.

    Args:
        update (Update): Объект Update от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
    """
    global awaiting_settings_upload

    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Эта команда доступна только администраторам.")
        return

    awaiting_settings_upload = True
    await update.message.reply_text("Пожалуйста, загрузите файл настроек.")
    logger.info("Admin %s (%s) initiated settings upload.", user.username, user.id)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает загруженные документы (настройки или базу данных).

    Args:
        update (Update): Объект Update от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
    """
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

        # Перезапускаем сервисы с новыми настройками
        restart_services()

        awaiting_settings_upload = False
        await update.message.reply_text("Новый файл настроек успешно загружен и сервисы перезапущены.")
        logger.info("Admin %s (%s) uploaded a new settings file and restarted services.", user.username, user.id)
    else:
        await update.message.reply_text("Неожиданно получен файл. Пожалуйста, используйте команду для загрузки перед отправкой файла.")
        logger.info("Unexpected file received from user %s (%s).", user.username, user.id)


def main() -> None:
    """Start the bot."""
    with open('token.txt', 'r') as file:
        token = file.read().strip()
    
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("my_games", my_games))
    application.add_handler(CommandHandler("ready", ready_command))
    application.add_handler(CommandHandler("unready", unready_command))
    application.add_handler(CommandHandler("start_table", start_table_command))
    application.add_handler(CommandHandler("update_game_status", update_game_status))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("get_db", get_db_command))
    application.add_handler(CommandHandler("set_db", set_db_command))
    application.add_handler(CommandHandler("get_settings", get_settings_command))
    application.add_handler(CommandHandler("set_settings", set_settings_command))
    application.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
