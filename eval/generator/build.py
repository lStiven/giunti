"""Generates synthetic tests from `generator/specs/*.json`.

Each spec yields, as listed in its `formats`: a DOCX (numbering, answers marked with bold,
underline, highlight or checkboxes, Likert tables, two-column matching, figure options, answer
key at the end), an XLSX (Likert matrix with merged headers, multiple choice rows, answers marked
with bold or fill, hidden answer-key sheet), a PDF converted with LibreOffice, and a "scanned"
PDF (rasterized with noise and slight rotation, no text layer). Next to them goes
`<id>.expected.json`, the JSON the API must return.

Usage: `uv run python -m generator.build [spec ids...]` (all specs when none is given).
"""

import json
import sys
import tempfile
import zlib
from pathlib import Path

from generator.docx_writer import write_docx
from generator.pdf import docx_to_pdf, scanned_pdf
from generator.spec import Spec, expected
from generator.xlsx_writer import write_xlsx

EVAL_DIR = Path(__file__).resolve().parents[1]
SPECS_DIR = EVAL_DIR / "generator" / "specs"
OUTPUT_DIR = EVAL_DIR / "datasets" / "synthetic"


def build(spec: Spec, output_dir: Path) -> list[Path]:
    target = output_dir / spec.id
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    formats = set(spec.formats)
    with tempfile.TemporaryDirectory() as workdir:
        docx = target / f"{spec.id}.docx" if "docx" in formats else Path(workdir, f"{spec.id}.docx")
        pdf = target / f"{spec.id}.pdf" if "pdf" in formats else Path(workdir, f"{spec.id}.pdf")
        if formats & {"docx", "pdf", "scanned"}:
            write_docx(spec, docx)
            if "docx" in formats:
                written.append(docx)
        if formats & {"pdf", "scanned"}:
            docx_to_pdf(docx, pdf)
            if "pdf" in formats:
                written.append(pdf)
        if "scanned" in formats:
            scanned = target / f"{spec.id}_escaneado.pdf"
            scanned_pdf(pdf, scanned, seed=zlib.crc32(spec.id.encode()))
            written.append(scanned)
    if "xlsx" in formats:
        xlsx = target / f"{spec.id}.xlsx"
        write_xlsx(spec, xlsx)
        written.append(xlsx)
    expected_json = target / f"{spec.id}.expected.json"
    expected_json.write_text(json.dumps(expected(spec), ensure_ascii=False, indent=2) + "\n")
    written.append(expected_json)
    return written


def load_specs(ids: list[str]) -> list[Spec]:
    specs = [Spec.model_validate_json(p.read_text()) for p in sorted(SPECS_DIR.glob("*.json"))]
    if not ids:
        return specs
    unknown = sorted(set(ids) - {spec.id for spec in specs})
    if unknown:
        message = f"Unknown spec ids: {', '.join(unknown)}"
        raise SystemExit(message)
    return [spec for spec in specs if spec.id in ids]


def main(argv: list[str]) -> None:
    for spec in load_specs(argv):
        files = build(spec, OUTPUT_DIR)
        names = ", ".join(path.name for path in files)
        sys.stdout.write(f"{spec.id}: {names}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
