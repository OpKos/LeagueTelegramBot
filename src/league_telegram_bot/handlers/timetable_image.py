from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from ..models import TableTime
from .utils import game_amount_string, timestring_from_timestamp


def create_timetable_image(table_times: list[TableTime], filename: str):
    name_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    name_font = ImageFont.truetype(font=name_font_file, size=25)
    table_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    table_font = ImageFont.truetype(font=table_font_file, size=25)
    table_font.set_variation_by_name("Bold")

    bg_color = (255, 255, 255)
    kawa_yellow = (244, 169, 61)
    kawa_blue = (63, 99, 155)

    n = len(table_times)
    margin = 10
    row_h = 35
    time_w = 150
    gap = 10
    block_w = 300
    block_h = row_h * 5 + gap * 2
    inter_gap = 16
    width = margin * 2 + time_w + block_w
    height = margin * 2 + n * (block_h + inter_gap) - inter_gap
    image = Image.new(mode="RGBA", size=(width, height), color=bg_color)
    d = ImageDraw.Draw(image)
    top = margin
    for table_time in table_times:
        time_str = (
            timestring_from_timestamp(table_time.time, day=True)
            + "\n"
            + game_amount_string(table_time.games)
        )
        d.text(
            anchor="mm",
            xy=(margin + time_w // 2, top + block_h // 2),
            text=time_str,
            font=name_font,
            fill="black",
            align="center",
        )
        d.rounded_rectangle(
            xy=(margin + time_w, top, margin + time_w + block_w, top + block_h),
            outline=kawa_blue,
            width=4,
            radius=14,
        )
        table = table_time.table
        top += gap
        d.text(
            anchor="mm",
            xy=(margin + time_w + block_w / 2, top + row_h / 2),
            text=f"Стол {table.name}",
            fill=kawa_yellow,
            font=table_font,
        )
        top += row_h
        for player in table.players():
            d.text(
                anchor="mm",
                xy=(margin + time_w + block_w / 2, top + row_h / 2),
                text=f"{player.irl_name}",
                fill=kawa_blue,
                font=name_font,
            )
            top += row_h
        top += gap
        top += inter_gap

    image.save(filename)
    return filename
