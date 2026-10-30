from __future__ import annotations

import datetime

from .. import models, time_utils
from .session import SessionProvider


class ReadyService:
    def __init__(self, session_provider: SessionProvider):
        self._session_provider = session_provider

    def check_player_ready(self, p_id: int):
        rp = self._session_provider.session.get(models.ReadyPlayer, p_id)
        if rp is None:
            return False
        return time_utils.is_within_time_window(rp.timestamp, datetime.timedelta(minutes=30))

    def set_player_ready(self, p_id: int):
        player = self._session_provider.session.get(models.Player, p_id)
        if player:
            rp = self._session_provider.session.get(models.ReadyPlayer, p_id)
            if rp is None:
                rp = models.ReadyPlayer(p_id=p_id, timestamp=time_utils.current_timestamp())
            else:
                rp.timestamp = time_utils.current_timestamp()
            self._session_provider.session.add(rp)
            self._session_provider.session.commit()
        return False

    def set_player_unready(self, p_id: int):
        self._session_provider.session.query(models.ReadyPlayer).filter(
            models.ReadyPlayer.p_id == p_id
        ).delete()
        self._session_provider.session.commit()
        return True
