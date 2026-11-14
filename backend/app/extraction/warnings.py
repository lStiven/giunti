"""Warnings returned with a successful extraction (header `X-Extraction-Warnings`).

Each warning has a stable `code`, an English `message` for API clients and the final item
numbers or pages it refers to, so a client can show its own text and point to the items.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class WarningCode(StrEnum):
    SCANNED_PAGES = "scanned_pages"
    MISSING_FORMULA_VALUES = "missing_formula_values"
    STATEMENT_NOT_FOUND = "statement_not_found"
    OPTIONS_NOT_FOUND = "options_not_found"
    ANSWER_NOT_VERIFIED = "answer_not_verified"
    MISSING_ITEM_NUMBERS = "missing_item_numbers"
    ANSWER_KEY_UNREAD = "answer_key_unread"
    ANSWERS_NOT_IN_KEY = "answers_not_in_key"


@dataclass(frozen=True, slots=True)
class ExtractionWarning:
    code: WarningCode
    message: str
    items: tuple[int, ...] = ()
    """Final `numero` of the items it refers to (document numbers for missing_item_numbers)."""
    pages: tuple[int, ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "items": list(self.items),
            "pages": list(self.pages),
        }


def listed(numbers: Iterable[int]) -> str:
    return ", ".join(map(str, numbers))
