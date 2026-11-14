"""XLSX extractor (openpyxl, cached values only).

Each non-empty sheet becomes one page holding a Markdown table without empty rows or columns.
Merged cell values are propagated, bold, underlined and filled cells are marked like in PDFs,
formulas without a cached value produce a warning, and images are ignored.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from io import BytesIO
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell, MergedCell
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.core.errors import AppError, ErrorCode, ErrorReason
from app.documents.models import (
    DocumentFormat,
    DocumentPage,
    DocumentWarning,
    ExtractedDocument,
    PageSource,
)

MAX_CELLS_PER_SHEET = 100_000
_WHITE_COLORS = frozenset({"FFFFFFFF", "00FFFFFF"})


@dataclass(frozen=True, slots=True)
class _Sheet:
    title: str
    hidden: bool
    rows: list[list[str]]
    char_count: int
    missing_formula_values: bool


def extract_xlsx(data: bytes, filename: str, *, max_pages: int) -> ExtractedDocument:
    values = _load(data, data_only=True)
    formulas = _load(data, data_only=False)
    worksheets = values.worksheets
    if len(worksheets) > max_pages:
        message = f"The workbook exceeds the maximum of {max_pages} sheets."
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            message,
            reason=ErrorReason.TOO_MANY_SHEETS,
            details={"limit": max_pages, "actual": len(worksheets)},
        )

    sheets = [_read_sheet(sheet, formulas[sheet.title]) for sheet in worksheets]
    pages = tuple(
        _page(number, sheet)
        for number, sheet in enumerate((sheet for sheet in sheets if sheet.rows), start=1)
    )
    return ExtractedDocument(document_format=DocumentFormat.XLSX, filename=filename, pages=pages)


def _load(data: bytes, *, data_only: bool) -> Workbook:
    try:
        return load_workbook(BytesIO(data), data_only=data_only, keep_links=False)
    except (InvalidFileException, BadZipFile, KeyError, ValueError, TypeError, OSError) as exc:
        message = "The XLSX file is damaged or not valid."
        raise AppError(ErrorCode.INVALID_FILE, message, reason=ErrorReason.DAMAGED) from exc


def _read_sheet(sheet: Worksheet, formula_sheet: object) -> _Sheet:
    if sheet.max_row * sheet.max_column > MAX_CELLS_PER_SHEET:
        message = f"The sheet '{sheet.title}' is too large to process."
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            message,
            reason=ErrorReason.SHEET_TOO_LARGE,
            details={"limit_cells": MAX_CELLS_PER_SHEET},
        )

    anchors = _merged_anchors(sheet)
    rows: list[list[str]] = []
    char_count = 0
    missing_formula_values = False
    for row in range(1, sheet.max_row + 1):
        texts: list[str] = []
        for column in range(1, sheet.max_column + 1):
            cell = sheet.cell(*anchors.get((row, column), (row, column)))
            text = _cell_text(cell.value) if isinstance(cell, Cell) else ""
            if not text and _has_formula(formula_sheet, row, column):
                missing_formula_values = True
            char_count += sum(1 for char in text if not char.isspace())
            texts.append(_styled(text, cell) if text and isinstance(cell, Cell) else text)
        rows.append(texts)

    return _Sheet(
        title=sheet.title,
        hidden=sheet.sheet_state != "visible",
        rows=_without_empty_lines(rows),
        char_count=char_count,
        missing_formula_values=missing_formula_values,
    )


def _merged_anchors(sheet: Worksheet) -> dict[tuple[int, int], tuple[int, int]]:
    anchors: dict[tuple[int, int], tuple[int, int]] = {}
    for merged in sheet.merged_cells.ranges:
        for row in range(merged.min_row, merged.max_row + 1):
            for column in range(merged.min_col, merged.max_col + 1):
                anchors[row, column] = (merged.min_row, merged.min_col)
    return anchors


def _has_formula(formula_sheet: object, row: int, column: int) -> bool:
    if not isinstance(formula_sheet, Worksheet):
        return False
    cell = formula_sheet.cell(row, column)
    return not isinstance(cell, MergedCell) and cell.data_type == "f"


def _cell_text(value: object) -> str:
    match value:
        case None:
            return ""
        case bool():
            text = "TRUE" if value else "FALSE"
        case float() if value.is_integer():
            text = str(int(value))
        case datetime() | date() | time():
            text = value.isoformat()
        case _:
            text = str(value)
    text = text.strip().replace("\r\n", "\n").replace("\n", "<br>")
    return text.replace("|", "\\|")


def _styled(text: str, cell: Cell) -> str:
    if cell.font.b:
        text = f"**{text}**"
    if cell.font.u:
        text = f"<u>{text}</u>"
    if _is_filled(cell):
        text = f"=={text}=="
    return text


def _is_filled(cell: Cell) -> bool:
    if cell.fill.fill_type != "solid":
        return False
    color = cell.fill.fgColor
    return not (color.type == "rgb" and str(color.rgb).upper() in _WHITE_COLORS)


def _without_empty_lines(rows: list[list[str]]) -> list[list[str]]:
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    kept_columns = [index for index in range(len(rows[0])) if any(row[index] for row in rows)]
    return [[row[index] for index in kept_columns] for row in rows]


def _page(number: int, sheet: _Sheet) -> DocumentPage:
    header = f"## Sheet: {sheet.title}" + (" (hidden)" if sheet.hidden else "")
    first, *rest = sheet.rows
    lines = [header, _markdown_row(first), _markdown_row(["---"] * len(first))]
    lines += [_markdown_row(row) for row in rest]
    warnings = (DocumentWarning.MISSING_FORMULA_VALUES,) if sheet.missing_formula_values else ()
    return DocumentPage(
        number=number,
        text="\n".join(lines),
        image_png=None,
        char_count=sheet.char_count,
        figure_coverage=0.0,
        source=PageSource.TEXT_LAYER,
        warnings=warnings,
    )


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"
