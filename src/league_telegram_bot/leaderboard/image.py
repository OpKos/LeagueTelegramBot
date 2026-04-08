from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont


def create_leaderboard_image(
    header: str,
    time_and_played: str,
    data: list[tuple[str, int, int]],
    specs: dict[int, list],
    filename: str,
) -> str:
    name_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    name_font = ImageFont.truetype(font=name_font_file, size=25)
    date_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    date_font = ImageFont.truetype(font=date_font_file, size=20)
    header_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    header_font = ImageFont.truetype(font=header_font_file, size=35)
    header_font.set_variation_by_name("Bold")
    place_font_file = font_manager.findfont("Jost", fallback_to_default=False)
    place_font = ImageFont.truetype(font=place_font_file, size=25)
    place_font.set_variation_by_name("Bold")
    number_font_file = font_manager.findfont("Inconsolata", fallback_to_default=False)
    number_font = ImageFont.truetype(font=number_font_file, size=25)

    bg_color = (255, 255, 255)
    kawa_yellow = (244, 169, 61)
    kawa_blue = (63, 99, 155)
    kawa_red = (206, 45, 79)
    kawa_green = (112, 183, 126)

    n = len(data)
    margin = 10
    header_h = 130
    time_h = 40
    row_h = 40
    place_w = 50
    block_w = 460
    games_w = 40
    width = place_w + block_w + games_w + margin * 2
    height = header_h + time_h + n * row_h + margin * 2
    image = Image.new(mode="RGBA", size=(width, height), color=bg_color)
    d = ImageDraw.Draw(image)

    top = margin
    d.text(
        anchor="mm",
        align="center",
        xy=(width / 2, top + header_h / 2),
        text=header,
        fill=kawa_blue,
        font=header_font,
    )
    top += header_h
    d.text(
        anchor="rm",
        xy=(width - margin, top + time_h / 2),
        text=time_and_played,
        fill="black",
        font=date_font,
    )
    top += time_h

    for place, player in enumerate(data, 1):
        name, score, games = player
        left = margin
        d.text(
            anchor="mm",
            xy=(left + place_w / 2, top + row_h / 2),
            text=str(place),
            fill=kawa_yellow,
            font=place_font,
        )
        left += place_w
        d.text(
            anchor="lm", xy=(left + 5, top + row_h / 2), text=name, fill=kawa_blue, font=name_font
        )
        left += block_w
        d.text(
            anchor="rm",
            xy=(left, top + row_h / 2),
            text=f"{score:+}",
            fill=kawa_blue,
            font=number_font,
        )
        d.text(
            anchor="mm",
            xy=(left + games_w / 2, top + row_h / 2),
            text=str(games),
            fill=kawa_blue,
            font=number_font,
        )

        top += row_h
        row_specs = specs.get(place, [])
        line_fill = None
        if "green" in row_specs:
            line_fill = kawa_green
        if "red" in row_specs:
            line_fill = kawa_red
        if line_fill:
            if "dashed" in row_specs:
                dash_width = 20
                left = 0
                while left < width:
                    d.line(xy=((left, top), (left + dash_width, top)), fill=line_fill, width=3)
                    left += dash_width * 2
            else:
                d.line(xy=((0, top), (width, top)), fill=line_fill, width=3)

    image.show()
    image.save(filename)
    return filename
