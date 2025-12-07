from PIL import Image, ImageDraw, ImageFont
from sqlalchemy_parser import SqlParser
from matplotlib import font_manager
import models
from math import sqrt, floor

def create_seating_image(db: SqlParser, event: models.Event):
    name_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    name_font = ImageFont.truetype(font=name_font_file, size=25)
    table_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    table_font = ImageFont.truetype(font=table_font_file, size=25)
    table_font.set_variation_by_name('Bold')

    bg_color = (255, 255, 255)
    kawa_yellow = (244, 169, 61)
    kawa_blue = (63, 99, 155)
    kawa_red = (217, 89, 108)

    tables = [table for table in event.tables if table.reveal_cached]
    tables.sort(key=lambda table: table.name)

    n=len(tables)
    row_h = 35
    block_w = 300
    gap = 10
    inter_gap = 16
    grid_w = floor(sqrt(n))
    grid_h = (n+grid_w-1)//grid_w
    width = grid_w * (block_w+inter_gap)+400
    height = n*400
    image = Image.new(mode="RGBA", size=(width,height), color=bg_color)
    d = ImageDraw.Draw(image)

    top = row_h+10
    center = inter_gap+block_w//2+100
    for i, table in enumerate(tables):
        grid_x = i//grid_h
        grid_y = i-grid_x*grid_h
        if grid_y == 0 and i > 0:
            top = row_h+10
            center += block_w+inter_gap+30
        table_h = row_h * (len(table.players())+1) + gap*2
        if grid_x == grid_w-1 and grid_y == 0:
            true_w = center+block_w//2+100
        d.rounded_rectangle(xy=(center-block_w/2, top, center+block_w/2, top+table_h), outline=kawa_blue, width=4, radius=14)
        top += gap
        text_color = kawa_yellow
        d.text(anchor="mm", xy=(center, top+row_h/2), text=f"Стол {table.name}", fill=text_color, font=table_font)
        top += row_h
        for player in table.players():
            d.text(anchor="mm", xy=(center, top+row_h/2), text=f"{player.irl_name}", fill=kawa_blue, font=name_font)
            top+=row_h
        top += inter_gap+gap
        if grid_y == grid_h-1 and grid_x == 0:
            true_h = top+row_h

    image = image.crop((0, 0, true_w, true_h))

    image.save("seating.png")

