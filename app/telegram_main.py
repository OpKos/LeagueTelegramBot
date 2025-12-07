#!/usr/bin/env python3
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from other_bot_functions import *

def main() -> None:
    setup_logging()

    with open("token.txt", "r") as file:
        token = file.read().strip()
    
    application = Application.builder().token(token).write_timeout(30).read_timeout(30).connect_timeout(300).build()

    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("start_table", start_table_command))
    application.add_handler(CommandHandler("next_table", next_table_command))
    application.add_handler(CommandHandler("update_game_status", update_game_status_command))
    application.add_handler(CommandHandler("get_settings", get_settings_command))
    application.add_handler(CommandHandler("get_logs", get_logs_command))
    application.add_handler(CommandHandler("force_reveal", force_reveal_command))
    application.add_handler(CommandHandler(["player_info", "my_games"], get_player_info_command))
    application.add_handler(CommandHandler("table_info", get_table_info_command))
    application.add_handler(CommandHandler("start_status_message", start_status_message_command))
    application.add_handler(CommandHandler("set_time", set_time_command))
    application.add_handler(CommandHandler("remove_time", remove_time_command))
    application.add_handler(CommandHandler("timetable", timetable_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("lobby", lobby_command))
    application.add_handler(CommandHandler("pantheon", pantheon_command))
    application.add_handler(CommandHandler("set_language", set_language))
    application.add_handler(CommandHandler("update_event_players", update_event_players_command))
    application.add_handler(CommandHandler("create_seating", create_seating_command))
    application.add_handler(CommandHandler("next_table", next_table_command))
    application.add_handler(CommandHandler("all_tables", all_tables_command))
    application.add_handler(CommandHandler("reveal_new_tables", reveal_new_tables))
    application.add_handler(CommandHandler("seating_image", seating_image_command))
    application.add_handler(CommandHandler("set_chat", set_chat))

    application.add_handler(CallbackQueryHandler(chat_button, pattern=r"^TC"))
    application.add_handler(CallbackQueryHandler(ready_button, pattern=r"^RB"))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
