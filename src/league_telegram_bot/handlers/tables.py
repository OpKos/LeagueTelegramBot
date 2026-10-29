from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import models
from ..time_utils import datetime_to_timestamp, now_in_timezone
from .decorators import callback_query_handler, command_handler
from .utils import log_command_event, table_time_string

logger = logging.getLogger(__name__)

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


@dataclass(frozen=True)
class ParsedTableTime:
    timestamp: int
    games: int
    display: str


class TableTimeInputError(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def parse_table_time(
    day_arg: str,
    time_arg: str,
    games_arg: str,
    now: datetime.datetime,
    timezone: str,
) -> ParsedTableTime:
    try:
        games = int(games_arg)
    except ValueError as error:
        raise TableTimeInputError(
            "invalid_game_count", "Количество игр должно быть положительным."
        ) from error
    if games <= 0:
        raise TableTimeInputError(
            "nonpositive_game_count", "Количество игр должно быть положительным."
        )

    time_digits = "".join(ch for ch in time_arg if ch.isdigit())
    if not time_digits:
        raise TableTimeInputError("invalid_time", f"Время не распознано {time_arg}")
    if len(time_digits) < 3:
        hour = int(time_digits)
        minute = 0
    else:
        hour = int(time_digits[:-2])
        minute = int(time_digits[-2:])

    if day_arg.isnumeric():
        day = int(day_arg)
        month = now.month
        year = now.year
        if day < now.day:
            month += 1
            if month > 12:
                month = 1
                year += 1
    else:
        weekday_name = day_arg.lower()
        if weekday_name not in WEEKDAYS:
            raise TableTimeInputError("weekday_not_found", f"День недели не найден {weekday_name}.")
        weekday = WEEKDAYS.index(weekday_name)
        shift = (weekday - now.weekday()) % 7
        prospective_date = now + datetime.timedelta(days=shift)
        day = prospective_date.day
        month = prospective_date.month
        year = prospective_date.year

    try:
        prospective_start = datetime.datetime(
            year=year, month=month, day=day, hour=hour, minute=minute
        )
        timestamp = datetime_to_timestamp(prospective_start, timezone)
    except ValueError as error:
        raise TableTimeInputError(
            "invalid_time",
            f"Время не распознано {year}.{month}.{day} {hour}:{minute}",
        ) from error

    return ParsedTableTime(
        timestamp=timestamp,
        games=games,
        display=prospective_start.strftime("%d.%m %H:%M") + f" (игр: {games})",
    )


def remaining_unassigned_games(table: models.Table) -> int:
    scheduled_games = sum(table_time.games for table_time in table.table_times)
    return len(table.unfinished_games()) - scheduled_games


def validate_scheduled_game_count(table: models.Table, games: int) -> None:
    if games > remaining_unassigned_games(table):
        raise TableTimeInputError("too_many_games", "Указано больше игр, чем осталось.")


class TableHandlers:
    @command_handler("start_table")
    async def start_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "start_table", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        if not table.unfinished_games():
            log_command_event(
                update, "start_table", "rejected", logger=logger, reason="no_unfinished_games"
            )
            await update.effective_message.reply_text(text="Все игры за столом сыграны")
            return

        msg = self.games.get_table_ready_string(table_id=table.table_id)
        await update.message.reply_text(msg, reply_markup=self._ready_button_reply_markup)
        log_command_event(
            update, "start_table", "succeeded", logger=logger, table_id=table.table_id
        )

    @callback_query_handler(pattern=r"^RB")
    async def ready_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        chat = query.message.chat
        data = query.data[2:]
        await query.answer()
        log_command_event(update, "ready_button", "started", logger=logger, action=data)
        if data == "Cancel":
            await query.edit_message_text(text="Отменено")
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
            await query.edit_message_text(text="Все игры за столом сыграны")
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
                text = f"Игра за столом {game.table.name} запущена:"
                for index, player in enumerate(game.players()):
                    text += f"\n{seat_winds_names[index]} {player.irl_name} ({player.tenhou_name})"
                    self.ready.set_player_unready(player.p_id)
                await context.bot.send_message(chat_id=self.chat, text=text)
                await update.callback_query.edit_message_text(text="Приятной игры!")
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
                    text=f"Игроки не в лобби: {', '.join(missed_players)}, статус готовности обновлён."
                )
            else:
                await update.callback_query.message.chat.send_message(
                    text=f"Не удалось запустить игру: {result}"
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
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        if not context.args or len(context.args) != 3:
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="invalid_arguments"
            )
            await update.effective_message.reply_text(
                "Использование: /set_time <день> <время> <число игр>\n"
                "День вводить без месяца, только само число. Можно вводить день недели двумя буквами.\n"
                "Время можно указывать как с минутами, так и без. При указании с минутами, разделитель не обязателен.\n"
                "Пример: 17:00 вторник, 2 ханчана - /set_time вт 17 2\n"
                "Пример: 17:15 25 числа, 4 ханчана - /set_time 25 1715 4"
            )
            return

        if not table.unfinished_games():
            await update.effective_message.reply_text(f"Нет неначатых игр за столом {table.name}.")
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="no_unstarted_games"
            )
            return

        if user is None:
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="user_not_found"
            )
            return
        player = self.players.get_player(telegram_id=user.id)
        if player is None or player not in table.players():
            await update.effective_message.reply_text(
                "Указывать время можно только за своим столом."
            )
            log_command_event(
                update, "set_time", "rejected", logger=logger, reason="not_table_player"
            )
            return

        now = now_in_timezone(self.timezone)
        try:
            scheduled_time = parse_table_time(
                context.args[0],
                context.args[1],
                context.args[2],
                now,
                self.timezone,
            )
            validate_scheduled_game_count(table, scheduled_time.games)
        except TableTimeInputError as error:
            await update.effective_message.reply_text(str(error))
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
            await update.effective_message.reply_text("Не удалось сохранить время.")
            return
        await update.effective_message.reply_text(f"Время установлено: \n{scheduled_time.display}")
        log_command_event(update, "set_time", "succeeded", logger=logger, table_id=table.table_id)
        await update.effective_message.chat.send_poll(
            question=scheduled_time.display,
            options=["Согласен играть в это время"],
            allows_revoting=False,
            is_anonymous=False,
        )

    @command_handler("remove_time")
    async def remove_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            log_command_event(
                update, "remove_time", "rejected", logger=logger, reason="chat_has_no_table"
            )
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        player = self.players.get_player(telegram_id=user.id)
        if player not in table.players() and not self.is_admin(user.id):
            await update.effective_message.reply_text("Удалять время можно только за своим столом.")
            log_command_event(
                update, "remove_time", "rejected", logger=logger, reason="not_table_player"
            )
            return
        if not self.tables.clear_table_times(table.table_id):
            log_command_event(
                update, "remove_time", "failed", logger=logger, reason="table_not_found"
            )
            await update.effective_message.reply_text("Не удалось удалить время.")
            return
        log_command_event(
            update, "remove_time", "succeeded", logger=logger, table_id=table.table_id
        )
        await update.effective_message.reply_text("Время удалено.")

    @command_handler("timetable")
    async def timetable_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        if update.effective_message.chat.type != "private":
            log_command_event(
                update, "timetable", "rejected", logger=logger, reason="private_chat_required"
            )
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return

        now = now_in_timezone(self.timezone)
        cutoff = int((now - datetime.timedelta(hours=3)).timestamp())
        known_times = self.tables.get_all_relevant_table_times(left_cutoff=cutoff)
        known_str = "".join(
            table_time_string(i, explicit=True, timezone=self.timezone) for i in known_times
        )
        ans = known_str
        if ans == "":
            ans = "Игр нет"
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
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        player = self.players.get_player(telegram_id=user.id)
        if not player:
            log_command_event(
                update, "judge_call", "rejected", logger=logger, reason="not_registered"
            )
            await update.effective_message.reply_text("Вы не зарегистрированы в системе")
            return

        try:
            link = await context.bot.create_chat_invite_link(chat_id=table.chat_id)
        except Exception:
            await update.effective_message.reply_text("Ошибка генерации ссылки")
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
        msg = [f"{player.irl_name} вызывает админа за стол {table.name}\n{link.invite_link}\n"]
        for admin in admin_list:
            msg.append(admin.dirty_mention() + " ")
        msg = "".join(msg)
        await context.bot.send_message(chat_id=self.admin_chat, text=msg)
        await update.effective_message.reply_text("Вызвал админа за стол")
        log_command_event(update, "judge_call", "succeeded", logger=logger, table_id=table.table_id)
