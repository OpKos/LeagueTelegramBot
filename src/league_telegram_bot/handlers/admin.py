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
from .utils import log_command_event

logger = logging.getLogger(__name__)


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
            log_command_event(
                update, "update_game_status", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        if not context.args or len(context.args) != 2:
            log_command_event(
                update,
                "update_game_status",
                "rejected",
                logger=logger,
                reason="invalid_arguments",
            )
            await update.effective_message.reply_text(
                "Usage: /update_game_status <game_id> <status>"
            )
            return

        game_id = int(context.args[0])
        status = int(context.args[1])

        if status not in [0, 1]:
            log_command_event(
                update, "update_game_status", "rejected", logger=logger, reason="invalid_status"
            )
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
            log_command_event(
                update,
                "update_game_status",
                "succeeded",
                logger=logger,
                game_id=game_id,
                status=status_text,
            )
        else:
            await update.effective_message.reply_text(
                f"Не удалось обновить статус игры с ID {game_id}."
            )
            log_command_event(
                update,
                "update_game_status",
                "failed",
                logger=logger,
                game_id=game_id,
                status=status,
            )

    @command_handler("replace_player")
    async def replace_player_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            log_command_event(
                update, "replace_player", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        if not context.args or len(context.args) != 3:
            log_command_event(
                update, "replace_player", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(
                "Usage: /replace_player <game_id> <seat> <player_id>"
            )
            return

        game_id = int(context.args[0])
        seat = int(context.args[1])
        player_id = int(context.args[2])

        self.games.replace_game_player(game_id=game_id, seat=seat, player_id=player_id)
        await update.effective_message.reply_text("Игрок успешно заменён.")
        log_command_event(
            update,
            "replace_player",
            "succeeded",
            logger=logger,
            game_id=game_id,
            seat=seat,
            player_id=player_id,
        )

    @command_handler("get_logs")
    async def get_logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Отправляет файл с логами администратору."""
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            log_command_event(update, "get_logs", "rejected", logger=logger, reason="admin_only")
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        try:
            with open("bot.log", "rb") as log_file:
                await update.effective_message.reply_document(document=log_file)
            log_command_event(update, "get_logs", "succeeded", logger=logger)
        except FileNotFoundError:
            await update.effective_message.reply_text("Файл с логами не найден.")
            log_command_event(
                update, "get_logs", "failed", logger=logger, exc_info=True, reason="file_missing"
            )
        except Exception as e:
            await update.effective_message.reply_text(f"Произошла ошибка при отправке логов: {e}")
            log_command_event(update, "get_logs", "failed", logger=logger, exc_info=True)

    @command_handler("status")
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        if not self.is_admin(user.id):
            log_command_event(update, "status", "rejected", logger=logger, reason="admin_only")
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        await self.send_game_status_message(context)
        log_command_event(update, "status", "succeeded", logger=logger)

    async def reload_session_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Admin command to reload database session"""
        user = update.effective_user
        assert user
        assert update.effective_message
        if not self.is_admin(user.id):
            log_command_event(
                update, "reload_session", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text("🔒 Admin only command")
            return

        if self.session_manager.reload_session():
            await update.effective_message.reply_text("🔄 Database session reloaded")
            log_command_event(update, "reload_session", "succeeded", logger=logger)
        else:
            await update.effective_message.reply_text("❌ Failed to reload session")
            log_command_event(
                update, "reload_session", "failed", logger=logger, reason="reload_failed"
            )

    @command_handler("get_settings")
    async def get_settings_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Отправляет текущий файл настроек администратору."""
        user = update.effective_user
        assert user
        assert update.effective_message
        if not self.is_admin(user.id):
            log_command_event(
                update, "get_settings", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        with open(self.settings_path, "rb") as settings_file:
            await update.effective_message.reply_document(document=settings_file)
        log_command_event(update, "get_settings", "succeeded", logger=logger)

    @command_handler("update_event_players")
    async def update_event_players_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message
        assert context.job_queue

        if not self.is_admin(user.id):
            log_command_event(
                update, "update_event_players", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        events = self.events.get_signup_events()

        for event in events:
            self.events.clear_event_players(event.event_id)
            res = event_portal_update(self.players, self.events, event)
            await update.effective_message.reply_text(f"Event {event.event_id}\n{res}")
            log_command_event(
                update,
                "update_event_players",
                "succeeded",
                logger=logger,
                event_id=event.event_id,
            )

    @command_handler("create_seating")
    async def create_seating_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            log_command_event(
                update, "create_seating", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event = self.events.get_event(int(context.args[0]))
        create_seating(self.tables, self.games, event)
        await update.effective_message.reply_text("Seating created")
        log_command_event(
            update, "create_seating", "succeeded", logger=logger, event_id=event.event_id
        )

    @command_handler("seating_image")
    async def seating_image_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            log_command_event(
                update, "seating_image", "rejected", logger=logger, reason="admin_only"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        events = self.events.get_signup_events()
        create_seating_image(
            events=events,
            deadline_group=int(context.args[0]),
            filename="seating.png",
            header=" ".join(context.args[1:]),
        )
        with open("seating.png", "rb") as image_file:
            await update.effective_message.reply_document(document=image_file)
        log_command_event(
            update,
            "seating_image",
            "succeeded",
            logger=logger,
            deadline_group=context.args[0],
        )

    @command_handler("split_leaderboard")
    async def split_leaderboard_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            log_command_event(
                update, "split_leaderboard", "rejected", logger=logger, reason="admin_only"
            )
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
        log_command_event(
            update, "split_leaderboard", "succeeded", logger=logger, event_id=event_id
        )

    @command_handler("add_table")
    async def add_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            log_command_event(update, "add_table", "rejected", logger=logger, reason="admin_only")
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
        log_command_event(
            update,
            "add_table",
            "succeeded",
            logger=logger,
            event_id=event_id,
            table_name=table_name,
        )

    @command_handler("table_chat")
    async def table_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            log_command_event(update, "table_chat", "rejected", logger=logger, reason="admin_only")
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /table_chat <table_id>")
            return

        table_name = context.args[0]
        table = self.tables.get_table(table_name=table_name)
        if not table:
            log_command_event(
                update, "table_chat", "rejected", logger=logger, reason="table_not_found"
            )
            await update.effective_message.reply_text("Стол не найден.")
            return
        try:
            link = await context.bot.create_chat_invite_link(chat_id=table.chat_id)
        except Exception:
            await update.effective_message.reply_text("Ошибка генерации ссылки")
            log_command_event(
                update,
                "table_chat",
                "failed",
                logger=logger,
                exc_info=True,
                table_id=table.table_id,
            )
            return
        await update.effective_message.reply_text(link.invite_link)
        log_command_event(update, "table_chat", "succeeded", logger=logger, table_id=table.table_id)
