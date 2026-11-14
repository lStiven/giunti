"""Grounding checks against the source document (anti-hallucination, soft).

Statements, option texts and answer evidence must appear in the page text, and item numbers
present in the source must not be missing from the extraction (including items after the last
extracted one, the usual sign of a model that stopped early). Pages without a text layer cannot
be checked this way; they are reported as warnings instead.

These checks can have false positives (unusual layouts, text inside images), so they are a
`review`: the model gets one chance to fix them and the remaining ones become warnings.
"""

import re
import unicodedata
from collections.abc import Callable, Collection, Iterable

from rapidfuzz import fuzz

from app.documents.models import DocumentPage, DocumentWarning, ExtractedDocument, PageSource
from app.extraction.schema import ExtractedItem, ExtractedQuestionnaire, ItemType
from app.extraction.warnings import ExtractionWarning, WarningCode, listed

MIN_SIMILARITY = 85.0
MIN_CHECKED_LENGTH = 4
MAX_REPORTED = 20

_MARKS = re.compile(r"\*\*|</?u>|==|<br>")
_SPACES = re.compile(r"[\s|]+")
_QUOTES = str.maketrans(
    {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"'}
)
# An item number at the start of a line: "12.", "12)", "**12.**".
_ITEM_NUMBER = re.compile(r"(?m)^\s*(?:\*\*|<u>|==)*\s*(\d{1,3})\s*[.)]")
_CHECKED_OPTION_TYPES = frozenset({ItemType.MULTIPLE_CHOICE, ItemType.MATCHING})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    text = _MARKS.sub(" ", text)
    return _SPACES.sub(" ", text).strip().casefold()


def appears_in(fragment: str, text: str) -> bool:
    """Whether the fragment is in the (normalized) text, tolerating small extraction noise."""
    wanted = normalize(fragment)
    if len(wanted) < MIN_CHECKED_LENGTH or wanted in text:
        return True
    return fuzz.partial_ratio(wanted, text) >= MIN_SIMILARITY


def grounding_review(
    document: ExtractedDocument, extracted_pages: Collection[int] | None = None
) -> Callable[[ExtractedQuestionnaire], list[str]]:
    """Review for an extraction of `extracted_pages` (all pages by default)."""
    pages = {page.number: page for page in document.pages}
    texts = {page.number: normalize(page.text) for page in document.pages if _checkable(page)}
    all_text = " ".join(texts.values())
    source_numbers = _numbers_on(document, extracted_pages)

    def review(questionnaire: ExtractedQuestionnaire) -> list[str]:
        issues: list[str] = []
        for index, item in enumerate(questionnaire.items):
            page = pages.get(item.page)
            if page is None or not _checkable(page):
                continue
            # An item can continue on the next page.
            text = f"{texts.get(item.page, '')} {texts.get(item.page + 1, '')}"
            issues += [
                f"items[{index}] (numero {item.number}): {issue}"
                for issue in _item_issues(item, text, all_text)
            ]
        issues += _missing_numbers(questionnaire, source_numbers)
        return issues[:MAX_REPORTED]

    return review


def document_warnings(
    document: ExtractedDocument, questionnaire: ExtractedQuestionnaire
) -> list[ExtractionWarning]:
    """Warnings about what could not be verified, independent of the model's answer."""
    warnings: list[ExtractionWarning] = []
    pages_with_items = {item.page for item in questionnaire.items}
    unverifiable = tuple(
        page.number
        for page in document.pages
        if page.source is PageSource.IMAGE_ONLY and page.number in pages_with_items
    )
    if unverifiable:
        message = (
            f"Pages {listed(unverifiable)} have no text layer (scanned): their items were read "
            "from the image and could not be checked against the text."
        )
        items = tuple(item.number for item in questionnaire.items if item.page in unverifiable)
        warnings.append(
            ExtractionWarning(WarningCode.SCANNED_PAGES, message, items=items, pages=unverifiable)
        )
    sheets = tuple(
        page.number
        for page in document.pages
        if DocumentWarning.MISSING_FORMULA_VALUES in page.warnings
    )
    if sheets:
        message = (
            f"Sheets {listed(sheets)} have formulas without saved values; open the file in "
            "Excel, save it and upload it again to include them."
        )
        warnings.append(
            ExtractionWarning(WarningCode.MISSING_FORMULA_VALUES, message, pages=sheets)
        )
    return warnings


def review_warnings(
    document: ExtractedDocument, questionnaire: ExtractedQuestionnaire
) -> list[ExtractionWarning]:
    """The grounding checks on the final questionnaire, grouped by kind, with final numbers.

    The parts already got one chance to fix these issues; what is left is reported once per
    kind so the client can point to the items (numbers are the final ones, after merging).
    """
    texts = {page.number: normalize(page.text) for page in document.pages if _checkable(page)}
    all_text = " ".join(texts.values())
    statements: list[int] = []
    options: list[int] = []
    answers: list[int] = []
    for item in questionnaire.items:
        if item.page not in texts:
            continue
        text = f"{texts[item.page]} {texts.get(item.page + 1, '')}"
        if not appears_in(item.statement, text):
            statements.append(item.number)
        if _missing_options(item, text):
            options.append(item.number)
        if item.evidence and not appears_in(item.evidence, all_text):
            answers.append(item.number)

    warnings: list[ExtractionWarning] = []
    if statements:
        message = (
            f"The statements of items {listed(statements)} were not found literally in the "
            "document text (columns, figures or text inside images); check them."
        )
        warnings.append(
            ExtractionWarning(WarningCode.STATEMENT_NOT_FOUND, message, items=tuple(statements))
        )
    if options:
        message = (
            f"Some options of items {listed(options)} were not found literally in the "
            "document text; check them."
        )
        warnings.append(
            ExtractionWarning(WarningCode.OPTIONS_NOT_FOUND, message, items=tuple(options))
        )
    if answers:
        message = (
            f"The correct answers of items {listed(answers)} could not be checked against the "
            "document text (for example, an answer key drawn as an image); check them."
        )
        warnings.append(
            ExtractionWarning(WarningCode.ANSWER_NOT_VERIFIED, message, items=tuple(answers))
        )
    warnings += missing_item_numbers(document, questionnaire)
    return warnings


def _checkable(page: DocumentPage) -> bool:
    return page.source is PageSource.TEXT_LAYER


def _item_issues(item: ExtractedItem, text: str, all_text: str) -> list[str]:
    issues: list[str] = []
    if not appears_in(item.statement, text):
        issues.append(
            f"the enunciado was not found on page {item.page}; copy it literally from the "
            "document or remove the item if it is not there."
        )
    missing = _missing_options(item, text)
    if missing:
        issues.append(
            f"the texto of the options {', '.join(missing)} was not found on page "
            f"{item.page}; copy them literally."
        )
    if item.evidence and not appears_in(item.evidence, all_text):
        issues.append(
            "the evidencia was not found in the document; set respuesta_correcta and evidencia "
            "to null unless the document marks the answer."
        )
    return issues


def _missing_options(item: ExtractedItem, text: str) -> list[str]:
    if item.item_type not in _CHECKED_OPTION_TYPES:
        return []
    options = [*item.alternatives, *item.premises]
    return [
        str(option.value)
        for option in options
        if option.text is not None and not appears_in(option.text, text)
    ]


def missing_item_numbers(
    document: ExtractedDocument, questionnaire: ExtractedQuestionnaire
) -> list[ExtractionWarning]:
    """Item numbers printed in the document that are missing from the final result."""
    issues = _missing_numbers(questionnaire, _numbers_on(document, None))
    numbers = _missing_number_list(questionnaire, _numbers_on(document, None))
    if not issues:
        return []
    return [ExtractionWarning(WarningCode.MISSING_ITEM_NUMBERS, issues[0], items=numbers)]


def _numbers_on(document: ExtractedDocument, page_numbers: Collection[int] | None) -> set[int]:
    pages = [
        page
        for page in document.pages
        if _checkable(page) and (page_numbers is None or page.number in page_numbers)
    ]
    return _source_item_numbers(pages)


def _source_item_numbers(pages: Iterable[DocumentPage]) -> set[int]:
    return {int(match) for page in pages for match in _ITEM_NUMBER.findall(page.text)}


def _missing_numbers(questionnaire: ExtractedQuestionnaire, source: set[int]) -> list[str]:
    missing = _missing_number_list(questionnaire, source)
    if not missing:
        return []
    message = (
        f"Item numbers {listed(missing)} appear in the document but were not extracted; add "
        "them if they are items."
    )
    return [message]


def _missing_number_list(
    questionnaire: ExtractedQuestionnaire, source: set[int]
) -> tuple[int, ...]:
    extracted = {item.number for item in questionnaire.items}
    if not extracted or not source:
        return ()
    expected = set(range(min(extracted), max(extracted)))
    gaps = sorted((expected - extracted) & source)
    tail: list[int] = []
    following = max(extracted) + 1
    while following in source:
        tail.append(following)
        following += 1
    return (*gaps, *tail)
