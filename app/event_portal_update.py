import requests
from bs4 import BeautifulSoup
import models
from sqlalchemy_parser import SqlParser

def event_portal_update(db: SqlParser, event: models.Event):
    url = event.link

    response = requests.get(url)
    data = response.text

    soup = BeautifulSoup(data, 'html.parser')
    table = soup.find(class_="table table-hover mt-4")
    players = table.find_all("tr")
    data = []
    for p in players[1:]:
        if p.has_attr('class'):
            success = 1
        else:
            success = 0
        name_obj, city_obj, nick_obj = p.find_all('td')[:3]
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
        player = db.get_player(tenhou_name=nick)
        if player:
            db.fill_player_data(player.p_id, name)
            res.append(f"player updated in database: {name}")
            if include:
                db.add_event_player(event_id=event.event_id, player_id=player.p_id)
        else:
            res.append(f"player not found in database: {name}")
    return "\n".join(res)

