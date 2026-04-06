from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from google.protobuf.json_format import MessageToDict
from twirp.context import Context
from twirp.exceptions import TwirpServerException

from .proto import atoms_pb2, frey_pb2, mimir_pb2  # noqa: F401
from .proto.frey_client_twirp import FreyClient
from .proto.mimir_client_twirp import MimirClient

_ = atoms_pb2  # prevent ruff from deleting import


class PantheonClient:
    def __init__(
        self,
        base_url: str,
        *,
        event_id: int | None = None,
        person_id: int | None = None,
        auth_token: str | None = None,
        server_path_prefix: str = "/v2",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url
        self._event_id = event_id
        self._person_id = person_id
        self._auth_token = auth_token
        self._server_path_prefix = server_path_prefix
        self._timeout = timeout
        self._mimir = MimirClient(base_url)
        self._frey = FreyClient(base_url)

    def send_game_log(self, link: str) -> dict[str, Any]:
        if not link:
            raise ValueError("link must be a non-empty string")
        if self._event_id is None:
            raise ValueError("event_id must be set to send game logs")

        payload = mimir_pb2.GamesAddOnlineReplayPayload(event_id=self._event_id, link=link)
        try:
            response = self._mimir.AddOnlineReplay(
                ctx=self._build_ctx(),
                request=payload,
                server_path_prefix=self._server_path_prefix,
                timeout=self._timeout,
            )
            return {
                "ok": True,
                "game": _to_dict(response.game),
                "players": [_to_dict(player) for player in response.players],
            }
        except TwirpServerException as exc:
            return {
                "ok": False,
                "error": exc.message,
                "code": str(exc.code),
                "meta": exc.meta,
            }
        except Exception as exc:  # pragma: no cover - network/transport errors
            return {"ok": False, "error": str(exc)}

    def get_rating_table(
        self,
        *,
        event_id_list: Iterable[int] | None = None,
        order_by: str | None = None,
        order: str | None = None,
        only_min_games: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        if event_id_list is None:
            if self._event_id is None:
                raise ValueError("event_id_list must be provided if event_id is not set")
            event_id_list = [self._event_id]

        payload = mimir_pb2.EventsGetRatingTablePayload(event_id_list=list(event_id_list))
        if order_by is not None:
            payload.order_by = order_by
        if order is not None:
            payload.order = order
        if only_min_games is not None:
            payload.only_min_games = only_min_games
        if date_from is not None:
            payload.date_from = date_from
        if date_to is not None:
            payload.date_to = date_to

        try:
            response = self._mimir.GetRatingTable(
                ctx=self._build_ctx(),
                request=payload,
                server_path_prefix=self._server_path_prefix,
                timeout=self._timeout,
            )
            return {
                "ok": True,
                "players": [_to_dict(entry) for entry in response.list],
            }
        except TwirpServerException as exc:
            return {
                "ok": False,
                "error": exc.message,
                "code": str(exc.code),
                "meta": exc.meta,
            }
        except Exception as exc:  # pragma: no cover - network/transport errors
            return {"ok": False, "error": str(exc)}

    def get_person_by_tenhou(self, nickname: str):
        if not nickname:
            raise ValueError("nickname must be a non-empty string")

        payload = frey_pb2.PersonsFindByTenhouIdsPayload(ids=[nickname])
        try:
            response = self._frey.FindByTenhouIds(
                ctx=self._build_ctx(),
                request=payload,
                server_path_prefix=self._server_path_prefix,
                timeout=self._timeout,
            )
            return {
                "ok": True,
                "people": [_to_dict(people) for people in response.people],
            }
        except TwirpServerException as exc:
            return {
                "ok": False,
                "error": exc.message,
                "code": str(exc.code),
                "meta": exc.meta,
            }
        except Exception as exc:  # pragma: no cover - network/transport errors
            return {"ok": False, "error": str(exc)}

    def _build_ctx(self) -> Context:
        headers: dict[str, Any] = {}
        if self._event_id is not None:
            headers["x-current-event-id"] = str(self._event_id)
        if self._person_id is not None:
            headers["x-current-person-id"] = str(self._person_id)
        if self._auth_token is not None:
            headers["x-auth-token"] = self._auth_token
        return Context(headers=headers or None)


def _to_dict(message: Any) -> dict[str, Any]:
    return MessageToDict(message, preserving_proto_field_name=True)
