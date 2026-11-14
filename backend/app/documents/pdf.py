"""PDF extractor: per page, Markdown text with formatting marks plus a rendered page image.

Formatting marks are the main evidence of the correct answer, so bold (from font names),
underline (lines right under a word) and highlight (coloured rectangles behind a word) are kept.
Tables become Markdown tables, figures become `[FIGURE]` markers, symbol-font checkboxes become
Unicode symbols and words split by a hyphen at the end of a line are joined.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import BytesIO
from itertools import groupby
from typing import Any

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.page import Page
from pdfplumber.table import Table
from pdfplumber.utils.exceptions import PdfminerException

from app.core.errors import AppError, ErrorCode
from app.documents.models import (
    DocumentFormat,
    DocumentPage,
    DocumentWarning,
    ExtractedDocument,
    PageSource,
)
from app.documents.rendering import RenderOptions, render_page_png

FIGURE_MARK = "[FIGURE]"
MIN_TEXT_CHARS = 20
MAX_GARBLED_RATIO = 0.2
MIN_FIGURE_AREA_RATIO = 0.01
LINE_TOLERANCE_PT = 3.0
UNDERLINE_MAX_GAP_PT = 3.0
UNDERLINE_MAX_OVERLAP_PT = 4.0
UNDERLINE_MAX_THICKNESS_PT = 1.5
EDGE_TOLERANCE_PT = 1.0
MIN_CHROMA = 0.15
COLOR_COMPONENTS = 3

_BOLD_FONT_HINTS = ("bold", "black", "heavy", "semibold", "demibold")
_HYPHENATED_END = re.compile(r"[^\W\d_]-$")
_LOWERCASE_START = re.compile(r"^[^\W\d_A-ZÀ-Þ]")

# Symbol fonts map checkboxes to letters or private-use code points instead of Unicode symbols.
_SYMBOL_FONTS: dict[str, dict[str, str]] = {
    "dingbats": {"n": "■", "o": "❏", "q": "❑", "3": "✓", "4": "✔", "7": "✗", "8": "✘"},
    "wingdings": {
        "": "☐",
        "": "☐",
        "": "☐",
        "": "☑",
        "": "☒",
        "": "☒",
        "": "✓",
        "": "✗",
    },
}


@dataclass(frozen=True, slots=True)
class _Box:
    x0: float
    top: float
    x1: float
    bottom: float

    @classmethod
    def of(cls, obj: dict[str, Any]) -> "_Box":
        return cls(float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"]))

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.bottom - self.top)

    def contains_point(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.top <= y <= self.bottom


@dataclass(frozen=True, slots=True)
class _Style:
    bold: bool = False
    underline: bool = False
    highlight: bool = False

    def apply(self, text: str) -> str:
        if self.bold:
            text = f"**{text}**"
        if self.underline:
            text = f"<u>{text}</u>"
        if self.highlight:
            text = f"=={text}=="
        return text


@dataclass(frozen=True, slots=True)
class _Word:
    text: str
    box: _Box
    style: _Style

    @property
    def center(self) -> tuple[float, float]:
        return (self.box.x0 + self.box.x1) / 2, (self.box.top + self.box.bottom) / 2


@dataclass(frozen=True, slots=True)
class _Block:
    """A piece of page text placed at a vertical position, so blocks can be merged in order."""

    top: float
    text: str


@dataclass(frozen=True, slots=True)
class _Marks:
    """Page graphics that carry formatting: underline segments and highlight rectangles."""

    underlines: tuple[_Box, ...]
    highlights: tuple[_Box, ...]


def extract_pdf(
    data: bytes, filename: str, *, max_pages: int, render: RenderOptions
) -> ExtractedDocument:
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if not pdf.pages:
                raise AppError(ErrorCode.INVALID_FILE, "The PDF has no pages.")
            if len(pdf.pages) > max_pages:
                message = f"The document exceeds the maximum of {max_pages} pages."
                raise AppError(ErrorCode.FILE_TOO_LARGE, message)
            pages = tuple(_extract_page(page, render) for page in pdf.pages)
    except PdfminerException as exc:
        if exc.args and isinstance(exc.args[0], PDFPasswordIncorrect):
            raise AppError(ErrorCode.PROTECTED_FILE) from exc
        raise AppError(ErrorCode.INVALID_FILE) from exc
    return ExtractedDocument(document_format=DocumentFormat.PDF, filename=filename, pages=pages)


def _extract_page(page: Page, render: RenderOptions) -> DocumentPage:
    marks = _Marks(underlines=_underline_segments(page), highlights=_highlight_boxes(page))
    tables = page.find_tables()
    table_boxes = [_Box(*map(float, table.bbox)) for table in tables]
    words = _words(page, marks)

    free_words = [w for w in words if not any(b.contains_point(*w.center) for b in table_boxes)]
    blocks = _line_blocks(free_words)
    blocks += [
        _table_block(table, box, words) for table, box in zip(tables, table_boxes, strict=True)
    ]
    figures = _figure_boxes(page)
    blocks += [_Block(figure.top, FIGURE_MARK) for figure in figures]
    text = "\n".join(block.text for block in sorted(blocks, key=lambda block: block.top))

    char_count, garbled_ratio = _text_layer_stats(page.chars)
    warnings: list[DocumentWarning] = []
    if char_count < MIN_TEXT_CHARS:
        warnings.append(DocumentWarning.NO_TEXT_LAYER)
    elif garbled_ratio > MAX_GARBLED_RATIO:
        warnings.append(DocumentWarning.GARBLED_TEXT_LAYER)

    page_area = float(page.width) * float(page.height)
    return DocumentPage(
        number=page.page_number,
        text=text,
        image_png=render_page_png(page, render),
        char_count=char_count,
        figure_coverage=min(1.0, sum(figure.area for figure in figures) / page_area),
        source=PageSource.IMAGE_ONLY if warnings else PageSource.TEXT_LAYER,
        warnings=tuple(warnings),
    )


def _words(page: Page, marks: _Marks) -> list[_Word]:
    words: list[_Word] = []
    for raw in page.extract_words(extra_attrs=["fontname"]):
        box = _Box.of(raw)
        fontname = str(raw["fontname"]).lower()
        center_x, center_y = (box.x0 + box.x1) / 2, (box.top + box.bottom) / 2
        style = _Style(
            bold=any(hint in fontname for hint in _BOLD_FONT_HINTS),
            highlight=any(h.contains_point(center_x, center_y) for h in marks.highlights),
        )
        words.append(_Word(_map_symbols(str(raw["text"]), fontname), box, style))
    return _with_underlines(words, marks.underlines)


def _map_symbols(text: str, fontname: str) -> str:
    for font_hint, symbols in _SYMBOL_FONTS.items():
        if font_hint in fontname:
            return "".join(symbols.get(char, char) for char in text)
    return text


def _with_underlines(words: list[_Word], underlines: Sequence[_Box]) -> list[_Word]:
    """Marks words with an underline segment right below them and within their line's span.

    Requiring the segment to stay within the line's text span discards separators and rules
    that run across the page.
    """
    result: list[_Word] = []
    for line in _group_lines(words):
        line_x0 = min(word.box.x0 for word in line)
        line_x1 = max(word.box.x1 for word in line)
        for word in line:
            underlined = any(
                segment.x0 <= word.box.x0 + EDGE_TOLERANCE_PT
                and segment.x1 >= word.box.x1 - EDGE_TOLERANCE_PT
                and segment.x0 >= line_x0 - UNDERLINE_MAX_OVERLAP_PT
                and segment.x1 <= line_x1 + UNDERLINE_MAX_OVERLAP_PT
                and segment.top - word.box.bottom >= -UNDERLINE_MAX_OVERLAP_PT
                and segment.top - word.box.bottom <= UNDERLINE_MAX_GAP_PT
                for segment in underlines
            )
            style = _Style(word.style.bold, underlined, word.style.highlight)
            result.append(_Word(word.text, word.box, style))
    return result


def _underline_segments(page: Page) -> tuple[_Box, ...]:
    candidates = [*page.lines, *page.rects]
    boxes = (_Box.of(obj) for obj in candidates)
    return tuple(box for box in boxes if box.bottom - box.top <= UNDERLINE_MAX_THICKNESS_PT)


def _highlight_boxes(page: Page) -> tuple[_Box, ...]:
    return tuple(
        _Box.of(rect)
        for rect in page.rects
        if rect.get("fill") and _is_chromatic(rect.get("non_stroking_color"))
    )


def _is_chromatic(color: object) -> bool:
    """True for coloured fills; grays (including white and black) are not highlights."""
    if not isinstance(color, tuple | list):
        return False
    components = [float(value) for value in color if isinstance(value, int | float)]
    rgb_or_cmy = components[:COLOR_COMPONENTS]
    has_color = len(rgb_or_cmy) == COLOR_COMPONENTS
    return has_color and max(rgb_or_cmy) - min(rgb_or_cmy) > MIN_CHROMA


def _group_lines(words: Iterable[_Word]) -> list[list[_Word]]:
    lines: list[list[_Word]] = []
    for word in sorted(words, key=lambda w: (w.box.top, w.box.x0)):
        if lines and word.box.top - lines[-1][0].box.top <= LINE_TOLERANCE_PT:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w.box.x0) for line in lines]


def _line_text(line: Sequence[_Word]) -> str:
    runs = groupby(line, key=lambda word: word.style)
    return " ".join(style.apply(" ".join(word.text for word in run)) for style, run in runs)


def _line_blocks(words: Iterable[_Word]) -> list[_Block]:
    blocks: list[_Block] = []
    for line in _group_lines(words):
        text = _line_text(line)
        if blocks and _HYPHENATED_END.search(blocks[-1].text) and _LOWERCASE_START.match(text):
            blocks[-1] = _Block(blocks[-1].top, blocks[-1].text[:-1] + text)
        else:
            blocks.append(_Block(line[0].box.top, text))
    return blocks


def _table_block(table: Table, box: _Box, words: Sequence[_Word]) -> _Block:
    rows: list[list[str]] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            if cell is None:
                cells.append("")
                continue
            cell_box = _Box(*map(float, cell))
            inside = [w for w in words if cell_box.contains_point(*w.center)]
            cell_text = " ".join(block.text for block in _line_blocks(inside))
            cells.append(cell_text.replace("|", "\\|"))
        rows.append(cells)
    return _Block(box.top, _markdown_table(rows))


def _markdown_table(rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return ""
    header, *body = rows
    lines = [_markdown_row(header), _markdown_row(["---"] * len(header))]
    lines += [_markdown_row(row) for row in body]
    return "\n".join(lines)


def _markdown_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _figure_boxes(page: Page) -> list[_Box]:
    min_area = MIN_FIGURE_AREA_RATIO * float(page.width) * float(page.height)
    boxes = (_Box.of(obj) for obj in [*page.images, *page.curves])
    return [box for box in boxes if box.area >= min_area]


def _text_layer_stats(chars: Sequence[dict[str, Any]]) -> tuple[int, float]:
    """Returns the number of visible characters and the share of unreadable ones."""
    texts = [str(char["text"]) for char in chars if not str(char["text"]).isspace()]
    if not texts:
        return 0, 0.0
    garbled = sum(1 for text in texts if text.startswith("(cid:") or text == "�")
    return len(texts), garbled / len(texts)
