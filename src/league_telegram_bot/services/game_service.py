from __future__ import annotations

from .. import models
from .ready_service import ReadyService
from .session import SessionProvider


class GameService:
    def __init__(
        self, session_provider: SessionProvider, ready_service: ReadyService | None = None
    ):
        self._session_provider = session_provider
        self._ready_service = ready_service or ReadyService(session_provider)

    def create_game_with_players(self, table_id: int, players: list[models.Player]):
        game = models.Game(table_id=table_id)
        self._session_provider.session.add(game)
        self._session_provider.session.commit()
        for seat, player in enumerate(players):
            game_player = models.GamePlayer(game_id=game.game_id, p_id=player.p_id, seat=seat)
            self._session_provider.session.add(game_player)
        self._session_provider.session.commit()

    def get_all_games(self):
        return self._session_provider.session.query(models.Game).all()

    def set_game_status(self, game_id: int, status: int):
        game = self._session_provider.session.get(models.Game, game_id)
        assert game
        game.started = status
        self._session_provider.session.commit()
        return True

    def replace_game_player(self, game_id: int, seat: int, player_id: int):
        game_player = (
            self._session_provider.session.query(models.GamePlayer)
            .where(models.GamePlayer.game_id == game_id)
            .where(models.GamePlayer.seat == seat)
            .one()
        )
        game_player.p_id = player_id
        self._session_provider.session.commit()
        return True

    def get_games_status(self):
        started = (
            self._session_provider.session.query(models.Game)
            .filter(models.Game.started != 0)
            .count()
        )
        total = self._session_provider.session.query(models.Game).count()
        return started, total

    def get_game(self, game_id: int):
        return self._session_provider.session.get(models.Game, game_id)

    def get_game_string(self, game_id: int):
        game = self._session_provider.session.get(models.Game, game_id)
        ans = []
        for player in game.players():
            res = "✅ " if self._ready_service.check_player_ready(player.p_id) else "❌ "
            res += player.irl_name
            ans.append(res)
        return "\n".join(ans)

    def get_table_ready_string(self, table_id: int):
        table = self._session_provider.session.get(models.Table, table_id)
        ans = []
        for player in table.get_unfinished_players():
            res = "✅ " if self._ready_service.check_player_ready(player.p_id) else "❌ "
            res += player.irl_name
            ans.append(res)
        return "\n".join(ans)

    def check_game_ready(self, game_id: int):
        game = self._session_provider.session.get(models.Game, game_id)
        return all(self._ready_service.check_player_ready(player.p_id) for player in game.players())
