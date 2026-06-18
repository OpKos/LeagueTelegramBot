import datetime
import json

import pytz

from .. import models
from . import create_leaderboard_image


def get_leaderboard_data(event: models.Event, pantheon_data: list) -> list:
    pantheon_players = {}
    for player_in_event in pantheon_data:
        player_id: int = player_in_event.get("id", 0)
        score: int = int(player_in_event.get("rating", 0))
        games: int = player_in_event.get("games_played", 0)
        pantheon_players[player_id] = {"score": score, "games": games}
    relevant_players = []
    for event_player in event.event_players:
        player = event_player.player
        player_data = pantheon_players.get(player.pantheon_id, {"score": 0, "games": 0})
        player_data["name"] = player.irl_name
        player_data["group"] = event_player.leaderboard_group
        player_data["p_id"] = event_player.p_id
        relevant_players.append(player_data)
    relevant_players.sort(key=lambda el: (el["group"], -el["score"], el["name"]))
    player_data = [
        (player["name"], player["score"], player["games"], player["p_id"])
        for player in relevant_players
    ]
    return player_data


def get_leaderboard_image(event: models.Event, pantheon_data: list) -> str:
    player_data = get_leaderboard_data(event, pantheon_data)
    finished_games = 0
    total_games = 0
    for table in event.tables:
        for game in table.games:
            total_games += 1
            if game.started:
                finished_games += 1
    now = datetime.datetime.now(tz=pytz.timezone("Europe/Moscow"))
    filename = f"leaderboard{event.name}{now.timestamp()}.png"
    time_and_played_str = f"{now.strftime("%d.%m.%y")}, {finished_games}/{total_games} игр"
    specs = json.loads(event.leaderboard_specs)
    new_specs = dict()
    for k, v in specs.items():
        new_specs[int(k)] = v
    result = create_leaderboard_image(
        header=event.leaderboard_name,
        time_and_played=time_and_played_str,
        data=player_data,
        specs=new_specs,
        filename=filename,
    )
    return result
