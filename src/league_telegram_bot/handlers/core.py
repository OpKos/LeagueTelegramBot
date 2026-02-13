from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from typing import ClassVar

from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..app_config import AppConfig
from ..services import (
    EventService,
    GameService,
    PlayerService,
    ReadyService,
    RevealService,
    SessionManager,
    TableService,
)
from ..tenhou_parser import TenhouClient
from .decorators import HandlerSpec
from .utils import ready_button_reply_markup, table_string

logger = logging.getLogger()


class BaseHandlers:
    _handler_attr: ClassVar[str] = "_handler_spec"

    def __init__(self, config: AppConfig, locales: dict[str, dict[str, str]]):
        self.session_manager = SessionManager(database_url=config.database_url)
        self.players = PlayerService(self.session_manager)
        self.tables = TableService(self.session_manager)
        self.events = EventService(self.session_manager)
        self.ready = ReadyService(self.session_manager)
        self.games = GameService(self.session_manager, ready_service=self.ready)
        self.reveal = RevealService(self.session_manager, table_service=self.tables)
        self.tenhou_client = TenhouClient(lobby=config.lobby, game_type="0009", is_enable=True)
        self.admin_ids = set(config.admin_ids)
        self.lobby = config.lobby
        self.pantheon = config.pantheon
        self.locales = locales
        self.settings_path = config.config_path
        self._ready_button_reply_markup = ready_button_reply_markup

    @classmethod
    def iter_handler_specs(cls) -> Iterable[tuple[str, HandlerSpec]]:
        seen: set[str] = set()
        for base in cls.mro():
            for name, value in base.__dict__.items():
                if name in seen:
                    continue
                seen.add(name)
                spec = getattr(value, cls._handler_attr, None)
                if spec is not None:
                    yield name, spec

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        return user_id in self.admin_ids

    def tr(self, lang: str, key: str, **kwargs) -> str:
        template = self.locales.get(key).get(lang)
        return template.format(**kwargs)

    async def notify_table_revealed(self, bot: Bot, table) -> None:
        player_names = [p.irl_name for p in table.players()]
        message = f"Раскрыт стол {table.name}!\n" + "\n".join(player_names) + "\n"
        await bot.send_message(chat_id="@kawaleague", text=message)

    async def send_game_status_message(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = datetime.datetime.now()
        tommorow: datetime.datetime = now + datetime.timedelta(days=1)
        tables = self.tables.get_unfinished_visible_tables()
        started, total = self.games.get_games_status()
        tables = [i for i in tables if i.time and now.timestamp() <= i.time < tommorow.timestamp()]
        tables.sort(key=lambda el: el.time)
        games = [table_string(table, mention=True, explicit=False) for table in tables]
        ans = f"Доброе утро, запущено игр: {started}/{total}"
        if games:
            ans += "\nСегодня играют:\n\n" + "".join(games)
        await context.bot.send_message(chat_id="@kawaleague", text=ans, parse_mode=ParseMode.HTML)
