from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ..integrations.event_portal import event_portal_update
from ..integrations.pantheon import PantheonClient
from ..leaderboard.logic import get_leaderboard_data
from ..seating.image import create_seating_image
from ..seating.logic import add_table, create_seating
from .decorators import command_handler

logger = logging.getLogger()


class AdminHandlers:
    @command_handler("update_game_status")
    async def update_game_status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Обновляет статус игры (только для администраторов)."""
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        if not context.args or len(context.args) != 2:
            await update.effective_message.reply_text(
                "Usage: /update_game_status <game_id> <status>"
            )
            return

        game_id = int(context.args[0])
        status = int(context.args[1])

        if status not in [0, 1]:
            await update.effective_message.reply_text(
                "Invalid status. Use '1' for started or '0' for not started."
            )
            return

        success = self.games.set_game_status(game_id, status)
        if success:
            status_text = "started" if status != 0 else "not started"
            await update.effective_message.reply_text(
                f"Статус игры с ID {game_id} успешно обновлен на '{status_text}'."
            )
            logger.info(
                "Admin %s (%s) updated game status with game ID %s to %s.",
                user.username,
                user.id,
                game_id,
                status_text,
            )
        else:
            await update.effective_message.reply_text(
                f"Не удалось обновить статус игры с ID {game_id}."
            )
            logger.error(
                "Admin %s (%s) failed to update game status with game ID %s to %s.",
                user.username,
                user.id,
                game_id,
                status,
            )

    @command_handler("replace_player")
    async def replace_player_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        logger.info(
            "User %s (%s) uses command %s with args %s.",
            user.username,
            user.id,
            "replace_player",
            str(context.args),
        )

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        if not context.args or len(context.args) != 3:
            await update.effective_message.reply_text(
                "Usage: /replace_player <game_id> <seat> <player_id>"
            )
            return

        game_id = int(context.args[0])
        seat = int(context.args[1])
        player_id = int(context.args[2])

        self.games.replace_game_player(game_id=game_id, seat=seat, player_id=player_id)
        await update.effective_message.reply_text("Игрок успешно заменён.")
        logger.info(
            "Admin %s (%s) set player in game %s (seat %s) to %s.",
            user.username,
            user.id,
            game_id,
            seat,
            player_id,
        )

    @command_handler("get_logs")
    async def get_logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Отправляет файл с логами администратору."""
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
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

    @command_handler("force_reveal")
    async def force_reveal_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Админская команда раскрытия стола через стандартный метод"""
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
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

        if self.tables.reveal_table(table_id):
            table = self.tables.get_table(table_id)
            assert table
            await self.notify_table_revealed(context.bot, table)
            await update.effective_message.reply_text(f"Стол {table_id} раскрыт")
        else:
            await update.effective_message.reply_text("Ошибка раскрытия стола")

    @command_handler("status")
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        await self.send_game_status_message(context)

    async def reload_session_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Admin command to reload database session"""
        user = update.effective_user
        assert user
        assert update.effective_message
        if not self.is_admin(user.id):
            await update.effective_message.reply_text("🔒 Admin only command")
            return

        if self.session_manager.reload_session():
            await update.effective_message.reply_text("🔄 Database session reloaded")
        else:
            await update.effective_message.reply_text("❌ Failed to reload session")

    @command_handler("get_settings")
    async def get_settings_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Отправляет текущий файл настроек администратору."""
        user = update.effective_user
        assert user
        assert update.effective_message
        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        with open(self.settings_path, "rb") as settings_file:
            await update.effective_message.reply_document(document=settings_file)
        logger.info("Admin %s (%s) requested the settings file.", user.username, user.id)

    @command_handler("update_event_players")
    async def update_event_players_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message
        assert context.job_queue

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        logger.info("Admin %s (%s) updated players in events.", user.username, user.id)

        events = self.events.get_signup_events()

        for event in events:
            self.events.clear_event_players(event.event_id)
            res = event_portal_update(self.players, self.events, event)
            await update.effective_message.reply_text(f"Event {event.event_id}\n{res}")
            logger.info("Updated event %s", event.event_id)

    @command_handler("create_seating")
    async def create_seating_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event = self.events.get_event(int(context.args[0]))
        logger.info(
            "Admin %s (%s) created seating for event %s", user.username, user.id, event.event_id
        )
        create_seating(self.tables, self.games, event)
        await update.effective_message.reply_text("Seating created")

    @command_handler("reveal_new_tables")
    async def reveal_new_tables(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event = self.events.get_event(int(context.args[0]))
        new_min = int(context.args[1])
        new_max = int(context.args[2])
        logger.info(
            "Admin %s (%s) revealed new tables with new_min = %s and new_max = %s",
            user.username,
            event.event_id,
            new_min,
            new_max,
        )
        logger.info("Admin %s (%s) revealed new tables", user.username, event.event_id)
        event.global_maximum = new_max
        nt = self.reveal.try_reveal(event.event_id, cache=True)
        while nt:
            nt = self.reveal.try_reveal(event.event_id, cache=True)
        event.global_minimum = new_min
        nt = self.reveal.try_reveal(event.event_id, cache=True)
        while nt:
            nt = self.reveal.try_reveal(event.event_id, cache=True)
        cached = self.tables.get_event_cached_tables(event_id=event.event_id)
        await update.effective_message.reply_text(
            f"Event {event.event_id} cached tables\n{' '.join(t.name for t in cached)}"
        )

    @command_handler("seating_image")
    async def seating_image_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        events = self.events.get_signup_events()
        logger.info(
            "Admin %s (%s) requested image for deadline group %s",
            user.username,
            user.id,
            context.args[0],
        )
        create_seating_image(
            events=events,
            deadline_group=int(context.args[0]),
            filename="seating.png",
            header=" ".join(context.args[1:]),
        )
        with open("seating.png", "rb") as image_file:
            await update.effective_message.reply_document(document=image_file)

    @command_handler("split_leaderboard")
    async def split_leaderboard_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event_id = int(context.args[0])
        cutoff = int(context.args[1])

        event = self.events.get_event(event_id)
        api_url = os.getenv("PANTHEON_GAME_API_URL", "https://gameapi.riichimahjong.org")
        client = PantheonClient(
            api_url,
            server_path_prefix="/v2",
        )
        pantheon_data = client.get_rating_table(
            event_id_list=[event.pantheon_id], order="desc", order_by="rating"
        ).get("players")
        leaderboard = get_leaderboard_data(event, pantheon_data)
        player_ids = []
        for player in leaderboard[cutoff:]:
            player_ids.append(player[3])
        self.players.edit_event_players_leaderboard_group(event_id=event_id, player_ids=player_ids)
        await update.effective_message.reply_text("Успешно")

    @command_handler("add_table")
    async def add_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event_id = int(context.args[0])
        cutoff = int(context.args[1]) - 1
        amount = int(context.args[2])
        table_name = context.args[3]

        event = self.events.get_event(event_id)
        api_url = os.getenv("PANTHEON_GAME_API_URL", "https://gameapi.riichimahjong.org")
        client = PantheonClient(
            api_url,
            server_path_prefix="/v2",
        )
        pantheon_data = client.get_rating_table(
            event_id_list=[event.pantheon_id], order="desc", order_by="rating"
        ).get("players")
        leaderboard = get_leaderboard_data(event, pantheon_data)
        player_ids = []
        for player in leaderboard[cutoff : cutoff + amount]:
            player_ids.append(player[3])
        players = [self.players.get_player(p_id=el) for el in player_ids]
        add_table(
            tables=self.tables,
            games=self.games,
            players=players,
            event=event,
            table_name=table_name,
        )
        await update.effective_message.reply_text("Успешно")
