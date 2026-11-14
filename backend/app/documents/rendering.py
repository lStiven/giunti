"""Renders PDF pages to PNG, capping the longest side to bound the model's token usage."""

from dataclasses import dataclass
from io import BytesIO

from pdfplumber.page import Page

POINTS_PER_INCH = 72


@dataclass(frozen=True, slots=True)
class RenderOptions:
    dpi: int
    max_px: int


def render_page_png(page: Page, options: RenderOptions) -> bytes:
    longest_side_pt = max(page.width, page.height)
    # Floor to one decimal so rounding never pushes the image past `max_px`.
    capped_dpi = int(options.max_px * POINTS_PER_INCH / longest_side_pt * 10) / 10
    image = page.to_image(resolution=min(options.dpi, capped_dpi)).original
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
