"""Renders a spec as a spreadsheet: one block per section, answers marked or in a hidden sheet."""

from itertools import groupby
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from generator.spec import Item, ItemType, Mark, Spec

HIGHLIGHT = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
BOLD = Font(bold=True)
FIRST_OPTION_COLUMN = 3
SCALE_HEADER = "Escala"


def write_xlsx(spec: Spec, path: Path) -> None:
    unsupported = [i.numero for i in spec.items if i.tipo is ItemType.MATCHING]
    unsupported += [i.numero for i in spec.items if any(o.figure for o in i.alternativas)]
    if unsupported:
        message = f"{spec.id}: items {unsupported} cannot be written to a spreadsheet"
        raise ValueError(message)

    workbook = Workbook()
    sheet = workbook.active
    if sheet is None:
        message = "openpyxl created a workbook without a sheet"
        raise RuntimeError(message)
    sheet.title = "Cuestionario"
    if spec.titulo:
        sheet.append([spec.titulo])
        sheet.cell(row=sheet.max_row, column=1).font = BOLD
    for line in spec.instructions:
        sheet.append([line])
    for section in spec.sections:
        sheet.append([])
        if section.heading:
            sheet.append([section.heading])
            sheet.cell(row=sheet.max_row, column=1).font = BOLD
        for is_likert, group in groupby(section.items, key=lambda i: i.tipo is ItemType.LIKERT):
            items = list(group)
            if is_likert:
                _write_likert(sheet, items)
            else:
                for item in items:
                    _write_item(sheet, item)
    sheet.column_dimensions["B"].width = 60
    _write_key_sheet(workbook, spec)
    workbook.save(path)


def _write_likert(sheet: Worksheet, items: list[Item]) -> None:
    scale = items[0].alternativas
    first = FIRST_OPTION_COLUMN
    last = first + len(scale) - 1
    sheet.append(["", "", SCALE_HEADER])
    row = sheet.max_row
    sheet.merge_cells(start_row=row, start_column=first, end_row=row, end_column=last)
    sheet.append(["#", "", *[point.texto or "" for point in scale]])
    sheet.append(["", "", *[point.valor for point in scale]])
    for item in items:
        sheet.append([item.printed_number, item.enunciado])


def _write_item(sheet: Worksheet, item: Item) -> None:
    if item.tipo is ItemType.OPEN:
        sheet.append([item.printed_number, item.enunciado, "Respuesta:"])
        return
    sheet.append(["", "", *[str(option.valor) for option in item.alternativas]])
    sheet.append([item.printed_number, item.enunciado, *[o.texto for o in item.alternativas]])
    row = sheet.max_row
    for column, option in enumerate(item.alternativas, start=FIRST_OPTION_COLUMN):
        if str(option.valor) not in (item.respuesta_correcta or []):
            continue
        cell = sheet.cell(row=row, column=column)
        if item.mark is Mark.BOLD:
            cell.font = BOLD
        elif item.mark is Mark.HIGHLIGHT:
            cell.fill = HIGHLIGHT


def _write_key_sheet(workbook: Workbook, spec: Spec) -> None:
    keyed = [item for item in spec.items if item.mark is Mark.KEY]
    if not keyed or spec.answer_key is None:
        return
    sheet = workbook.create_sheet(spec.answer_key.heading[:31])
    sheet.append(list(spec.answer_key.columns))
    for item in keyed:
        sheet.append([item.printed_number, ", ".join(item.respuesta_correcta or [])])
    sheet.sheet_state = "hidden"
