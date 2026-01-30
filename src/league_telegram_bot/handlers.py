from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Literal

import pytz
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .app_config import AppConfig
from .event_portal_update import event_portal_update
from .seating_functions import create_seating
from .seating_image import create_seating_image
from .sqlalchemy_parser import SqlParser
from .tenhou_parser import TenhouClient

ready_button_reply_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Готов", callback_data="RBReady"),
            InlineKeyboardButton("❌ Не готов", callback_data="RBUnready"),
            InlineKeyboardButton("Отмена", callback_data="RBCancel"),
        ]
    ]
)

logger = logging.getLogger()


def timestring_from_timestamp(timestamp: int, weekday: bool = False, day: bool = False) -> str:
    timezone = pytz.timezone("Europe/Moscow")
    res = ""
    weekdays = [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]
    date = datetime.datetime.fromtimestamp(timestamp, tz=timezone)
    if weekday:
        res += weekdays[date.weekday()] + " "
    if day:
        res += f"{date.strftime('%d.%m')} "
    res += f"{date.strftime('%H:%M')}"
    return res


def table_string(table, mention: bool = False, explicit: bool = True) -> str:
    ans = (
        timestring_from_timestamp(table.time, weekday=explicit, day=explicit)
        + " - "
        + f"Стол {table.name}:\n"
    )
    for i, player in enumerate(table.players()):
        if mention:
            ans += player.clean_mention()
        else:
            ans += player.irl_name
        if i % 2 == 0:
            ans += ", "
        elif i < len(table.players()) - 1:
            ans += ",\n"
        else:
            ans += ".\n\n"
    return ans


@dataclass(frozen=True)
class HandlerSpec:
    kind: Literal["command", "callback_query"]
    commands: tuple[str, ...] = ()
    pattern: str | None = None


def command_handler(*commands: str):
    def decorator(func):
        func._handler_spec = HandlerSpec(kind="command", commands=commands)
        return func

    return decorator


def callback_query_handler(pattern: str):
    def decorator(func):
        func._handler_spec = HandlerSpec(kind="callback_query", pattern=pattern)
        return func

    return decorator


class BotHandlers:
    _handler_attr: ClassVar[str] = "_handler_spec"

    def __init__(self, config: AppConfig, locales: dict[str, dict[str, str]]):
        self.db = SqlParser(database_url=config.database_url)
        self.tenhou_client = TenhouClient(lobby=config.lobby, game_type="0009", is_enable=True)
        self.admin_ids = set(config.admin_ids)
        self.lobby = config.lobby
        self.pantheon = config.pantheon
        self.locales = locales
        self.settings_path = config.config_path
        self._ready_button_reply_markup = ready_button_reply_markup

    @classmethod
    def iter_handler_specs(cls) -> Iterable[tuple[str, HandlerSpec]]:
        for name, value in cls.__dict__.items():
            spec = getattr(value, cls._handler_attr, None)
            if spec is not None:
                yield name, spec

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        return user_id in self.admin_ids

    def tr(self, lang: str, key: str, **kwargs) -> str:
        template = self.locales.get(key).get(lang)
        return template.format(**kwargs)

    @command_handler("register")
    async def register_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Регистрирует нового игрока в системе.

        Args:
            update (Update): Объект Update от Telegram.
            context (ContextTypes.DEFAULT_TYPE): Контекст выполнения команды.
        """
        user = update.effective_user
        args = context.args
        assert update.effective_message
        assert user
        logger.info(
            "User %s (%s) issued /register command with args: %s", user.username, user.id, args
        )

        if not args or len(args) != 1:
            logger.info(
                "User %s (%s) used /register with invalid args: %s", user.username, user.id, args
            )
            await update.effective_message.reply_text(self.tr("en", "register_invalid_args"))
            return

        tenhou_name = args[0]

        # Проверяем, не зарегистрирован ли уже пользователь
        player = self.db.get_player(telegram_id=user.id)
        if player:
            lang = player.language
            old_name = player.tenhou_name
            if old_name == tenhou_name:
                await update.effective_message.reply_text(
                    self.tr(lang, "already_registered", old=old_name, new=tenhou_name)
                )
            else:
                self.db.update_tenhou_nick(p_id=player.p_id, tenhou_name=tenhou_name)
                await update.effective_message.reply_text(
                    self.tr(lang, "nick_change", old=old_name, new=tenhou_name)
                )
            logger.info(
                "User %s (%s) already registered with Tenhou ID %s.",
                user.username,
                user.id,
                tenhou_name,
            )
            return

        # Регистрируем нового игрока
        self.db.register_player(
            telegram_id=user.id, telegram_name=user.username, tenhou_id=tenhou_name
        )
        await update.effective_message.reply_text(
            self.tr("ru", "register_success")
            + "\n"
            + self.tr("en", "register_success")
            + "\nUse /set_language to change your language"
        )
        logger.info(
            "User %s (%s) registered with Tenhou ID %s.", user.username, user.id, tenhou_name
        )

    @command_handler("start_table")
    async def start_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        logger.info(f"Пользователь {user.username} ({user.id}) вызвал /start_table.")

        table = self.db.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        game = self.db.get_table_first_game(table_id=table.table_id)
        if not game:
            await update.effective_message.reply_text(f"Нет неначатых игр за столом {table.name}")
            logger.info(f"Нет игр за столом {table.name}")
            return

        game_string = self.db.get_game_string(game_id=game.game_id)
        await update.message.reply_text(game_string, reply_markup=self._ready_button_reply_markup)

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
        player = self.db.get_player(telegram_id=user.id)
        table = self.db.get_table(chat_id=chat_id)
        game = self.db.get_table_first_game(table_id=table.table_id)
        if not game:
            await query.edit_message_text(text="Все игры за столом сыграны")
            return
        if status == "Ready":
            logger.info("User %s pressed ready button", user.username)
            self.db.set_player_ready(player.p_id)
        else:
            logger.info("User %s pressed unready button", user.username)
            self.db.set_player_unready(player.p_id)
        msg = self.db.get_game_string(game_id=game.game_id)
        await query.edit_message_text(text=msg, reply_markup=self._ready_button_reply_markup)
        rdy = self.db.check_game_ready(game_id=game.game_id)
        if rdy:
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
                self.db.set_game_status(game.game_id, 1)
                seat_winds_names = ["東", "南", "西", "北"]
                text = f"Игра за столом {game.table.name} запущена:"
                for i, p in enumerate(game.players()):
                    text += f"\n{seat_winds_names[i]} {p.irl_name} ({p.tenhou_name})"
                    self.db.set_player_unready(p.p_id)
                await context.bot.send_message(chat_id="@kawaleague", text=text)
                logger.info("Игра за столом %s успешно запущена", game.table.name)
                await query.edit_message_text(text="Приятной игры!")
            elif result == "MEMBER NOT FOUND":
                for nick in missed_players:
                    p = self.db.get_player(tenhou_name=nick)
                    self.db.set_player_unready(p.p_id)
                msg = self.db.get_game_string(game_id=game.game_id)
                await query.edit_message_text(
                    text=msg, reply_markup=self._ready_button_reply_markup
                )
                await query.message.chat.send_message(
                    text=f"Игроки не в лобби: {', '.join(missed_players)}, статус готовности обновлён."
                )
            else:
                await query.message.chat.send_message(text=f"Не удалось запустить игру: {result}")

    @command_handler("next_table")
    async def next_table_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return
        logger.info("User %s (%s) issued /next_table command.", user.username, user.id)
        player = self.db.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
            return
        lang = player.language
        if not self.db.set_target_tables(player.p_id, goal=1):
            await update.effective_message.reply_text(self.tr(lang, "next_table_fail"))
            return

        await update.effective_message.reply_text(self.tr(lang, "next_table_success"))

        for ep in player.player_events:
            nt = self.db.try_reveal(ep.event_id)
            while nt:
                await self.notify_table_revealed(context.bot, nt)
                nt = self.db.try_reveal(ep.event_id)

    @command_handler("all_tables")
    async def all_tables_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if update.effective_message.chat.type != "private":
            await update.effective_message.reply_text(
                "Эта команда доступна только в личных сообщениях с ботом."
            )
            return
        logger.info("User %s (%s) issued /all_tables command.", user.username, user.id)
        player = self.db.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы в системе.")
            return
        player.full_ready = 1
        self.db.session.commit()
        lang = player.language
        if not self.db.set_target_tables(player.p_id, full=True):
            await update.effective_message.reply_text(self.tr(lang, "all_tables_fail"))
            return

        await update.effective_message.reply_text(self.tr(lang, "all_tables_success"))

        for ep in player.player_events:
            if ep.event.started == 0:
                continue
            nt = self.db.try_reveal(ep.event_id)
            while nt:
                await self.notify_table_revealed(context.bot, nt)
                nt = self.db.try_reveal(ep.event_id)

    async def notify_table_revealed(self, bot: Bot, table) -> None:
        player_names = [p.irl_name for p in table.players()]
        message = f"Раскрыт стол {table.name}!\n" + "\n".join(player_names) + "\n"
        await bot.send_message(chat_id="@kawaleague", text=message)

    @command_handler("set_time")
    async def set_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обновляет статус игры (только для администраторов)."""
        user = update.effective_user

        table = self.db.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        if not context.args or len(context.args) != 2:
            await update.effective_message.reply_text(
                "Использование: /set_time <день> <время>\n"
                "День вводить без месяца, только само число.\n"
                "Время можно указывать как с минутами, так и без. При указании с минутами, разделитель не обязателен.\n"
                "Пример: 19:30 20 числа - /set_time 20 1930\n"
                "17:00 10 числа - /set_time 10 17"
            )
            return

        day, chosen_time = context.args

        games = table.unfinished_games
        if not games:
            await update.effective_message.reply_text(f"Нет неначатых игр за столом {table.name}.")
            logger.info("No unstarted games at table %s.", table.name)
            return

        player = self.db.get_player(telegram_id=user.id)
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
        day = int(day)
        timezone = pytz.timezone("Europe/Moscow")
        now = datetime.datetime.now(tz=timezone)
        time_digits = "".join(ch for ch in chosen_time if ch.isdigit())
        if len(time_digits) < 3:
            hour = int(time_digits)
            minute = 0
        else:
            hour = int(time_digits[:-2])
            minute = int(time_digits[-2:])
        month = now.month
        year = now.year
        if day < now.day:
            month += 1
        if month > 12:
            month -= 12
            year += 1
        try:
            prospective_start = timezone.localize(
                datetime.datetime(year=year, month=month, day=day, hour=hour, minute=minute)
            )
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
        self.db.set_table_time(
            table_id=table.table_id, timestamp=int(prospective_start.timestamp())
        )
        logger.info(
            "%s used set_time with args %s. Time set: %s.%s.%s %s:%s",
            user.name,
            [context.args],
            year,
            month,
            day,
            hour,
            minute,
        )
        await update.effective_message.reply_text(
            f"Время установлено: {prospective_start.strftime('%d.%m %H:%M')}"
        )

    @command_handler("remove_time")
    async def remove_time_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обновляет статус игры (только для администраторов)."""
        user = update.effective_user

        table = self.db.get_table(chat_id=update.effective_message.chat_id)
        if not table:
            await update.effective_message.reply_text(
                "У чата не указан стол, используйте /set_chat"
            )
            return

        player = self.db.get_player(telegram_id=user.id)
        if player not in table.players() and not self.is_admin(user.id):
            await update.effective_message.reply_text("Удалять время можно только за своим столом.")
            logger.info(
                "%s attempted using remove_time with args %s. Not found at table",
                user.name,
                [context.args],
            )
            return
        self.db.set_table_time(table_id=table.table_id, timestamp=0)
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
        cutoff = now - datetime.timedelta(hours=3)
        tables = self.db.get_unfinished_visible_tables()
        tables.sort(key=lambda el: el.table_id)
        unknown_ids = [
            table.name for table in tables if not table.time or table.time < cutoff.timestamp()
        ]
        known = [table for table in tables if table.time and table.time >= cutoff.timestamp()]
        known.sort(key=lambda el: el.time)
        known_str = "".join([table_string(i, explicit=True) for i in known])
        unknown_str = ", ".join(map(str, sorted(unknown_ids)))
        ans = known_str
        if unknown_str:
            ans += "Время неизвестно: " + unknown_str
        if ans == "":
            ans = "Игр нет"
        await update.effective_message.reply_text(ans, parse_mode=ParseMode.HTML)

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

        success = self.db.set_game_status(game_id, status)
        if success:
            status_text = "started" if status == "1" else "not started"
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

        if self.db.reveal_table(table_id):
            table = self.db.get_table(table_id)
            assert table
            await self.notify_table_revealed(context.bot, table)
            await update.effective_message.reply_text(f"Стол {table_id} раскрыт")
        else:
            await update.effective_message.reply_text("Ошибка раскрытия стола")

    async def send_game_status_message(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.datetime.now()
        tommorow: datetime.datetime = now + datetime.timedelta(days=1)
        tables = self.db.get_unfinished_visible_tables()
        started, total = self.db.get_games_status()
        tables = [i for i in tables if i.time and now.timestamp() <= i.time < tommorow.timestamp()]
        tables.sort(key=lambda el: el.time)
        games = [table_string(table, mention=True, explicit=False) for table in tables]
        ans = f"Доброе утро, запущено игр: {started}/{total}"
        if games:
            ans += "\nСегодня играют:\n\n" + "".join(games)
        await context.bot.send_message(chat_id="@kawaleague", text=ans, parse_mode=ParseMode.HTML)

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

    @command_handler("start_status_message")
    async def start_status_message_command(
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

        chat_id = update.effective_message.chat_id
        tz = pytz.timezone("Europe/Moscow")
        callback_time = datetime.time(hour=10, minute=0, tzinfo=tz)
        context.job_queue.run_daily(
            self.send_game_status_message,
            time=callback_time,
            chat_id="@kawaleague",
            name=str(chat_id),
        )
        text = "Timer successfully set!"
        await update.effective_message.reply_text(text)

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
            player = self.db.get_player(telegram_id=user.id)

        elif len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /player_info <telegram_name>")
            return
        else:
            telegram_name = context.args[0]
            if telegram_name[0] == "@":
                telegram_name = telegram_name[1:]
            player = self.db.get_player(telegram_name=telegram_name)

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
        table = self.db.get_table(table_id)
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
        await update.effective_message.reply_text(
            self.pantheon,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

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

        if self.db.reload_session():
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

    @command_handler("set_language")
    async def set_language(self, update, context) -> None:
        user_id = update.effective_user.id
        if not context.args or context.args[0] not in ("ru", "en"):
            await update.message.reply_text("Usage: /set_language ru|en")
            return

        lang = context.args[0]
        p_id = self.db.get_player(telegram_id=user_id).p_id

        if not p_id:
            await update.message.reply_text(self.tr(lang, "not_registered"))
            return

        self.db.set_language(p_id, lang)
        await update.message.reply_text(self.tr(lang, "language_set"))

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

        events = self.db.get_signup_events()

        for event in events:
            self.db.clear_event_players(event.event_id)
            res = event_portal_update(self.db, event)
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

        event = self.db.get_event(int(context.args[0]))
        logger.info(
            "Admin %s (%s) created seating for event %s", user.username, user.id, event.event_id
        )
        create_seating(self.db, event)
        await update.effective_message.reply_text("Seating created")

    @command_handler("reveal_new_tables")
    async def reveal_new_tables(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user

        if not self.is_admin(user.id):
            await update.effective_message.reply_text(
                "Эта команда доступна только администраторам."
            )
            return

        event = self.db.get_event(int(context.args[0]))
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
        nt = self.db.try_reveal(event.event_id, cache=True)
        while nt:
            nt = self.db.try_reveal(event.event_id, cache=True)
        event.global_minimum = new_min
        nt = self.db.try_reveal(event.event_id, cache=True)
        while nt:
            nt = self.db.try_reveal(event.event_id, cache=True)
        cached = self.db.get_event_cached_tables(event_id=event.event_id)
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

        event = self.db.get_event(int(context.args[0]))
        logger.info(
            "Admin %s (%s) requested image for event %s", user.username, user.id, event.event_id
        )
        create_seating_image(self.db, event)
        with open("seating.png", "rb") as image_file:
            await update.effective_message.reply_document(document=image_file)

    @callback_query_handler(pattern=r"^TC")
    async def chat_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        chat = query.message.chat
        chat_id = chat.id
        data = query.data[2:]
        if data == "Cancel":
            await query.answer()
            await query.edit_message_text(text="Отменено")
        table_name = data
        table = self.db.get_table(table_name=table_name)
        self.db.set_table_chat(table.table_id, chat_id)
        await query.answer()
        await query.edit_message_text(text=f"Выбран стол {table_name}")
        try:
            await chat.set_title(f"Кава стол {table_name}")
        except Exception as e:
            logger.error(e)
        try:
            link = await context.bot.create_chat_invite_link(chat_id=chat_id)
        except Exception as e:
            await chat.send_message("Ошибка.")
            logger.error(e)
            return
        for player in table.players():
            member = await chat.get_member(player.telegram_id)
            logger.info(member)
            if str(member.status).lower() == "left":
                try:
                    await context.bot.send_message(
                        chat_id=player.telegram_id,
                        text=f"Чат стола {table_name}:\n{link.invite_link}",
                    )
                    await chat.send_message(f"Ссылка отправлена {player.irl_name}.")
                except Exception as e:
                    await chat.send_message(f"Не удалось пригласить игрока {player.irl_name}.")
                    logger.error(e)

    @command_handler("set_chat")
    async def set_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message.chat.type != "supergroup":
            await update.effective_message.reply_text(
                "Доступно только в супергруппах. (В настройках группы включите историю чата для новых участников)"
            )
            return
        member = await update.effective_message.chat.get_member(context.bot.id)
        if member.status != "administrator":
            await update.effective_message.reply_text(
                "Сначала назначьте боту права администратора."
            )
            return
        user = update.effective_user
        logger.info(
            "Пользователь %s (%s) вызвал /set_chat в чате %s",
            user.username,
            user.id,
            update.effective_message.chat.id,
        )
        t = self.db.get_table(chat_id=update.effective_message.chat.id)
        if t:
            await update.effective_message.reply_text(f"У этого чата уже есть стол {t.name}.")
            return
        player = self.db.get_player(telegram_id=user.id)
        if not player:
            await update.effective_message.reply_text("Вы не зарегистрированы.")
            return
        table_names = [table.name for table in player.visible_tables() if table.chat_id == 0]
        if not table_names:
            await update.effective_message.reply_text("У вас нет нераскрытых столов.")
            return
        keyboard = [
            [InlineKeyboardButton(t_n, callback_data="TC" + t_n)] for t_n in table_names
        ] + [[InlineKeyboardButton("Отмена", callback_data="TCCancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите стол", reply_markup=reply_markup)
