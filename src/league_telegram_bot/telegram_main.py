#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .app_config import load_app_config, load_locales
from .handlers import BotHandlers
from .logging_setup import configure_logging


def load_token(token_path: Path) -> str:
    with open(token_path, encoding="utf-8") as file:
        return file.read().strip()


def build_application(token: str, handlers: BotHandlers) -> Application:
    application = (
        Application.builder()
        .token(token)
        .write_timeout(30)
        .read_timeout(30)
        .connect_timeout(300)
        .build()
    )

    application.add_handler(CommandHandler("register", handlers.register_command))
    application.add_handler(CommandHandler("set_language", handlers.set_language))
    application.add_handler(
        CommandHandler(["player_info", "my_games"], handlers.get_player_info_command)
    )

    application.add_handler(CommandHandler("set_chat", handlers.set_chat))

    application.add_handler(CommandHandler("start_table", handlers.start_table_command))

    application.add_handler(CommandHandler("next_table", handlers.next_table_command))
    application.add_handler(CommandHandler("all_tables", handlers.all_tables_command))

    application.add_handler(CommandHandler("set_time", handlers.set_time_command))
    application.add_handler(CommandHandler("remove_time", handlers.remove_time_command))
    application.add_handler(CommandHandler("timetable", handlers.timetable_command))

    application.add_handler(CommandHandler("get_settings", handlers.get_settings_command))
    application.add_handler(CommandHandler("get_logs", handlers.get_logs_command))

    application.add_handler(CommandHandler("lobby", handlers.lobby_command))
    application.add_handler(CommandHandler("pantheon", handlers.pantheon_command))

    application.add_handler(
        CommandHandler("update_game_status", handlers.update_game_status_command)
    )
    application.add_handler(CommandHandler("force_reveal", handlers.force_reveal_command))
    application.add_handler(CommandHandler("table_info", handlers.get_table_info_command))

    application.add_handler(
        CommandHandler("start_status_message", handlers.start_status_message_command)
    )
    application.add_handler(CommandHandler("status", handlers.status_command))

    application.add_handler(
        CommandHandler("update_event_players", handlers.update_event_players_command)
    )
    application.add_handler(CommandHandler("create_seating", handlers.create_seating_command))
    application.add_handler(CommandHandler("reveal_new_tables", handlers.reveal_new_tables))
    application.add_handler(CommandHandler("seating_image", handlers.seating_image_command))

    application.add_handler(CallbackQueryHandler(handlers.chat_button, pattern=r"^TC"))
    application.add_handler(CallbackQueryHandler(handlers.ready_button, pattern=r"^RB"))

    return application


def main() -> None:
    config = load_app_config()
    configure_logging(config.logging_config_path)
    locales = load_locales(config.locales_path)
    handlers = BotHandlers(config, locales)

    token = load_token(config.token_path)
    application = build_application(token, handlers)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
