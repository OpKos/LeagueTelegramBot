import requests
from bs4 import BeautifulSoup
import json

# URL страницы
url = "https://mahjong.click/ru/tournaments/riichi/yoroshiku-league-2/announcement/"
ena = 1

# Отправляем запрос на страницу
response = requests.get(url)
data = response.text
    

# Проверка, что запрос прошел успешно
if response.status_code == 200:
    # Парсим страницу с помощью BeautifulSoup
    soup = BeautifulSoup(data, 'html.parser')
    # Находим таблицу с игроками
    table = soup.find(class_="table table-hover mt-4")
    players = table.find_all("tr")
    data = []
    # Первая строчка - легенда, пропускаем
    for p in players[1:]:
        # У "зелёных" строчек есть класс "table-success"
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
        if nick_obj.find(name = "a"):
            nick = nick_obj.find(name = "a").contents[0]
        else:
            nick = nick_obj.contents[0]
        data.append([name, nick, success])
        
    with open('table_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    
    print("Данные успешно сохранены в 'table_data.json'")
else:
    print(f"Не удалось загрузить страницу. Код ошибки: {response.status_code}")
