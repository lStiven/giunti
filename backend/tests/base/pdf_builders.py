"""Builds small PDFs in memory so document tests never depend on fixture files."""

from collections.abc import Sequence
from io import BytesIO

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table

PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = 72.0


def questionnaire_pdf(*, encrypt: StandardEncryption | None = None) -> bytes:
    """One page with every formatting mark the extractor must keep."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, encrypt=encrypt)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(LEFT, 800, "1. Quale e la capitale d'Italia?")
    canvas.drawString(LEFT, 780, "A) Milano")
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(LEFT, 760, "B) Roma")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(LEFT, 740, "C) Napoli")
    canvas.line(LEFT, 738, LEFT + 52, 738)
    canvas.setFillColorRGB(1, 1, 0)
    canvas.rect(LEFT - 2, 716, 60, 14, fill=1, stroke=0)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.drawString(LEFT, 720, "D) Torino")
    canvas.drawString(LEFT, 700, "2. Questa domanda e molto lun-")
    canvas.drawString(LEFT, 686, "ga e continua.")
    canvas.setFont("ZapfDingbats", 12)
    canvas.drawString(LEFT, 660, "n")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(LEFT + 20, 660, "Vero")
    canvas.line(LEFT, 658, PAGE_WIDTH - LEFT, 658)
    table = Table([["Mai", "Sempre"], ["0", "1"]])
    table.setStyle([("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0))])
    table.wrapOn(canvas, 300, 100)
    table.drawOn(canvas, LEFT, 580)
    canvas.circle(300, 400, 50, fill=1)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def text_pdf(pages: int = 1) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for number in range(1, pages + 1):
        canvas.setFont("Helvetica", 12)
        canvas.drawString(LEFT, 800, f"Pagina {number}: indica quanto sei d'accordo.")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def lines_pdf(*pages: Sequence[str]) -> bytes:
    """One page per argument, each with its lines of text."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for lines in pages:
        canvas.setFont("Helvetica", 12)
        for index, line in enumerate(lines):
            canvas.drawString(LEFT, 800 - 20 * index, line)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def blank_pdf() -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def scanned_pdf() -> bytes:
    """A page that is only a raster image, like a scan without OCR."""
    image = Image.new("RGB", (400, 560), "white")
    image.paste((0, 0, 0), (40, 40, 360, 60))
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    canvas.drawImage(ImageReader(image), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
