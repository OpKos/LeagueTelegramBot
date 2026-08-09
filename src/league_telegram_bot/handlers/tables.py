from __future__ import annotations

import datetime
import logging

import pytz
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .decorators import callback_query_handler, command_handler
from .utils import table_time_string

logger = logging.getLogger()


class TableHandlers:
    @command_handler("start_table")
    async def start_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        logger.info(f"Пользователь {user.username} ({user.id}) вызвал /start_table.")

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        if not table.unfinished_games():
            await update.effective_message.reply_text(text="Все игры за столом сыграны")
            return

        msg = self.games.get_table_ready_string(table_id=table.table_id)
        await update.message.reply_text(msg, reply_markup=self._ready_button_reply_markup)

    @callback_query_handler(pattern=r"^RB")
    async def ready_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        chat = query.message.chat
        chat_id = chat.id
        data = query.data[2:]
        await query.answer()
        if data == "Cancel":
            await query.edit_message_text(text="Отменено")
            return
        status = data
        user = update.effective_user
        player = self.players.get_player(telegram_id=user.id)
        table = self.tables.get_table(chat_id=chat_id)
        if not table.unfinished_games():
            await query.edit_message_text(text="Все игры за столом сыграны")
            return
        if status == "Ready":
            logger.info("User %s pressed ready button", user.username)
            self.ready.set_player_ready(player.p_id)
        else:
            logger.info("User %s pressed unready button", user.username)
            self.ready.set_player_unready(player.p_id)
        msg = self.games.get_table_ready_string(table_id=table.table_id)
        await query.edit_message_text(text=msg, reply_markup=self._ready_button_reply_markup)
        ready_games = []
        for game in table.unfinished_games():
            if self.games.check_game_ready(game_id=game.game_id):
                ready_games.append(game)
        if ready_games:
            game = ready_games[0]
            player_nicks = [p.tenhou_name for p in game.players()]
            result, missed_players, success = self.tenhou_client.start_game(player_nicks)
            logger.info(
                "Запуск игры за столом %s: %s, %s, %s",
                game.table.name,
                result,
                missed_players,
                success,
            )
            if success:
                self.games.set_game_status(game.game_id, 1)
                seat_winds_names = ["東", "南", "西", "北"]
                text = f"Игра за столом {game.table.name} запущена:"
                for i, p in enumerate(game.players()):
                    text += f"\n{seat_winds_names[i]} {p.irl_name} ({p.tenhou_name})"
                    self.ready.set_player_unready(p.p_id)
                await context.bot.send_message(chat_id=self.chat, text=text)
                logger.info("Игра за столом %s успешно запущена", game.table.name)
                await query.edit_message_text(text="Приятной игры!")
            elif result == "MEMBER NOT FOUND":
                for nick in missed_players:
                    p = self.players.get_player(tenhou_name=nick)
                    self.ready.set_player_unready(p.p_id)
                msg = self.games.get_table_ready_string(table_id=table.table_id)
                await query.edit_message_text(
                    text=msg, reply_markup=self._ready_button_reply_markup
                )
                await query.message.chat.send_message(
                    text=f"Игроки не в лобби: {', '.join(missed_players)}, статус готовности обновлён."
                )
            else:
                await query.message.chat.send_message(text=f"Не удалось запустить игру: {result}")

    async def next_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return
        logger.info("User %s (%s) issued /next_table command.", user.username, user.id)
        player = self.players.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
            return
        lang = player.language
        if not self.players.set_target_tables(player.p_id, goal=1):
            await update.effective_message.reply_text(self.tr(lang, "next_table_fail"))
            return

        await update.effective_message.reply_text(self.tr(lang, "next_table_success"))

        for ep in player.player_events:
            nt = self.reveal.try_reveal(ep.event_id)
            while nt:
                await self.notify_table_revealed(context.bot, nt)
                nt = self.reveal.try_reveal(ep.event_id)

    async def all_tables_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return
        logger.info("User %s (%s) issued /all_tables command.", user.username, user.id)
        player = self.players.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
            return
        player.full_ready = 1
        self.session_manager.session.commit()
        lang = player.language
        if not self.players.set_target_tables(player.p_id, full=True):
            await update.effective_message.reply_text(self.tr(lang, "all_tables_fail"))
            return

        await update.effective_message.reply_text(self.tr(lang, "all_tables_success"))

        for ep in player.player_events:
            if ep.event.started == 0:
                continue
            nt = self.reveal.try_reveal(ep.event_id)
            while nt:
                await self.notify_table_revealed(context.bot, nt)
                nt = self.reveal.try_reveal(ep.event_id)

    @command_handler("set_time")
    async def set_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обновляет статус игры (только для администраторов)."""
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        if not context.args or len(context.args) % 3 != 0:
            await update.effective_message.reply_text(
                "Использование: /set_time <день> <время> <число игр>\n"
                "День вводить без месяца, только само число. Можно вводить день недели двумя буквами.\n"
                "Время можно указывать как с минутами, так и без. При указании с минутами, разделитель не обязателен.\n"
                "Пример: 19:30 20 числа, 4 ханчана - /set_time 20 1930 4\n"
                "17:00 вторник 2 ханчана и 19:00 среда 2 ханчана - /set_time вт 17 2 ср 19 2"
            )
            return

        games_left = len(table.unfinished_games())
        if not games_left:
            await update.effective_message.reply_text(f"Нет неначатых игр за столом {table.name}.")
            logger.info("No unstarted games at table %s.", table.name)
            return

        player = self.players.get_player(telegram_id=user.id)
        if player not in table.players():
            await update.effective_message.reply_text(
                "Указывать время можно только за своим столом."
            )
            logger.info(
                "%s attempted using set_time with args %s. Not found at table",
                user.name,
                [context.args],
            )
            return

        weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

        days = context.args[::3]
        times = context.args[1::3]
        lengths = context.args[2::3]
        start_times = []
        game_lengths = []
        success_times = []

        timezone = pytz.timezone("Europe/Moscow")
        now = datetime.datetime.now(tz=timezone)
        for day, time, games in zip(days, times, lengths, strict=False):
            games = int(games)
            if games <= 0:
                await update.effective_message.reply_text(
                    "Количество игр должно быть положительным."
                )
                logger.info("Not positive games at table %s: %s.", table.name, games)
                return
            games_left -= games
            if games_left < 0:
                await update.effective_message.reply_text("Указано больше игр, чем осталось.")
                logger.info("Too many games at table %s.", table.name)
                return

            time_digits = "".join(ch for ch in time if ch.isdigit())
            if len(time_digits) < 3:
                hour = int(time_digits)
                minute = 0
            else:
                hour = int(time_digits[:-2])
                minute = int(time_digits[-2:])

            if day.isnumeric():
                day = int(day)
                month = now.month
                year = now.year
                if day < now.day:
                    month += 1
                if month > 12:
                    month -= 12
                    year += 1
            else:
                day = day.lower()
                if day not in weekdays:
                    await update.effective_message.reply_text(f"День недели не найден {day}.")
                    logger.info("Weekday not found %s.", day)
                    return
                weekday = weekdays.index(day)
                current_weekday = now.weekday()
                shift = (weekday - current_weekday) % 7
                prospective_date = now + datetime.timedelta(days=shift)
                day = prospective_date.day
                month = prospective_date.month
                year = prospective_date.year
            try:
                prospective_start = timezone.localize(
                    datetime.datetime(year=year, month=month, day=day, hour=hour, minute=minute)
                )
                start_times.append(int(prospective_start.timestamp()))
                success_times.append(prospective_start.strftime("%d.%m %H:%M") + f" (игр: {games})")
                game_lengths.append(games)
            except ValueError:
                logger.info(
                    "%s attempted using set_time with args %s. Invalid time: %s.%s.%s %s:%s",
                    user.name,
                    [context.args],
                    year,
                    month,
                    day,
                    hour,
                    minute,
                )
                await update.effective_message.reply_text(
                    f"Время не распознано {year}.{month}.{day} {hour}:{minute}"
                )
                return
        cutoff = now + datetime.timedelta(hours=12)
        cutoff = int(cutoff.timestamp())
        self.tables.set_table_time(
            table_id=table.table_id,
            timestamps=start_times,
            reminder_cutoff=cutoff,
            lengths=game_lengths,
        )
        await update.effective_message.reply_text(
            f"Время установлено: \n{'\n'.join(success_times)}"
        )
        for time in success_times:
            await update.effective_message.chat.send_poll(
                question=time,
                options=["Согласен играть в это время"],
                allows_revoting=False,
                is_anonymous=False,
            )

    @command_handler("remove_time")
    async def remove_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        player = self.players.get_player(telegram_id=user.id)
        if player not in table.players() and not self.is_admin(user.id):
            await update.effective_message.reply_text("Удалять время можно только за своим столом.")
            logger.info(
                "%s attempted using remove_time with args %s. Not found at table",
                user.name,
                [context.args],
            )
            return
        timezone = pytz.timezone("Europe/Moscow")
        now = datetime.datetime.now(tz=timezone)
        cutoff = now + datetime.timedelta(hours=12)
        cutoff = int(cutoff.timestamp())
        self.tables.set_table_time(
            table_id=table.table_id, timestamps=[], reminder_cutoff=cutoff, lengths=[]
        )
        logger.info("%s used remove_time for table %s.", user.name, [table.table_id])
        await update.effective_message.reply_text("Время удалено.")

    @command_handler("timetable")
    async def timetable_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        assert user
        assert update.effective_message

        logger.info("User %s (%s) issued /timetable command.", user.username, user.id)
        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return

        now = datetime.datetime.now(tz=pytz.timezone("Europe/Moscow"))
        cutoff = int((now - datetime.timedelta(hours=3)).timestamp())
        known_times = self.tables.get_all_relevant_table_times(left_cutoff=cutoff)
        known_str = "".join([table_time_string(i, explicit=True) for i in known_times])
        ans = known_str
        if ans == "":
            ans = "Игр нет"
        await update.effective_message.reply_text(ans, parse_mode=ParseMode.HTML)

    @command_handler("judge_call")
    async def judge_call_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        table = self.tables.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        player = self.players.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы в системе")
            return

        try:
            link = await context.bot.create_chat_invite_link(chat_id=table.chat_id)
        except Exception as e:
            await update.effective_message.reply_text("Ошибка генерации ссылки")
            logger.error(e)
            return
        admin_list = self.players.get_admins()
        msg = [f"{player.irl_name} вызывает админа за стол {table.name}\n{link.invite_link}\n"]
        for admin in admin_list:
            msg.append(admin.dirty_mention() + " ")
        msg = "".join(msg)
        await context.bot.send_message(chat_id=self.admin_chat, text=msg)
        await update.effective_message.reply_text("Вызвал админа за стол")
