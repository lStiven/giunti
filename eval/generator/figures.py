"""Small PNG drawings used as figure options ("which figure comes next?")."""

from io import BytesIO

from PIL import Image, ImageDraw

from generator.spec import Figure

SIZE = 120
MARGIN = 20
LINE = 6


def figure_png(figure: Figure) -> bytes:
    image = Image.new("RGB", (SIZE, SIZE), "white")
    draw = ImageDraw.Draw(image)
    low, high = MARGIN, SIZE - MARGIN
    middle = SIZE // 2
    match figure:
        case "circle":
            draw.ellipse((low, low, high, high), outline="black", width=LINE)
        case "square":
            draw.rectangle((low, low, high, high), outline="black", width=LINE)
        case "triangle":
            draw.polygon([(middle, low), (high, high), (low, high)], outline="black", width=LINE)
        case "star":
            points = [(middle, low), (70, 50), (high, 50), (76, 72), (88, high)]
            points += [(middle, 84), (32, high), (44, 72), (low, 50), (50, 50)]
            draw.polygon(points, outline="black", width=LINE)
        case "cross":
            draw.line((low, low, high, high), fill="black", width=LINE)
            draw.line((low, high, high, low), fill="black", width=LINE)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
