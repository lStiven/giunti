"""Builds small DOCX and XLSX files in memory for document tests."""

from io import BytesIO

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


def questionnaire_docx() -> bytes:
    document = Document()
    document.add_heading("Verifica di geografia", level=1)
    document.add_paragraph("Quale e la capitale d'Italia?", style="List Number")
    document.add_paragraph("Milano")
    document.add_paragraph().add_run("Roma").bold = True
    document.add_paragraph().add_run("Napoli").underline = True
    document.add_paragraph().add_run("Torino").font.highlight_color = WD_COLOR_INDEX.YELLOW
    document.add_paragraph("☐ Vero   ☒ Falso")
    document.add_paragraph("Il fiume piu lungo d'Italia?", style="List Number")
    table = document.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ["Mai", "A volte", "Sempre"], strict=True):
        cell.text = text
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def questionnaire_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Test"
    sheet["A1"] = "Questionario"
    sheet.merge_cells("A1:D1")
    sheet.append([])
    sheet.append(["N", "Domanda", "Mai", "Sempre"])
    sheet.append([1, "Mi sento | nervoso", 0, 1.0])
    sheet["D4"].font = Font(bold=True)
    sheet.append([2, "Dormo bene\ne a lungo", 0, 1])
    sheet["C5"].fill = PatternFill("solid", fgColor="FFFFFF00")
    sheet["D5"].font = Font(underline="single")
    answer_key = workbook.create_sheet("Chiave")
    answer_key.sheet_state = "hidden"
    answer_key["A1"] = "1-B"
    workbook.create_sheet("Vuota")
    return _save(workbook)


def xlsx_with_uncached_formula() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = "Totale"
    sheet["B1"] = "=1+1"
    return _save(workbook)


def xlsx_with_sheets(count: int) -> bytes:
    workbook = Workbook()
    for number in range(1, count):
        workbook.create_sheet(f"Sheet {number}")
    return _save(workbook)


def _save(workbook: Workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
