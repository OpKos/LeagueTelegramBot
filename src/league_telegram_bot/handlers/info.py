from __future__ import annotations

import datetime
import logging

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..time_utils import now_in_timezone
from .decorators import command_handler
from .utils import log_command_event

logger = logging.getLogger(__name__)


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
        lang = self.language_for_user(user.id)

        if update.effective_message.chat.type != "private":
            log_command_event(
                update, "player_info", "rejected", logger=logger, reason="private_chat_required"
            )
            await update.effective_message.reply_text(self.tr(lang, "private_chat_required"))
            return

        if not context.args:
            player = self.players.get_player(telegram_id=user.id)

        elif len(context.args) != 1:
            log_command_event(
                update, "player_info", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(self.tr(lang, "player_info_usage"))
            return
        else:
            telegram_name = context.args[0]
            if telegram_name[0] == "@":
                telegram_name = telegram_name[1:]
            player = self.players.get_player(telegram_name=telegram_name)

        if not player:
            log_command_event(
                update, "player_info", "rejected", logger=logger, reason="player_not_found"
            )
            await update.effective_message.reply_text(self.tr(lang, "player_not_found"))
            return

        message_parts = []
        if self.is_admin(user.id):
            message_parts.append(
                self.tr(
                    lang,
                    "player_info_admin_ids",
                    player_id=player.p_id,
                    telegram_id=player.telegram_id,
                )
            )

        message_parts.append(
            self.tr(
                lang,
                "player_info_profile",
                telegram_name=player.telegram_name,
                tenhou_name=player.tenhou_name,
                name=player.irl_name,
            )
        )

        timezone = self.timezone_for_user(user.id)
        now = now_in_timezone(timezone)
        cutoff = int((now - datetime.timedelta(hours=3)).timestamp())

        tables = player.all_tables()
        tables.sort(key=lambda el: el.deadline_group)

        for table in tables:
            message_parts.append(self.tr(lang, "table_name", table=table.name) + "\n")
            message_parts.append(table.players_string(mention=True) + "\n")
            if table.unfinished_games and table.get_relevant_times(left_cutoff=cutoff):
                message_parts.append(self.tr(lang, "table_times_heading"))
                message_parts.append(
                    table.get_relevant_times_string(
                        timezone,
                        left_cutoff=cutoff,
                        weekday_names=tuple(self.weekday_names(lang)),
                    )
                    + "\n"
                )
            played_games, total_games = table.game_counts(player)
            message_parts.append(
                self.tr(
                    lang,
                    "table_played_games",
                    played=played_games,
                    total=total_games,
                )
                + "\n"
            )

        message = "".join(message_parts)
        message += "\n" + self.tr(lang, "timezone_note", timezone=timezone)
        await update.effective_message.reply_text(message)
        log_command_event(update, "player_info", "succeeded", logger=logger, player_id=player.p_id)

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
        lang = self.language_for_user(user.id)

        if update.effective_message.chat.type != "private":
            log_command_event(
                update, "table_info", "rejected", logger=logger, reason="private_chat_required"
            )
            await update.effective_message.reply_text(self.tr(lang, "private_chat_required"))
            return

        if not context.args or len(context.args) != 1:
            log_command_event(
                update, "table_info", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(self.tr(lang, "table_info_usage"))
            return

        table_name = context.args[0]
        table = self.tables.get_table(table_name=table_name)
        if not table:
            log_command_event(
                update, "table_info", "rejected", logger=logger, reason="table_not_found"
            )
            await update.effective_message.reply_text(self.tr(lang, "table_not_found"))
            return
        message_parts = [
            self.tr(lang, "table_name", table=table.table_id) + "\n",
            table.players_string(mention=True) + "\n",
            self.tr(
                lang,
                "table_played_games",
                played=len(table.games) - len(table.unfinished_games()),
                total=len(table.games),
            ),
        ]

        timezone = self.timezone_for_user(user.id)
        now = now_in_timezone(timezone)
        cutoff = int((now - datetime.timedelta(hours=3)).timestamp())

        if table.unfinished_games() and table.get_relevant_times(left_cutoff=cutoff):
            message_parts.extend(
                [
                    self.tr(lang, "table_times_heading"),
                    table.get_relevant_times_string(
                        timezone,
                        left_cutoff=cutoff,
                        weekday_names=tuple(self.weekday_names(lang)),
                    ),
                ]
            )
        message_parts.append("\n\n")

        for game in table.games:
            message_parts.append(game.info_string(self.translate(lang)))

        message = "".join(message_parts)
        message += self.tr(lang, "timezone_note", timezone=timezone)
        await update.effective_message.reply_text(message)
        log_command_event(update, "table_info", "succeeded", logger=logger, table_id=table.table_id)

    @command_handler("lobby")
    async def lobby_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_message
        await update.effective_message.reply_text(f"https://tenhou.net/3/?{self.lobby[:9]}")
        log_command_event(update, "lobby", "succeeded", logger=logger)

    @command_handler("pantheon")
    async def pantheon_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_message
        lang = self.language_for_update(update)
        events = self.events.get_started_events()
        if not events:
            log_command_event(update, "pantheon", "succeeded", logger=logger, active_events=0)
            await update.effective_message.reply_text(self.tr(lang, "pantheon_no_events"))
            return
        links = [f"<a href='{event.pantheon_link()}'>{event.short_name}</a>" for event in events]
        await update.effective_message.reply_text(
            "\n".join(links),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        log_command_event(update, "pantheon", "succeeded", logger=logger, active_events=len(events))
