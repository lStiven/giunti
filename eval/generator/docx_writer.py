"""Renders a spec as a Word document, the way a teacher would write it by hand."""

from io import BytesIO
from itertools import groupby
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_BREAK, WD_COLOR_INDEX
from docx.shared import Cm
from docx.table import Table
from docx.text.paragraph import Paragraph

from generator.figures import figure_png
from generator.spec import Item, ItemType, Mark, Option, Section, Spec

ANSWER_LINE = "_" * 70
UNCHECKED = "☐"
CHECKED = "☒"
FIGURE_WIDTH = Cm(2)


def write_docx(spec: Spec, path: Path) -> None:
    document = Document()
    if spec.titulo:
        document.add_heading(spec.titulo, level=1)
    for line in spec.instructions:
        document.add_paragraph(line)
    for section in spec.sections:
        _write_section(document, section)
    if spec.answer_key is not None and any(item.mark is Mark.KEY for item in spec.items):
        _write_answer_key(document, spec)
    document.save(str(path))


def _write_section(document: DocxDocument, section: Section) -> None:
    if section.heading:
        document.add_heading(section.heading, level=2)
    if section.intro:
        document.add_paragraph(section.intro)
    for is_likert, group in groupby(section.items, key=lambda i: i.tipo is ItemType.LIKERT):
        items = list(group)
        if is_likert:
            _write_likert_table(document, items)
            continue
        for item in items:
            _write_item(document, item)


def _write_item(document: DocxDocument, item: Item) -> None:
    document.add_paragraph(f"{item.printed_number}. {item.enunciado}")
    match item.tipo:
        case ItemType.OPEN:
            document.add_paragraph(ANSWER_LINE)
        case ItemType.MATCHING:
            _write_matching_table(document, item)
        case _ if any(option.figure for option in item.alternativas):
            _write_figure_options(document, item)
        case _:
            for option in item.alternativas:
                _write_option(document, item, option)


def _write_option(document: DocxDocument, item: Item, option: Option) -> None:
    correct = str(option.valor) in (item.respuesta_correcta or [])
    paragraph = document.add_paragraph()
    if item.mark is Mark.CHECKBOX:
        paragraph.add_run(f"{CHECKED if correct else UNCHECKED} ")
    run = paragraph.add_run(f"{option.valor}) {option.texto}")
    if not correct:
        return
    match item.mark:
        case Mark.BOLD:
            run.bold = True
        case Mark.UNDERLINE:
            run.underline = True
        case Mark.HIGHLIGHT:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        case _:
            pass


def _write_figure_options(document: DocxDocument, item: Item) -> None:
    table = document.add_table(rows=1, cols=len(item.alternativas))
    for cell, option in zip(table.rows[0].cells, item.alternativas, strict=True):
        paragraph = cell.paragraphs[0]
        paragraph.add_run(f"{option.valor})")
        if option.figure:
            paragraph.add_run().add_picture(BytesIO(figure_png(option.figure)), width=FIGURE_WIDTH)
    document.add_paragraph()


def _write_matching_table(document: DocxDocument, item: Item) -> None:
    rows = max(len(item.premisas), len(item.alternativas))
    table = document.add_table(rows=rows, cols=2)
    table.style = "Table Grid"
    for index, premise in enumerate(item.premisas):
        table.cell(index, 0).text = f"{premise.valor}. {premise.texto}"
    for index, option in enumerate(item.alternativas):
        table.cell(index, 1).text = f"{option.valor}) {option.texto}"
    document.add_paragraph()


def _write_likert_table(document: DocxDocument, items: list[Item]) -> None:
    scale = items[0].alternativas
    table = document.add_table(rows=len(items) + 1, cols=len(scale) + 1)
    table.style = "Table Grid"
    for column, point in enumerate(scale, start=1):
        table.cell(0, column).text = point.texto or str(point.valor)
    for row, item in enumerate(items, start=1):
        table.cell(row, 0).text = f"{item.printed_number}. {item.enunciado}"
        for column in range(1, len(scale) + 1):
            table.cell(row, column).text = UNCHECKED
    _widen_first_column(table)
    document.add_paragraph()


def _widen_first_column(table: Table) -> None:
    for row in table.rows:
        row.cells[0].width = Cm(8)


def _write_answer_key(document: DocxDocument, spec: Spec) -> None:
    key = spec.answer_key
    if key is None:
        return
    if key.new_page:
        _page_break(document.add_paragraph())
    document.add_heading(key.heading, level=2)
    if key.style == "inline":
        entries = [
            f"{i.printed_number}-{_answer_text(i)}" for i in spec.items if i.mark is Mark.KEY
        ]
        document.add_paragraph(", ".join(entries))
        return
    groups = (
        [s for s in spec.sections if s.items] if key.by_section else [Section(items=spec.items)]
    )
    for section in groups:
        keyed = [item for item in section.items if item.mark is Mark.KEY]
        if not keyed:
            continue
        if key.by_section and section.heading:
            document.add_paragraph(section.heading).runs[0].bold = True
        table = document.add_table(rows=len(keyed) + 1, cols=2)
        table.style = "Table Grid"
        table.cell(0, 0).text, table.cell(0, 1).text = key.columns
        for row, item in enumerate(keyed, start=1):
            table.cell(row, 0).text = str(item.printed_number)
            table.cell(row, 1).text = _answer_text(item)
        document.add_paragraph()


def _answer_text(item: Item) -> str:
    return ", ".join(item.respuesta_correcta or [])


def _page_break(paragraph: Paragraph) -> None:
    paragraph.add_run().add_break(WD_BREAK.PAGE)
