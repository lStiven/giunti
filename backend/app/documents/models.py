"""Extraction output models: what the rest of the application knows about an uploaded file."""

from dataclasses import dataclass
from enum import StrEnum


class DocumentFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"


class PageSource(StrEnum):
    """Where the page content must be read from."""

    TEXT_LAYER = "text_layer"
    """The text layer is reliable; the page image only adds visual context."""

    IMAGE_ONLY = "image_only"
    """The text layer is missing or unreadable: the page must be read from its image."""


class DocumentWarning(StrEnum):
    NO_TEXT_LAYER = "no_text_layer"
    GARBLED_TEXT_LAYER = "garbled_text_layer"
    MISSING_FORMULA_VALUES = "missing_formula_values"
    """The workbook was saved without computed values, so some formula cells look empty."""


@dataclass(frozen=True, slots=True)
class DocumentPage:
    """One page as text plus image.

    `text` is Markdown with formatting marks: `**bold**`, `<u>underline</u>`,
    `==highlight==`, tables as Markdown tables and `[FIGURE]` where a figure appears.
    `figure_coverage` is the fraction of the page area covered by figures (0 to 1).
    """

    number: int
    text: str
    image_png: bytes | None
    char_count: int
    figure_coverage: float
    source: PageSource
    warnings: tuple[DocumentWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    document_format: DocumentFormat
    filename: str
    pages: tuple[DocumentPage, ...]
    warnings: tuple[DocumentWarning, ...] = ()

    @property
    def requires_vision(self) -> bool:
        return any(page.source is PageSource.IMAGE_ONLY for page in self.pages)
