import logging
import random

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import models, settings

logger = logging.getLogger(__name__)


class SqlParser:
    def __init__(self, database_url: str | None = None):
        if database_url is None:
            database_url = settings.build_database_url(settings.load_database_settings())
        logger.info(database_url)
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def __del__(self):
        """Clean up the session when the parser is destroyed"""
        if hasattr(self, "session"):
            self.session.close()

    def reload_session(self):
        """Close and reopen a fresh session"""
        self.session.close()
        self.session = self.Session()
        return True

    def register_player(self, telegram_id: int, telegram_name: str | None, tenhou_id: str):
        player = models.Player(
            telegram_id=telegram_id, telegram_name=telegram_name, tenhou_name=tenhou_id
        )
        self.session.add(player)
        self.session.commit()

    def create_table_with_players(
        self, event_id: int, table_name: str, players: list[models.Player]
    ):
        table = models.Table(event_id=event_id, name=table_name)
        self.session.add(table)
        self.session.commit()
        for seat, player in enumerate(players):
            table_player = models.TablePlayer(table_id=table.table_id, p_id=player.p_id, seat=seat)
            self.session.add(table_player)

        return table

    def create_game_with_players(self, table_id: int, players: list[models.Player]):
        game = models.Game(table_id=table_id)
        self.session.add(game)
        self.session.commit()
        for seat, player in enumerate(players):
            game_player = models.GamePlayer(game_id=game.game_id, p_id=player.p_id, seat=seat)
            self.session.add(game_player)
        self.session.commit()

    def fill_player_data(self, p_id: int, irl_name: str):
        player = self.session.get(models.Player, p_id)
        assert player
        player.irl_name = irl_name
        self.session.commit()

    def update_tenhou_nick(self, p_id: int, tenhou_name: str):
        player = self.session.get(models.Player, p_id)
        assert player
        player.tenhou_name = tenhou_name
        self.session.commit()

    def get_player(self, p_id=None, telegram_id=None, telegram_name=None, tenhou_name=None):
        query = self.session.query(models.Player)
        if p_id:
            query = query.filter(models.Player.p_id == p_id)
        if telegram_id:
            query = query.filter(models.Player.telegram_id == telegram_id)
        if telegram_name:
            query = query.filter(models.Player.telegram_name == telegram_name)
        if tenhou_name:
            query = query.filter(models.Player.tenhou_name == tenhou_name)
        return query.first()

    def get_all_games(self):
        return self.session.query(models.Game).all()

    def set_game_status(self, game_id: int, status: int):
        game = self.session.get(models.Game, game_id)
        assert game
        game.started = status
        self.session.commit()

    def get_games_status(self):
        started = self.session.query(models.Game).filter(models.Game.started != 0).count()
        total = self.session.query(models.Game).count()
        return started, total

    def get_game(self, game_id: int):
        return self.session.get(models.Game, game_id)

    def get_table(self, table_id: int = None, table_name: str = None, chat_id: int = None):
        if table_name:
            return self.session.query(models.Table).filter(models.Table.name == table_name).first()
        if chat_id:
            return self.session.query(models.Table).filter(models.Table.chat_id == chat_id).first()
        return self.session.get(models.Table, table_id)

    def get_event(self, event_id: int):
        return self.session.get(models.Event, event_id)

    def get_visible_table(self, table_id: int):
        table = self.session.get(models.Table, table_id)
        if table and table.visible:
            return table
        return None

    def set_table_time(self, table_id: int, timestamp: int):
        table = self.session.get(models.Table, table_id)
        if table is None:
            return False
        table.time = timestamp
        self.session.commit()
        return True

    def get_all_tables(self):
        return self.session.query(models.Table).all()

    def get_visible_tables(self):
        return self.session.query(models.Table).filter(models.Table.visible > 0).all()

    def get_unfinished_visible_tables(self):
        tables = self.session.query(models.Table).all()
        return [table for table in tables if table.unfinished_games and table.visible]

    def set_target_tables(self, p_id: int, goal: int = 1, full: bool = False):
        player = self.session.get(models.Player, p_id)
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
            self.session.commit()
            return True
        self.session.commit()
        return False

    def reveal_table(self, table_id: int, cache: bool = False):
        table = self.session.get(models.Table, table_id)
        if not table or table.visible:
            return False
        table.visible = 1
        if cache:
            table.reveal_cached = 1
        self.session.commit()
        return True

    def try_reveal(self, event_id: int, cache: bool = False):
        event = self.get_event(event_id)
        tables = [table for table in event.tables]
        random.shuffle(tables)
        tables.sort(key=lambda table: table.reveal_priority(), reverse=True)
        logger.info(f"Best table: {tables[0].table_id}, prio: {tables[0].reveal_priority()}")
        for ep in tables[0].get_event_players():
            logger.info(f"Player {ep.p_id}, visible_tables: {len(ep.visible_tables())}")
        if tables[0].reveal_priority() == 0:
            return False
        else:
            self.reveal_table(tables[0].table_id, cache=cache)
            return tables[0]

    def set_language(self, p_id: int, lang: str):
        player = self.session.get(models.Player, p_id)
        if player:
            player.language = lang
            self.session.commit()
            return True
        return False

    def check_player_ready(self, p_id: int):
        rp = self.session.get(models.ReadyPlayer, p_id)
        return bool(rp)

    def set_player_ready(self, p_id: int):
        player = self.session.get(models.Player, p_id)
        if player and not self.check_player_ready(p_id):
            rp = models.ReadyPlayer(p_id=p_id)
            self.session.add(rp)
            self.session.commit()
        return False

    def set_player_unready(self, p_id: int):
        self.session.query(models.ReadyPlayer).filter(models.ReadyPlayer.p_id == p_id).delete()
        self.session.commit()
        return True

    def get_signup_events(self):
        return self.session.query(models.Event).filter(models.Event.signup == 1).all()

    def clear_event_players(self, event_id: int):
        self.session.query(models.EventPlayer).filter(
            models.EventPlayer.event_id == event_id
        ).delete()
        self.session.commit()

    def add_event_player(self, event_id: int, player_id: int, table_minimum: int = 0):
        self.session.add(
            models.EventPlayer(event_id=event_id, p_id=player_id, table_minimum=table_minimum)
        )
        self.session.commit()

    def get_event_cached_tables(self, event_id: int):
        return (
            self.session.query(models.Table)
            .filter(models.Table.event_id == event_id)
            .filter(models.Table.reveal_cached == 1)
            .all()
        )

    def set_table_chat(self, table_id: int, chat_id: int):
        table = self.session.get(models.Table, table_id)
        table.chat_id = chat_id
        self.session.commit()

    def get_game_string(self, game_id: int):
        game = self.session.get(models.Game, game_id)
        ans = []
        for player in game.players():
            res = "✅ " if self.check_player_ready(player.p_id) else "❌ "
            res += player.irl_name
            ans.append(res)
        return "\n".join(ans)

    def check_game_ready(self, game_id: int):
        game = self.session.get(models.Game, game_id)
        return all(self.check_player_ready(player.p_id) for player in game.players())

    def get_table_first_game(self, table_id: int):
        table = self.session.get(models.Table, table_id)
        games = table.unfinished_games()
        if games:
            return games[0]
        else:
            return None
