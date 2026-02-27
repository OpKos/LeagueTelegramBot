from __future__ import annotations

import logging
import random

from .. import models
from .session import SessionProvider
from .table_service import TableService

logger = logging.getLogger(__name__)


class RevealService:
    def __init__(
        self, session_provider: SessionProvider, table_service: TableService | None = None
    ):
        self._session_provider = session_provider
        self._table_service = table_service or TableService(session_provider)

    def try_reveal(self, event_id: int, cache: bool = False):
        event = self._session_provider.session.get(models.Event, event_id)
        tables = [table for table in event.tables]
        random.shuffle(tables)
        tables.sort(key=lambda table: table.reveal_priority(), reverse=True)
        logger.info(f"Best table: {tables[0].table_id}, prio: {tables[0].reveal_priority()}")
        for ep in tables[0].get_event_players():
            logger.info(f"Player {ep.p_id}, visible_tables: {len(ep.visible_tables())}")
        if tables[0].reveal_priority() == 0:
            return False
        else:
            self._table_service.reveal_table(tables[0].table_id, cache=cache)
            return tables[0]
