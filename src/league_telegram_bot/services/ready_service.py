from __future__ import annotations

from .. import models
from .session import SessionProvider


class ReadyService:
    def __init__(self, session_provider: SessionProvider):
        self._session_provider = session_provider

    def check_player_ready(self, p_id: int):
        rp = self._session_provider.session.get(models.ReadyPlayer, p_id)
        return bool(rp)

    def set_player_ready(self, p_id: int):
        player = self._session_provider.session.get(models.Player, p_id)
        if player and not self.check_player_ready(p_id):
            rp = models.ReadyPlayer(p_id=p_id)
            self._session_provider.session.add(rp)
            self._session_provider.session.commit()
        return False

    def set_player_unready(self, p_id: int):
        self._session_provider.session.query(models.ReadyPlayer).filter(
            models.ReadyPlayer.p_id == p_id
        ).delete()
        self._session_provider.session.commit()
        return True
