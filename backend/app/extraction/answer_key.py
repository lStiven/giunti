"""Second pass that reads the answer key for items left without a correct answer.

Answer keys usually sit at the end of the document, often in a table that spans several pages
and whose letters are drawn (so they exist only in the page image). The parts that hold the
items may not see all of it, so after the parts are merged, the items that can have a correct
answer and still have none are sent in one extra call together with the answer-key pages.

The pass only adds: answers already found are never changed, and when it cannot run or fails,
the questionnaire is returned as it was with a warning. Documents without pending items or
without answer-key pages make no extra call.
"""

import json
import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.documents.models import DocumentPage, ExtractedDocument, PageSource
from app.extraction.grounding import normalize
from app.extraction.schema import Alternative, ExtractedItem, ExtractedQuestionnaire, ItemType
from app.extraction.validators import item_errors
from app.llm.client import ContentPart, ImagePart, TextPart
from app.llm.structured import ExtractionTask, StructuredResult, StructuredRunner

TASK_NAME = "answer_key"
MAX_KEY_PAGES = 20
MAX_ITEM_PAGES = 30
MAX_LISTED_NUMBERS = 20
STATEMENT_PREVIEW_CHARS = 160
MIN_KEY_TABLE_ROWS = 3

ANSWERABLE_TYPES = frozenset({ItemType.MULTIPLE_CHOICE, ItemType.TRUE_FALSE, ItemType.MATCHING})

# Matched on normalized text (formatting marks removed, casefolded); singular forms catch the
# column headers of key tables that continue on the following pages.
_KEY_HEADING = re.compile(
    r"\b(soluzion[ei]|rispost[ae] corrett[ae]|chiave (di correzione|delle risposte)"
    r"|answer key|correct answers?|solutions?|respuestas? correctas?|clave de respuestas"
    r"|solucionario|hoja de respuestas|gabarito|corrig[eé]s?|l[oö]sungen)\b"
)
_NUMBERED_TABLE_ROW = re.compile(r"(?m)^\|\s*\d{1,3}\s*\|")

INSTRUCTIONS = """\
You read the answer key of a questionnaire to fill in the correct answers of some items.

# Input
- The items that still have no correct answer, as JSON: numero, pagina (the page where the \
item starts), tipo, the start of the enunciado, the valor of each alternative and, for \
emparejamiento, the valor of each premise.
- The pages that look like an answer key ("=== Answer key page N ==="), with their text and \
usually their image. The letters of key tables are often drawn, so they may appear only in \
the image.
- The text of the pages where those items are, to tell sections apart.

# Output
Answer with one JSON object only, without Markdown fences or comments:
{"respuestas": [{"numero": integer, "respuesta_correcta": [string], "evidencia": string}]}

# Rules
1. Use only what the answer key shows. Never solve a question yourself.
2. numero is the numero given in the item list. It can differ from the number printed in the \
document when the numbering restarts (a second exam or section numbered from 1 again): use \
pagina, the section titles and the headings of the key to match them. When you cannot tell \
which key entry belongs to an item, leave the item out.
3. respuesta_correcta lists valor values of that item as strings, such as ["B"]. For \
emparejamiento use "premise-alternative" pairs with the valor of premisas and alternativas, \
such as ["1-c", "2-a"].
4. evidencia: the short key entry that gives the answer, as written ("14 B", "Posición 14: B").
5. Leave out the items whose answer the key does not give. Answer {"respuestas": []} when it \
gives none.
"""

CLOSING_REQUEST = "Give the correct answer of each listed item that the answer key shows."

_INTERNAL_CONFIG = ConfigDict(
    validate_by_name=True,
    validate_by_alias=True,
    serialize_by_alias=True,
    frozen=True,
    extra="ignore",
)


class KeyAnswer(BaseModel):
    model_config = _INTERNAL_CONFIG

    number: int = Field(alias="numero")
    correct_answer: list[str] = Field(alias="respuesta_correcta", min_length=1)
    evidence: str = Field(alias="evidencia", min_length=1)


class KeyAnswers(BaseModel):
    """What the model returns: the answers it found in the key."""

    model_config = _INTERNAL_CONFIG

    answers: list[KeyAnswer] = Field(alias="respuestas", default_factory=list)


@dataclass(frozen=True, slots=True)
class KeyFill:
    questionnaire: ExtractedQuestionnaire
    warnings: tuple[str, ...] = ()
    result: StructuredResult[KeyAnswers] | None = None


def answer_key_pages(document: ExtractedDocument) -> tuple[int, ...]:
    """Pages whose text looks like an answer key, plus the pages that continue its table.

    Pages without a text layer cannot be detected. When too many pages match, the last ones
    are kept, since keys are usually at the end.
    """
    found: list[int] = []
    previous_is_key = False
    for page in document.pages:
        is_key = bool(_KEY_HEADING.search(normalize(page.text))) or (
            previous_is_key and _continues_key_table(page)
        )
        if is_key:
            found.append(page.number)
        previous_is_key = is_key
    return tuple(found[-MAX_KEY_PAGES:])


def pending_items(questionnaire: ExtractedQuestionnaire) -> list[ExtractedItem]:
    """Items of a type that can have a correct answer and still have none."""
    return [
        item
        for item in questionnaire.items
        if item.item_type in ANSWERABLE_TYPES and item.correct_answer is None
    ]


async def fill_from_answer_key(
    runner: StructuredRunner,
    document: ExtractedDocument,
    questionnaire: ExtractedQuestionnaire,
    model_id: str,
) -> KeyFill:
    """The questionnaire with the answers the key gives for its pending items."""
    pending = pending_items(questionnaire)
    key_pages = answer_key_pages(document)
    if not pending or not key_pages:
        return KeyFill(questionnaire)

    by_number = {item.number: item for item in pending}
    try:
        result = await runner.run(
            answer_key_task(by_number),
            build_key_content(document, key_pages, pending),
            model_id=model_id,
        )
    except AppError as error:
        missing = _listed([item.number for item in pending])
        warning = (
            f"The answer key on pages {_listed(key_pages)} could not be read ({error.message}); "
            f"items {missing} have no correct answer."
        )
        return KeyFill(questionnaire, (warning,))

    filled = apply_answers(questionnaire, by_number, result.value)
    left = [item.number for item in pending_items(filled) if item.number in by_number]
    warnings = list(result.warnings)
    if left:
        warnings.append(
            f"An answer key was found on pages {_listed(key_pages)}, but items {_listed(left)} "
            "still have no correct answer; check them against the document."
        )
    return KeyFill(filled, tuple(warnings), result)


def answer_key_task(pending: dict[int, ExtractedItem]) -> ExtractionTask[KeyAnswers]:
    return ExtractionTask(
        name=TASK_NAME,
        output_type=KeyAnswers,
        instructions=INSTRUCTIONS,
        validate=_key_rules(pending),
    )


def build_key_content(
    document: ExtractedDocument, key_pages: Collection[int], pending: Sequence[ExtractedItem]
) -> list[ContentPart]:
    listing = [_item_summary(item) for item in pending]
    parts: list[ContentPart] = [
        TextPart("Items without a correct answer:\n" + json.dumps(listing, ensure_ascii=False))
    ]
    keys = set(key_pages)
    item_pages = sorted({item.page for item in pending} - keys)[:MAX_ITEM_PAGES]
    for page in document.pages:
        if page.number in keys:
            parts.append(TextPart(f"=== Answer key page {page.number} ===\n{page.text}"))
            if page.image_png is not None:
                required = page.source is PageSource.IMAGE_ONLY
                parts.append(ImagePart(page.image_png, required=required))
        elif page.number in item_pages:
            parts.append(TextPart(f"=== Item page {page.number} (text only) ===\n{page.text}"))
    parts.append(TextPart(CLOSING_REQUEST))
    return parts


def apply_answers(
    questionnaire: ExtractedQuestionnaire,
    pending: dict[int, ExtractedItem],
    found: KeyAnswers,
) -> ExtractedQuestionnaire:
    """Fills only the pending items; every other item is kept as it is."""
    answers = {answer.number: answer for answer in found.answers if answer.number in pending}
    items = [
        _answered(item, answers[item.number]) if item.number in answers else item
        for item in questionnaire.items
    ]
    return questionnaire.model_copy(update={"items": items})


def _key_rules(pending: dict[int, ExtractedItem]) -> Callable[[KeyAnswers], list[str]]:
    def validate(found: KeyAnswers) -> list[str]:
        errors: list[str] = []
        seen: set[int] = set()
        for index, answer in enumerate(found.answers):
            prefix = f"respuestas[{index}] (numero {answer.number})"
            item = pending.get(answer.number)
            if item is None:
                errors.append(f"{prefix}: numero is not one of the listed items.")
                continue
            if answer.number in seen:
                errors.append(f"{prefix}: the item appears more than once.")
            seen.add(answer.number)
            errors += [f"{prefix}: {error}" for error in item_errors(_answered(item, answer))]
        return errors

    return validate


def _answered(item: ExtractedItem, answer: KeyAnswer) -> ExtractedItem:
    values = [_canonical_answer(item, value) for value in answer.correct_answer]
    return item.model_copy(update={"correct_answer": values, "evidence": answer.evidence})


def _canonical_answer(item: ExtractedItem, value: str) -> str:
    """The answer written with the item's own valor ("b" becomes "B"), when it is unambiguous."""
    if item.item_type is ItemType.MATCHING:
        premise, separator, alternative = value.strip().partition("-")
        if not separator:
            return value
        return (
            f"{_canonical_value(item.premises, premise)}-"
            f"{_canonical_value(item.alternatives, alternative)}"
        )
    return _canonical_value(item.alternatives, value)


def _canonical_value(options: Sequence[Alternative], value: str) -> str:
    wanted = value.strip()
    matches = {
        str(option.value) for option in options if str(option.value).casefold() == wanted.casefold()
    }
    return matches.pop() if len(matches) == 1 else wanted


def _item_summary(item: ExtractedItem) -> dict[str, object]:
    summary: dict[str, object] = {
        "numero": item.number,
        "pagina": item.page,
        "tipo": item.item_type.value,
        "enunciado": item.statement[:STATEMENT_PREVIEW_CHARS],
        "valores": [str(option.value) for option in item.alternatives],
    }
    if item.premises:
        summary["premisas"] = [str(option.value) for option in item.premises]
    return summary


def _continues_key_table(page: DocumentPage) -> bool:
    return len(_NUMBERED_TABLE_ROW.findall(page.text)) >= MIN_KEY_TABLE_ROWS


def _listed(numbers: Sequence[int]) -> str:
    shown = ", ".join(map(str, numbers[:MAX_LISTED_NUMBERS]))
    hidden = len(numbers) - MAX_LISTED_NUMBERS
    return f"{shown} and {hidden} more" if hidden > 0 else shown
