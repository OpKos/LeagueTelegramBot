from __future__ import annotations

import datetime
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import models
from ..time_utils import (
    TableTimeInputError,
    datetime_from_timestamp,
    now_in_timezone,
    parse_table_time,
)
from .decorators import callback_query_handler, command_handler
from .utils import game_amount_string, generate_calendar_event, log_command_event, table_time_string

logger = logging.getLogger(__name__)


class TableHandlers:
    @command_handler("play")
    async def play_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(update, "play", "rejected", logger=logger, reason="chat_has_no_table")
            await update.effective_message.reply_text(self.tr("ru", "no_table_in_chat"))
            return

        if not table.unfinished_games():
            log_command_event(
                update, "play", "rejected", logger=logger, reason="no_unfinished_games"
            )
            await update.effective_message.reply_text(text=self.tr("ru", "no_unfinished_games"))
            return

        msg = self.games.get_table_ready_string(table_id=table.table_id)
        await update.message.reply_text(msg, reply_markup=self._ready_button_reply_markup)
        log_command_event(update, "play", "succeeded", logger=logger, table_id=table.table_id)

    @callback_query_handler(pattern=r"^RB")
    async def ready_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        chat = query.message.chat
        data = query.data[2:]
        await query.answer()
        log_command_event(update, "ready_button", "started", logger=logger, action=data)
        if data == "Cancel":
            await query.edit_message_text(text=self.tr("ru", "cancelled"))
            log_command_event(update, "ready_button", "rejected", logger=logger, reason="cancelled")
            return
        user = update.effective_user
        if user is None:
            log_command_event(
                update, "ready_button", "rejected", logger=logger, reason="user_not_found"
            )
            return
        player = self.players.get_player(telegram_id=user.id)
        if player is None:
            log_command_event(
                update, "ready_button", "rejected", logger=logger, reason="not_registered"
            )
            return
        table = self.tables.get_table(chat_id=chat.id)
        if table is None:
            log_command_event(
                update, "ready_button", "rejected", logger=logger, reason="chat_has_no_table"
            )
            return
        if not table.unfinished_games():
            await query.edit_message_text(text=self.tr("ru", "no_unfinished_games"))
            log_command_event(
                update, "ready_button", "rejected", logger=logger, reason="no_unfinished_games"
            )
            return
        if data == "Ready":
            self.ready.set_player_ready(player.p_id)
        elif data == "Unready":
            self.ready.set_player_unready(player.p_id)
        else:
            log_command_event(
                update, "ready_button", "rejected", logger=logger, reason="invalid_action"
            )
            return
        msg = self.games.get_table_ready_string(table_id=table.table_id)
        await query.edit_message_text(text=msg, reply_markup=self._ready_button_reply_markup)
        log_command_event(
            update,
            "ready_button",
            "succeeded",
            logger=logger,
            action=data,
            player_id=player.p_id,
            table_id=table.table_id,
        )
        await self.table_check_and_start_game(table, update, context)

    async def table_check_and_start_game(
        self, table: models.Table, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        game = self.games.get_first_ready_game(table.table_id)
        if game is not None:
            await self.game_start(game, table, update, context)

    async def game_start(
        self,
        game: models.Game,
        table: models.Table,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        log_command_event(update, "game_start", "started", logger=logger, game_id=game.game_id)
        player_nicks = [player.tenhou_name for player in game.players()]
        try:
            result, missed_players, success = self.tenhou_client.start_game(player_nicks)
        except Exception:
            log_command_event(
                update,
                "game_start",
                "failed",
                logger=logger,
                exc_info=True,
                game_id=game.game_id,
                reason="tenhou_exception",
            )
            raise

        if success:
            try:
                self.games.set_game_status(game.game_id, 1)
                seat_winds_names = ["東", "南", "西", "北"]
                players_text = []
                for index, player in enumerate(game.players()):
                    players_text.append(
                        f"{seat_winds_names[index]} {player.irl_name} ({player.tenhou_name})"
                    )
                    self.ready.set_player_unready(player.p_id)
                text = self.tr(
                    "ru",
                    "start_game_announcement",
                    table=game.table.name,
                    players="\n".join(players_text),
                )
                await context.bot.send_message(chat_id=self.chat, text=text)
                await update.callback_query.edit_message_text(text=self.tr("ru", "start_game_done"))
            except Exception:
                log_command_event(
                    update,
                    "game_start",
                    "failed",
                    logger=logger,
                    exc_info=True,
                    game_id=game.game_id,
                    reason="post_start_action_failed",
                )
                raise
            log_command_event(
                update,
                "game_start",
                "succeeded",
                logger=logger,
                game_id=game.game_id,
                result=result,
                missed_players=missed_players,
            )
            return

        try:
            if result == "MEMBER NOT FOUND":
                for nick in missed_players:
                    player = self.players.get_player(tenhou_name=nick)
                    if player is None:
                        log_command_event(
                            update,
                            "game_start",
                            "failed",
                            logger=logger,
                            game_id=game.game_id,
                            reason="missed_player_not_found",
                            tenhou_name=nick,
                        )
                        continue
                    self.ready.set_player_unready(player.p_id)
                msg = self.games.get_table_ready_string(table_id=table.table_id)
                await update.callback_query.edit_message_text(
                    text=msg, reply_markup=self._ready_button_reply_markup
                )
                await update.callback_query.message.chat.send_message(
                    text=self.tr(
                        "ru",
                        "start_game_missing_players",
                        players=", ".join(missed_players),
                    )
                )
            else:
                await update.callback_query.message.chat.send_message(
                    text=self.tr("ru", "start_game_failed", reason=result)
                )
        except Exception:
            log_command_event(
                update,
                "game_start",
                "failed",
                logger=logger,
                exc_info=True,
                game_id=game.game_id,
                reason="failure_notification_failed",
            )
            raise
        log_command_event(
            update,
            "game_start",
            "failed",
            logger=logger,
            game_id=game.game_id,
            reason=result,
            missed_players=missed_players,
            success=success,
        )

    @command_handler("set_time")
    async def set_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add one proposed game time for this table."""
        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(self.tr("ru", "no_table_in_chat"))
            return

        if not context.args or len(context.args) != 3:
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(self.tr("ru", "set_time_usage"))
            return

        if not table.unfinished_games():
            await update.effective_message.reply_text(
                self.tr("ru", "set_time_no_games", table=table.name)
            )
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="no_unstarted_games"
            )
            return

        timezone = self.timezone_for_user(update.effective_user.id)
        now = now_in_timezone(timezone)
        try:
            scheduled_time = parse_table_time(
                context.args[0],
                context.args[1],
                context.args[2],
                now,
                timezone,
            )
            table.validate_scheduled_game_count(scheduled_time.games)
        except TableTimeInputError as error:
            await update.effective_message.reply_text(
                self.tr("ru", f"set_time_{error.reason}", **error.params)
            )
            log_command_event(update, "set_time", "rejected", logger=logger, reason=error.reason)
            return

        cutoff = now + datetime.timedelta(hours=12)
        cutoff = int(cutoff.timestamp())
        if not self.tables.add_table_time(
            table_id=table.table_id,
            timestamp=scheduled_time.timestamp,
            games=scheduled_time.games,
            reminder_cutoff=cutoff,
        ):
            log_command_event(update, "set_time", "failed", logger=logger, reason="table_not_found")
            await update.effective_message.reply_text(self.tr("ru", "set_time_save_failed"))
            return
        display = "\n".join(
            self.tr(
                "ru",
                "timezone_time",
                timezone=table_timezone,
                time=(
                    f"{datetime_from_timestamp(scheduled_time.timestamp, table_timezone).strftime('%d.%m %H:%M')} "
                    f"({game_amount_string(scheduled_time.games, 'ru', self.translate('ru'))})"
                ),
            )
            for table_timezone in table.get_timezones(self.timezone)
        )
        await update.effective_message.reply_text(self.tr("ru", "set_time_success", time=display))
        calendar_filename = f"Kawa_Table_{table.name}.ics"
        generate_calendar_event(
            name=(
                f"Kawa Table {table.name} "
                f"({game_amount_string(scheduled_time.games, 'ru', self.translate('ru'))})"
            ),
            start_time=datetime.datetime.fromtimestamp(scheduled_time.timestamp, tz=now.tzinfo),
            length=datetime.timedelta(hours=scheduled_time.games),
            filename=calendar_filename,
        )
        with Path(calendar_filename).open("rb") as calendar_file:
            await update.effective_message.reply_document(document=calendar_file)
        log_command_event(update, "set_time", "succeeded", logger=logger, table_id=table.table_id)
        await update.effective_message.chat.send_poll(
            question=display,
            options=[self.tr("ru", "set_time_poll")],
            allows_revoting=False,
            is_anonymous=False,
        )

    @command_handler("remove_time")
    async def remove_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "remove_time", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(self.tr("ru", "no_table_in_chat"))
            return

        if not self.tables.clear_table_times(table.table_id):
            log_command_event(
                update, "remove_time", "failed", logger=logger, reason="table_not_found"
            )
            await update.effective_message.reply_text(self.tr("ru", "remove_time_failed"))
            return
        log_command_event(
            update, "remove_time", "succeeded", logger=logger, table_id=table.table_id
        )
        await update.effective_message.reply_text(self.tr("ru", "remove_time_success"))

    @command_handler("timetable")
    async def timetable_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message
        lang = self.language_for_user(user.id)

        if update.effective_message.chat.type != "private":
            log_command_event(
                update, "timetable", "rejected", logger=logger, reason="private_chat_required"
            )
            await update.effective_message.reply_text(self.tr(lang, "private_chat_required"))
            return

        timezone = self.timezone_for_user(user.id)
        now = now_in_timezone(timezone)
        cutoff = int((now - datetime.timedelta(hours=3)).timestamp())
        known_times = self.tables.get_all_relevant_table_times(left_cutoff=cutoff)
        known_str = "".join(
            table_time_string(
                i,
                explicit=True,
                timezone=timezone,
                lang=lang,
                translate=self.translate(lang),
                weekday_names=tuple(self.weekday_names(lang)),
            )
            for i in known_times
        )
        ans = known_str
        if ans == "":
            ans = self.tr(lang, "timetable_empty")
        ans += "\n\n" + self.tr(lang, "timezone_note", timezone=timezone)
        await update.effective_message.reply_text(ans, parse_mode=ParseMode.HTML)
        log_command_event(
            update, "timetable", "succeeded", logger=logger, table_count=len(known_times)
        )

    @command_handler("judge_call")
    async def judge_call_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "judge_call", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(self.tr("ru", "no_table_in_chat"))
            return

        player = self.players.get_player(telegram_id=user.id)
        if not player:
            log_command_event(
                update, "judge_call", "rejected", logger=logger, reason="not_registered"
            )
            await update.effective_message.reply_text(self.tr("ru", "not_registered_system"))
            return

        try:
            link = await context.bot.create_chat_invite_link(chat_id=table.chat_id)
        except Exception:
            await update.effective_message.reply_text(self.tr("ru", "judge_call_failed_link"))
            log_command_event(
                update,
                "judge_call",
                "failed",
                logger=logger,
                exc_info=True,
                table_id=table.table_id,
            )
            return
        admin_list = self.players.get_admins()
        msg = [
            self.tr(
                "ru",
                "judge_call_admin_message",
                player=player.irl_name,
                table=table.name,
                link=link.invite_link,
            )
            + "\n"
        ]
        for admin in admin_list:
            msg.append(admin.dirty_mention() + " ")
        msg = "".join(msg)
        await context.bot.send_message(chat_id=self.admin_chat, text=msg)
        await update.effective_message.reply_text(self.tr("ru", "judge_call_success"))
        log_command_event(update, "judge_call", "succeeded", logger=logger, table_id=table.table_id)
