"""Splitting long documents into parts and merging the parts' results.

Models skip items and hit their output limit on long outputs, so a long document is extracted
in parts of a few pages. Each part also carries context pages that are never extracted from:
the page after the part (an item may continue there) and pages that look like an answer key
(usually at the end, needed to fill in the correct answers of every part).

Parts are merged in page order, dropping items repeated across parts, and renumbered 1, 2, 3...
when their numbers collide (documents without numbering or restarting it in each section).
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.documents.models import ExtractedDocument
from app.extraction.grounding import normalize
from app.extraction.schema import ExtractedItem, ExtractedQuestionnaire

MAX_ANSWER_KEY_PAGES = 2
SAME_STATEMENT_SIMILARITY = 90.0

_ANSWER_KEY = re.compile(
    r"\b(soluzion[ei]|risposte (corrette|esatte)|chiave (di correzione|delle risposte)"
    r"|answer key|solutions?|respuestas correctas|clave de respuestas|solucionario"
    r"|hoja de respuestas|gabarito|corrig[eé]s?|l[oö]sungen)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Chunk:
    """The pages to extract items from, plus context pages that are only read."""

    pages: tuple[int, ...]
    context_pages: tuple[int, ...]

    @property
    def first_page(self) -> int:
        return self.pages[0]

    @property
    def last_page(self) -> int:
        return self.pages[-1]


def plan_chunks(document: ExtractedDocument, pages_per_chunk: int) -> list[Chunk]:
    numbers = [page.number for page in document.pages]
    groups = [numbers[i : i + pages_per_chunk] for i in range(0, len(numbers), pages_per_chunk)]
    return [make_chunk(document, group) for group in groups]


def make_chunk(document: ExtractedDocument, pages: Sequence[int]) -> Chunk:
    if len(pages) == len(document.pages):
        return Chunk(pages=tuple(pages), context_pages=())
    own = set(pages)
    following = pages[-1] + 1
    context = {following} if any(p.number == following for p in document.pages) else set()
    context |= {number for number in answer_key_pages(document) if number not in own}
    return Chunk(pages=tuple(pages), context_pages=tuple(sorted(context - own)))


def split_chunk(document: ExtractedDocument, chunk: Chunk) -> tuple[Chunk, Chunk]:
    middle = len(chunk.pages) // 2
    return (
        make_chunk(document, chunk.pages[:middle]),
        make_chunk(document, chunk.pages[middle:]),
    )


def answer_key_pages(document: ExtractedDocument) -> tuple[int, ...]:
    """The last pages whose text looks like an answer key (scanned pages cannot be detected)."""
    matches = [page.number for page in document.pages if _ANSWER_KEY.search(page.text)]
    return tuple(matches[-MAX_ANSWER_KEY_PAGES:])


def merge(parts: Sequence[ExtractedQuestionnaire]) -> ExtractedQuestionnaire:
    """Joins the parts (in page order) into one questionnaire."""
    items: list[ExtractedItem] = []
    for part in parts:
        items += [item for item in part.items if not _already_kept(item, items)]
    if len({item.number for item in items}) != len(items):
        items = [item.model_copy(update={"number": n}) for n, item in enumerate(items, start=1)]
    return ExtractedQuestionnaire(
        titulo=next((part.title for part in parts if part.title), None),
        idioma=Counter(part.language for part in parts).most_common(1)[0][0],
        items=items,
    )


def _already_kept(item: ExtractedItem, kept: Sequence[ExtractedItem]) -> bool:
    statement = normalize(item.statement)
    return any(
        other.number == item.number
        and fuzz.ratio(normalize(other.statement), statement) >= SAME_STATEMENT_SIMILARITY
        for other in kept
    )
