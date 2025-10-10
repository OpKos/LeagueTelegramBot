from PIL import Image, ImageDraw, ImageFont
from PIL.Image import Resampling
from app.sqlalchemy_parser import SqliteParser
import configparser
from matplotlib import font_manager

config = configparser.ConfigParser()
config.read("app/config.ini")
db_path = config.get("Settings", "database")
db = SqliteParser(db_path)

REVEAL_START = 143
REVEAL_END = 158

name_font_file = font_manager.findfont("Jost", fallback_to_default=False)
name_font = ImageFont.truetype(font=name_font_file, size=25)
table_font_file = font_manager.findfont("Jost", fallback_to_default=False)
table_font = ImageFont.truetype(font=table_font_file, size=25)
table_font.set_variation_by_name('Bold')

bg_color = (255, 255, 255)
kawa_yellow = (244, 169, 61)
kawa_blue = (63, 99, 155)
kawa_red = (217, 89, 108)

n=REVEAL_END-REVEAL_START+1
row_h = 35
block_w = 300
gap = 10
inter_gap = 16
grid_w = 4
grid_h = (n+grid_w-1)//grid_w
width = grid_w * (block_w+inter_gap)+400
height = n*400
image = Image.new(mode="RGBA", size=(width,height), color=bg_color)
d = ImageDraw.Draw(image)
tables = [db.get_table_by_reveal_order(order) for order in range(REVEAL_START, REVEAL_END+1)]
tables.sort(key=lambda el: (len(el.players), el.table_id))

top = row_h+10
center = inter_gap+block_w//2+100
for i, table in enumerate(tables):
    assert table
    grid_x = i//grid_h
    grid_y = i-grid_x*grid_h
    if grid_y == 0 and i > 0:
        top = row_h+10
        center += block_w+inter_gap+30
    table_h = row_h * (len(table.players)+1) + gap*2
    if grid_x == grid_w-1 and grid_y == 0:
        top_wave = Image.open("images/top_wave.png").resize((120, 120), resample=Resampling.LANCZOS)
        image.paste(im=top_wave, box=(center+block_w//2-10-38, top-40), mask=top_wave)
        true_w = center+block_w//2+100
    d.rounded_rectangle(xy=(center-block_w/2, top, center+block_w/2, top+table_h), outline=kawa_blue, width=4, radius=14)
    top += gap
    text_color = kawa_yellow
    if len(table.games) > 4:
        text_color = kawa_red
    d.text(anchor="mm", xy=(center, top+row_h/2), text=f"Стол {table.table_id}", fill=text_color, font=table_font)
    top += row_h
    for player in table.players:
        d.text(anchor="mm", xy=(center, top+row_h/2), text=f"{player.irl_name}", fill=kawa_blue, font=name_font)
        top+=row_h
    top += inter_gap+gap
    if grid_y == grid_h-1 and grid_x == 0:
        bot_wave = Image.open("images/bot_wave.png").resize((154, 119), resample=Resampling.LANCZOS)
        image.paste(im=bot_wave, box=(center-block_w//2-144+38, top-76-inter_gap), mask=bot_wave)
        true_h = top+row_h
    if grid_y < grid_h-1 and i < len(tables)-1:
        for x in range(-1, 2):
            d.line(xy=(center-block_w/2+38+8*x, top-inter_gap-2, center-block_w/2+38+8*x, top+2), fill=kawa_blue, width=4)
        for x in range(-1, 2):
            d.line(xy=(center+block_w/2-38+8*x, top-inter_gap-2, center+block_w/2-38+8*x, top+2), fill=kawa_blue, width=4)
    


    
image = image.crop((0, 0, true_w, true_h))

image.save("seating.png")
image.show()

