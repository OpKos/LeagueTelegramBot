from __future__ import annotations

import logging

from .. import models
from .session import SessionProvider

logger = logging.getLogger(__name__)


class PlayerService:
    def __init__(self, session_provider: SessionProvider):
        self._session_provider = session_provider

    def register_player(self, telegram_id: int, telegram_name: str | None, tenhou_id: str):
        player = models.Player(
            telegram_id=telegram_id, telegram_name=telegram_name, tenhou_name=tenhou_id
        )
        self._session_provider.session.add(player)
        self._session_provider.session.commit()

    def fill_player_data(self, p_id: int, irl_name: str):
        player = self._session_provider.session.get(models.Player, p_id)
        assert player
        player.irl_name = irl_name
        self._session_provider.session.commit()

    def update_tenhou_nick(self, p_id: int, tenhou_name: str):
        player = self._session_provider.session.get(models.Player, p_id)
        assert player
        player.tenhou_name = tenhou_name
        self._session_provider.session.commit()

    def get_player(
        self,
        p_id: int | None = None,
        telegram_id: int | None = None,
        telegram_name: str | None = None,
        tenhou_name: str | None = None,
    ):
        query = self._session_provider.session.query(models.Player)
        if p_id:
            query = query.filter(models.Player.p_id == p_id)
        if telegram_id:
            query = query.filter(models.Player.telegram_id == telegram_id)
        if telegram_name:
            query = query.filter(models.Player.telegram_name == telegram_name)
        if tenhou_name:
            query = query.filter(models.Player.tenhou_name == tenhou_name)
        return query.first()

    def set_target_tables(self, p_id: int, goal: int = 1, full: bool = False):
        player = self._session_provider.session.get(models.Player, p_id)
        if player:
            eps = player.player_events
            for ep in eps:
                logger.info(f"Setting target tables for event_player {ep.event_id} {ep.p_id}")
                if ep.event.started == 0:
                    continue
                if full:
                    ep.table_minimum = len(ep.tables())
                    logger.info(f"Target set {len(ep.tables())}")
                else:
                    ep.table_minimum = len(ep.visible_tables()) + goal
                    logger.info(f"Target set {len(ep.visible_tables()) + goal}")
            self._session_provider.session.commit()
            return True
        self._session_provider.session.commit()
        return False

    def set_language(self, p_id: int, lang: str):
        player = self._session_provider.session.get(models.Player, p_id)
        if player:
            player.language = lang
            self._session_provider.session.commit()
            return True
        return False
