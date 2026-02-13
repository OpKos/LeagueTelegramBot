import requests
from bs4 import BeautifulSoup

from .. import models
from ..services import EventService, PlayerService


def event_portal_update(players: PlayerService, events: EventService, event: models.Event):
    url = event.link

    response = requests.get(url)
    data = response.text

    soup = BeautifulSoup(data, "html.parser")
    table = soup.find(class_="table table-hover mt-4")
    player_rows = table.find_all("tr")
    data = []
    for p in player_rows[1:]:
        success = 1 if p.has_attr("class") else 0
        name_obj, city_obj, nick_obj = p.find_all("td")[:3]
        if name_obj.find(class_="d-none d-print-block"):
            name = name_obj.find(class_="d-none d-print-block").contents[0]
        else:
            name = name_obj.contents[0]
        name = name.replace("\n", "")
        name = name.strip()
        if nick_obj.find(name="a"):
            nick = nick_obj.find(name="a").contents[0]
        else:
            nick = nick_obj.contents[0]
        data.append([name, nick, success])
    res = []
    for player in data:
        name, nick, include = player
        db_player = players.get_player(tenhou_name=nick)
        if db_player:
            players.fill_player_data(db_player.p_id, name)
            res.append(f"player updated in database: {name}")
            if include:
                table_minimum = 10000 if db_player.full_ready == 1 else 0
                events.add_event_player(
                    event_id=event.event_id, player_id=db_player.p_id, table_minimum=table_minimum
                )
        else:
            res.append(f"player not found in database: {name}")
    return "\n".join(res)
