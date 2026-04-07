from __future__ import annotations

import logging

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .decorators import command_handler
from .utils import timestring_from_timestamp

logger = logging.getLogger()


class InfoHandlers:
    @command_handler("player_info", "my_games")
    async def get_player_info_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Получает информацию об игроке
        """
        user = update.effective_user
        assert user
        assert update.effective_message

        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return

        if not context.args:
            player = self.players.get_player(telegram_id=user.id)

        elif len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /player_info <telegram_name>")
            return
        else:
            telegram_name = context.args[0]
            if telegram_name[0] == "@":
                telegram_name = telegram_name[1:]
            player = self.players.get_player(telegram_name=telegram_name)

        if not player:
            await update.effective_message.reply_text("Пользователь не зарегистрирован.")
            return

        message = ""
        if self.is_admin(user.id):
            message += f"ID в базе: {player.p_id}\n" f"Telegram ID: {player.telegram_id}\n"

        message += (
            f"Telegram хэндл: @{player.telegram_name}\n"
            f"Tenhou ник: {player.tenhou_name}\n"
            f"Имя: {player.irl_name}\n\n"
        )

        for table in player.visible_tables():
            message += f"Стол {table.name}\n"
            for i in table.players():
                message += f"{i.irl_name} ({i.dirty_mention()})\n"
            if table.unfinished_games and table.time:
                message += (
                    f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}\n"
                )
            message += f"Сыграно: {len(table.games) - len(table.unfinished_games())} из {len(table.games)} игр\n\n"

        if player.invisible_tables() and self.is_admin(user.id):
            ids = [i.name for i in player.invisible_tables()]
            message += f"Скрытые столы: {ids}\n\n"
        await update.effective_message.reply_text(message)
        logger.info("Person %s requested info for player %s", user.full_name, player.irl_name)

    @command_handler("table_info")
    async def get_table_info_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Получает информацию о столе
        """
        user = update.effective_user
        assert user
        assert update.effective_message

        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return

        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /table_info <table_id>")
            return

        table_id = int(context.args[0])
        table = self.tables.get_table(table_id)
        if not table:
            await update.effective_message.reply_text("Стол не найден.")
            return
        if not table.visible and not self.is_admin(user.id):
            await update.effective_message.reply_text("Стол скрыт.")
            return

        message = f"Стол {table.table_id}\n" f"{'Стол скрыт 🔒' if not table.visible else ''}\n"
        for i in table.players():
            message += f"{i.irl_name} ({i.dirty_mention()})\n"
        message += (
            f"Сыграно: {len(table.games) - len(table.unfinished_games)} из {len(table.games)} игр\n"
        )
        if table.time:
            message += f"Время: {timestring_from_timestamp(table.time, weekday=True, day=True)}"
        message += "\n\n"

        games = table.games
        for game in games:
            message += (
                f"ID игры: {game.game_id}\n"
                f"{'🟢 Запущена' if game.started else '🔴 Не запущена'}\n"
            )
            for player in game.players():
                message += f"{player.irl_name}\n"
            message += "\n"

        await update.effective_message.reply_text(message)
        logger.info("Person %s requested info for table %s", user.full_name, table.table_id)

    @command_handler("lobby")
    async def lobby_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_message
        await update.effective_message.reply_text(f"https://tenhou.net/3/?{self.lobby[:9]}")

    @command_handler("pantheon")
    async def pantheon_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_message
        events = self.events.get_started_events()
        if not events:
            await update.effective_message.reply_text("Активных событий нет")
            return
        links = [f"<a href='{event.pantheon_link()}'>Дивизион {event.name}</a>" for event in events]
        await update.effective_message.reply_text(
            "\n".join(links),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
