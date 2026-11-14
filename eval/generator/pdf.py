"""DOCX to PDF with LibreOffice, and "scanned" PDFs: rasterized pages without a text layer."""

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]  # ships no type information
from PIL import Image, ImageFilter

SCAN_DPI = 150
POINTS_PER_INCH = 72
NOISE_DOTS = 3000
ROTATION_DEGREES = 0.7
CONVERSION_TIMEOUT_S = 180


def docx_to_pdf(docx: Path, pdf: Path) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        message = "LibreOffice (soffice) is required to convert DOCX to PDF"
        raise RuntimeError(message)
    with tempfile.TemporaryDirectory() as workdir:
        # A private profile lets several conversions run without sharing LibreOffice's lock.
        profile = Path(workdir, "profile").as_uri()
        command = [
            soffice,
            f"-env:UserInstallation={profile}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            workdir,
            str(docx),
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=CONVERSION_TIMEOUT_S)  # noqa: S603 - fixed arguments, no shell
        shutil.move(Path(workdir, f"{docx.stem}.pdf"), pdf)


def scanned_pdf(source: Path, target: Path, *, seed: int) -> None:
    """Every page as a slightly rotated, noisy grayscale image, like a scan without OCR."""
    rng = random.Random(seed)  # noqa: S311 - reproducible noise, not security
    document = pdfium.PdfDocument(str(source))
    pages = [
        _scan(document[i].render(scale=SCAN_DPI / POINTS_PER_INCH).to_pil(), rng)
        for i in range(len(document))
    ]
    first, *rest = pages
    first.save(target, save_all=True, append_images=rest, resolution=SCAN_DPI)


def _scan(page: Image.Image, rng: random.Random) -> Image.Image:
    image = page.convert("L").rotate(ROTATION_DEGREES, fillcolor=255, expand=False)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    pixels = image.load()
    if pixels is not None:
        for _ in range(NOISE_DOTS):
            x, y = rng.randrange(image.width), rng.randrange(image.height)
            pixels[x, y] = rng.choice((0, 80, 190))
    return image.convert("RGB")
