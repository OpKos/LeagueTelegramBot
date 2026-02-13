from __future__ import annotations

from .. import models
from .session import SessionProvider


class EventService:
    def __init__(self, session_provider: SessionProvider):
        self._session_provider = session_provider

    def get_event(self, event_id: int):
        return self._session_provider.session.get(models.Event, event_id)

    def get_signup_events(self):
        return (
            self._session_provider.session.query(models.Event)
            .filter(models.Event.signup == 1)
            .all()
        )

    def clear_event_players(self, event_id: int):
        self._session_provider.session.query(models.EventPlayer).filter(
            models.EventPlayer.event_id == event_id
        ).delete()
        self._session_provider.session.commit()

    def add_event_player(self, event_id: int, player_id: int, table_minimum: int = 0):
        self._session_provider.session.add(
            models.EventPlayer(event_id=event_id, p_id=player_id, table_minimum=table_minimum)
        )
        self._session_provider.session.commit()
