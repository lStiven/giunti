"""Questionnaire consistency rules (hard): a result breaking them is never returned.

Each violation is a specific message the model receives in the repair attempt.
"""

import re
from collections import Counter
from collections.abc import Callable, Collection

from app.extraction.schema import Alternative, ExtractedItem, ExtractedQuestionnaire, ItemType

MAX_REPORTED = 30
_ISO_639_1 = re.compile(r"^[a-z]{2}$")
_MIN_OPTIONS = 2


def questionnaire_rules(pages: Collection[int]) -> Callable[[ExtractedQuestionnaire], list[str]]:
    """Rules for an extraction whose items must start on `pages`."""
    allowed = frozenset(pages)
    span = f"{min(allowed)}-{max(allowed)}" if allowed else "none"

    def validate(questionnaire: ExtractedQuestionnaire) -> list[str]:
        errors: list[str] = []
        if not _ISO_639_1.match(questionnaire.language):
            errors.append(
                f"idioma: '{questionnaire.language}' is not an ISO 639-1 code such as 'it'."
            )
        counts = Counter(item.number for item in questionnaire.items)
        repeated = sorted(number for number, count in counts.items() if count > 1)
        if repeated:
            listed = ", ".join(map(str, repeated))
            errors.append(f"Item numbers {listed} are repeated; numbers must be unique.")
        for index, item in enumerate(questionnaire.items):
            errors += [f"items[{index}] (numero {item.number}): {e}" for e in _item_errors(item)]
            if item.page not in allowed:
                errors.append(
                    f"items[{index}] (numero {item.number}): pagina {item.page} is outside the "
                    f"pages to extract ({span}); extract only items that start on them."
                )
        return errors[:MAX_REPORTED]

    return validate


def _item_errors(item: ExtractedItem) -> list[str]:
    errors = _shape_errors(item)
    if item.correct_answer is not None:
        if not item.correct_answer:
            errors.append("respuesta_correcta must be null or a non-empty list.")
        if not (item.evidence or "").strip():
            errors.append("respuesta_correcta needs the evidencia that marks it in the document.")
        errors += _answer_errors(item)
    return errors


def _shape_errors(item: ExtractedItem) -> list[str]:
    errors: list[str] = []
    options = len(item.alternatives)
    if item.item_type is not ItemType.MATCHING and item.premises:
        errors.append("premisas must be [] unless tipo is emparejamiento.")
    match item.item_type:
        case ItemType.LIKERT | ItemType.MULTIPLE_CHOICE if options < _MIN_OPTIONS:
            errors.append(f"tipo {item.item_type} needs at least 2 alternativas.")
        case ItemType.TRUE_FALSE if options != _MIN_OPTIONS:
            errors.append("tipo verdadero_falso needs exactly 2 alternativas.")
        case ItemType.OPEN if options:
            errors.append("tipo desarrollo must have alternativas [].")
        case ItemType.MATCHING if not item.premises or not item.alternatives:
            errors.append("tipo emparejamiento needs premisas and alternativas.")
        case _:
            pass
    if item.item_type in (ItemType.LIKERT, ItemType.OPEN) and item.correct_answer is not None:
        errors.append(f"tipo {item.item_type} must have respuesta_correcta null.")
    errors += _duplicated_values("alternativas", item.alternatives)
    errors += _duplicated_values("premisas", item.premises)
    return errors


def _answer_errors(item: ExtractedItem) -> list[str]:
    answers = item.correct_answer or []
    values = _values(item.alternatives)
    if item.item_type is ItemType.MATCHING:
        premises = _values(item.premises)
        errors = []
        for answer in answers:
            premise, separator, alternative = answer.partition("-")
            if not separator or premise not in premises or alternative not in values:
                errors.append(
                    f"respuesta_correcta '{answer}' must be 'premise-alternative' using the "
                    "valor of premisas and alternativas, such as '1-c'."
                )
        return errors
    if item.item_type in (ItemType.MULTIPLE_CHOICE, ItemType.TRUE_FALSE):
        return [
            f"respuesta_correcta '{answer}' is not the valor of any alternativa."
            for answer in answers
            if answer not in values
        ]
    return []


def _values(alternatives: list[Alternative]) -> set[str]:
    return {str(alternative.value) for alternative in alternatives}


def _duplicated_values(field: str, alternatives: list[Alternative]) -> list[str]:
    counts = Counter(str(alternative.value) for alternative in alternatives)
    repeated = sorted(value for value, count in counts.items() if count > 1)
    if not repeated:
        return []
    return [f"{field} repeat the valor {', '.join(repeated)}; each valor must be unique."]
