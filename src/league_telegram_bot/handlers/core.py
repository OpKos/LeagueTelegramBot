from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import ClassVar

from telegram import Bot

from ..config.app_config import AppConfig
from ..integrations.tenhou_client import TenhouClient
from ..services import (
    EventService,
    GameService,
    PlayerService,
    ReadyService,
    RevealService,
    SessionManager,
    TableService,
)
from .decorators import HandlerSpec
from .utils import ready_button_reply_markup

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
        self.lobby = config.lobby
        self.chat = config.chat
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
        player = self.players.get_player(telegram_id=user_id)
        return player and player.is_admin

    def tr(self, lang: str, key: str, **kwargs) -> str:
        template = self.locales.get(key).get(lang)
        return template.format(**kwargs)

    async def notify_table_revealed(self, bot: Bot, table) -> None:
        player_names = [p.irl_name for p in table.players()]
        message = f"Раскрыт стол {table.name}!\n" + "\n".join(player_names) + "\n"
        await bot.send_message(chat_id=self.chat, text=message)
