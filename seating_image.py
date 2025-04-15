from PIL import Image, ImageDraw, ImageFont
from sqlite_parser import SqliteParser
import configparser

config = configparser.ConfigParser()
config.read("config.ini")
db_path = config.get("Settings", "database")
database = SqliteParser(db_path)
stage = config.get("Settings", "stage")

games = database.get_games(stage=stage)
seen_table_ids = set()
games2 = []
for i in games:
    if i['table'] in seen_table_ids:
        continue
    seen_table_ids.add(i['table'])
    players = []
    for j in i['players']:
        name = database.get_irl_name_by_pid(j)
        players.append(name)
    i["players"] = players
    games2.append(i)
games = games2

n = len(games)
columns = 7
rows = (n+columns-1) // columns
cell_h = 50
cell_w = 330
row_h = 5*cell_h
column_w = cell_w
gap = 25
width = (column_w+gap)*columns+gap
height = (row_h+gap)*rows+gap

name_font = ImageFont.truetype(font="/home/konstantin/.local/share/fonts/indestructible type*/TrueType/Jost/Jost_Regular.ttf", size=25)
table_font = ImageFont.truetype(font="/home/konstantin/.local/share/fonts/indestructible type*/TrueType/Jost/Jost_Regular.ttf", size=25)
table_font.set_variation_by_name('Bold')

bg_color = (130,166,221)
yellow = (247, 241, 148)

image = Image.new(mode="RGBA", size=(width,height), color=bg_color)
d = ImageDraw.Draw(image)

for i in range(n):
    x = gap+(i%columns)*(gap+column_w)
    y = gap+(i//columns)*(gap+row_h)
    d.rectangle(xy=(x,y,x+column_w,y+row_h), fill='white', outline='black')
    d.rectangle(xy=(x,y,x+cell_w,y+cell_h), fill=yellow, outline='black')
    d.text(xy=(x+column_w/2, y+cell_h/2), text=f"Стол {i+1}", font=table_font, anchor="mm", fill='black')
    players = games[i]['players']
    for j in range(4):
        d.text(xy=(x+25, y+cell_h*(j+1.5)), text=players[j], font=name_font, anchor="lm", fill='black')
        
image.save("seating.png")
# image.show()
