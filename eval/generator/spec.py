"""Specification of a synthetic test: its content, how it is rendered and the expected JSON.

The questionnaire fields keep the Spanish names of the API's public schema (`titulo`,
`enunciado`, `alternativas`...), so `expected()` is the exact JSON the API should return.
The rendering hints (`mark`, `shown`, `answer_key`...) only describe how the document looks.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

type Format = Literal["docx", "pdf", "scanned", "xlsx"]
type Figure = Literal["circle", "square", "triangle", "star", "cross"]

_CONFIG = ConfigDict(extra="forbid", frozen=True)


class ItemType(StrEnum):
    LIKERT = "escala_likert"
    MULTIPLE_CHOICE = "seleccion_multiple"
    TRUE_FALSE = "verdadero_falso"
    OPEN = "desarrollo"
    MATCHING = "emparejamiento"


class Mark(StrEnum):
    """How the document shows the correct answer."""

    NONE = "none"
    BOLD = "bold"
    UNDERLINE = "underline"
    HIGHLIGHT = "highlight"
    CHECKBOX = "checkbox"
    KEY = "key"
    """Only in the answer key (a table or an inline list after the items)."""


class Option(BaseModel):
    model_config = _CONFIG

    valor: int | str
    texto: str | None
    figure: Figure | None = None
    """Drawn instead of the text; `texto` must then be null (the API never describes figures)."""


class Item(BaseModel):
    model_config = _CONFIG

    numero: int = Field(ge=1, description="Number the API must return")
    shown: int | None = Field(default=None, description="Number printed; numero when missing")
    enunciado: str
    tipo: ItemType
    alternativas: list[Option] = []
    premisas: list[Option] = []
    respuesta_correcta: list[str] | None = None
    mark: Mark = Mark.NONE

    @property
    def printed_number(self) -> int:
        return self.shown if self.shown is not None else self.numero

    @model_validator(mode="after")
    def _check_answer(self) -> Self:
        has_answer = self.respuesta_correcta is not None
        if has_answer == (self.mark is Mark.NONE):
            message = f"item {self.numero}: an answer needs a mark and a mark needs an answer"
            raise ValueError(message)
        if self.tipo in (ItemType.LIKERT, ItemType.OPEN) and has_answer:
            message = f"item {self.numero}: {self.tipo} items have no correct answer"
            raise ValueError(message)
        if any(option.figure and option.texto for option in self.alternativas):
            message = f"item {self.numero}: figure options must have texto null"
            raise ValueError(message)
        return self


class Section(BaseModel):
    model_config = _CONFIG

    heading: str | None = None
    intro: str | None = None
    items: list[Item] = []


class AnswerKey(BaseModel):
    model_config = _CONFIG

    heading: str
    style: Literal["table", "inline"] = "table"
    new_page: bool = True
    columns: tuple[str, str] = ("N.", "Respuesta")
    by_section: bool = False
    """One table per section, headed by the section heading (numbering restarts)."""


class Spec(BaseModel):
    model_config = _CONFIG

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str
    formats: list[Format]
    titulo: str | None
    idioma: str
    instructions: list[str] = []
    sections: list[Section]
    answer_key: AnswerKey | None = None
    expected_error: str | None = Field(
        default=None, description="Error code the API must return instead of a questionnaire"
    )

    @property
    def items(self) -> list[Item]:
        return [item for section in self.sections for item in section.items]

    @model_validator(mode="after")
    def _check_spec(self) -> Self:
        numbers = [item.numero for item in self.items]
        if numbers != list(range(1, len(numbers) + 1)):
            message = f"{self.id}: numero must be 1, 2, 3... in document order"
            raise ValueError(message)
        if any(item.mark is Mark.KEY for item in self.items) and self.answer_key is None:
            message = f"{self.id}: items marked 'key' need an answer_key"
            raise ValueError(message)
        if not self.items and self.expected_error is None:
            message = f"{self.id}: a spec without items must set expected_error"
            raise ValueError(message)
        return self


def expected(spec: Spec) -> dict[str, object]:
    """The JSON the API must return for this spec (or the expected error)."""
    if spec.expected_error is not None:
        return {"error": {"code": spec.expected_error}}
    items = [
        {
            "numero": item.numero,
            "enunciado": item.enunciado,
            "tipo": item.tipo.value,
            "alternativas": [_public(option) for option in item.alternativas],
            "premisas": [_public(option) for option in item.premisas],
            "respuesta_correcta": item.respuesta_correcta,
        }
        for item in spec.items
    ]
    return {
        "titulo": spec.titulo,
        "idioma": spec.idioma,
        "total_items": len(items),
        "items": items,
    }


def _public(option: Option) -> dict[str, object]:
    return {"valor": option.valor, "texto": option.texto}
