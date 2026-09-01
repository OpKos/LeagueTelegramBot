from __future__ import annotations

from sqlalchemy import delete

from .. import models
from .session import SessionProvider


class TableService:
    def __init__(self, session_provider: SessionProvider):
        self._session_provider = session_provider

    def create_table_with_players(
        self, event_id: int, table_name: str, players: list[models.Player], deadline_group: int = 0
    ):
        table = models.Table(event_id=event_id, name=table_name, deadline_group=deadline_group)
        self._session_provider.session.add(table)
        self._session_provider.session.commit()
        for seat, player in enumerate(players):
            table_player = models.TablePlayer(table_id=table.table_id, p_id=player.p_id, seat=seat)
            self._session_provider.session.add(table_player)

        return table

    def get_table(
        self, table_id: int | None = None, table_name: str | None = None, chat_id: int | None = None
    ):
        if table_name:
            return (
                self._session_provider.session.query(models.Table)
                .filter(models.Table.name == table_name)
                .first()
            )
        if chat_id:
            return (
                self._session_provider.session.query(models.Table)
                .filter(models.Table.chat_id == chat_id)
                .first()
            )
        return self._session_provider.session.get(models.Table, table_id)

    def get_visible_table(self, table_id: int):
        table = self._session_provider.session.get(models.Table, table_id)
        if table and table.visible:
            return table
        return None

    def set_table_time(
        self, table_id: int, timestamps: list[int], lengths: list[int], reminder_cutoff: int
    ):
        table = self._session_provider.session.get(models.Table, table_id)
        if table is None:
            return False
        self._session_provider.session.execute(
            delete(models.TableTime).where(models.TableTime.table_id == table_id)
        )
        time_objects = []
        for timestamp, games in zip(timestamps, lengths, strict=False):
            need_reminder = 1
            if timestamp < reminder_cutoff:
                need_reminder = 0
            time_objects.append(
                models.TableTime(
                    table_id=table_id, time=timestamp, need_reminder=need_reminder, games=games
                )
            )
        self._session_provider.session.add_all(time_objects)
        self._session_provider.session.commit()
        return True

    def get_all_tables(self):
        return self._session_provider.session.query(models.Table).all()

    def get_visible_tables(self):
        return (
            self._session_provider.session.query(models.Table)
            .filter(models.Table.visible > 0)
            .all()
        )

    def get_unfinished_visible_tables(self):
        tables = self._session_provider.session.query(models.Table).all()
        return [
            table
            for table in tables
            if table.unfinished_games and table.visible and table.event.started
        ]

    def get_all_relevant_table_times(self, left_cutoff=None, right_cutoff=None):
        times = (
            self._session_provider.session.query(models.TableTime)
            .join(models.TableTime.table)
            .join(models.Table.event)
            .filter(models.Event.started == 1)
        )
        if left_cutoff:
            times = times.filter(models.TableTime.time >= left_cutoff)
        if right_cutoff:
            times = times.filter(models.TableTime.time <= right_cutoff)
        times_list = times.order_by(models.TableTime.time, models.TableTime.table_id).all()
        return times_list

    def reveal_table(self, table_id: int, cache: bool = False):
        table = self._session_provider.session.get(models.Table, table_id)
        if not table or table.visible:
            return False
        table.visible = 1
        if cache:
            table.reveal_cached = 1
        self._session_provider.session.commit()
        return True

    def get_event_cached_tables(self, event_id: int):
        return (
            self._session_provider.session.query(models.Table)
            .filter(models.Table.event_id == event_id)
            .filter(models.Table.reveal_cached == 1)
            .all()
        )

    def set_table_chat(self, table_id: int, chat_id: int):
        table = self._session_provider.session.get(models.Table, table_id)
        table.chat_id = chat_id
        self._session_provider.session.commit()

    def get_table_first_game(self, table_id: int):
        table = self._session_provider.session.get(models.Table, table_id)
        games = table.unfinished_games()
        if games:
            return games[0]
        else:
            return None
