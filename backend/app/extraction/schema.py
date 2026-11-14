"""Questionnaire schemas.

The public contract keeps the Spanish JSON field names fixed by the problem statement
(`titulo`, `idioma`, `total_items`, `items`; each item has `numero`, `enunciado`, `tipo`,
`alternativas`, `premisas`, `respuesta_correcta`). Python identifiers stay in English through
Pydantic aliases.

The internal schema is what the model is asked to return: it adds the source page and the
evidence for each correct answer, which are removed by `to_public` before responding.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field

_PUBLIC_CONFIG = ConfigDict(
    validate_by_name=True,
    validate_by_alias=True,
    serialize_by_alias=True,
    frozen=True,
    extra="forbid",
)

# Unknown keys from the model are dropped instead of failing the whole extraction.
_INTERNAL_CONFIG = ConfigDict(
    validate_by_name=True,
    validate_by_alias=True,
    serialize_by_alias=True,
    frozen=True,
    extra="ignore",
)


class ItemType(StrEnum):
    LIKERT = "escala_likert"
    MULTIPLE_CHOICE = "seleccion_multiple"
    TRUE_FALSE = "verdadero_falso"
    OPEN = "desarrollo"
    MATCHING = "emparejamiento"


class Alternative(BaseModel):
    """An option of an item. `text` is None when the option is a figure."""

    model_config = _PUBLIC_CONFIG

    value: int | str = Field(alias="valor")
    text: str | None = Field(alias="texto")


class Item(BaseModel):
    """A questionnaire item.

    Matching items list the left column in `premises` and the right column in `alternatives`;
    their answers are pairs such as `"1-c"`. Other item types have no premises.
    """

    model_config = _PUBLIC_CONFIG

    number: int = Field(alias="numero", ge=1)
    statement: str = Field(alias="enunciado", min_length=1)
    item_type: ItemType = Field(alias="tipo")
    alternatives: list[Alternative] = Field(alias="alternativas", default_factory=list)
    premises: list[Alternative] = Field(alias="premisas", default_factory=list)
    correct_answer: list[str] | None = Field(alias="respuesta_correcta", default=None)


class Questionnaire(BaseModel):
    """Public response of the extraction endpoint."""

    model_config = _PUBLIC_CONFIG

    title: str | None = Field(alias="titulo")
    language: str = Field(alias="idioma")
    items: list[Item]

    @computed_field  # type: ignore[prop-decorator]  # mypy does not support decorated properties
    @property
    def total_items(self) -> int:
        return len(self.items)


class ExtractedItem(Item):
    """An item as returned by the model, with the data needed to verify it."""

    model_config = _INTERNAL_CONFIG

    page: int = Field(alias="pagina", ge=1)
    evidence: str | None = Field(
        alias="evidencia",
        default=None,
        description="Literal source fragment that marks the correct answer.",
    )

    def to_public(self) -> Item:
        return Item.model_validate(self.model_dump(exclude={"page", "evidence"}))


class ExtractedQuestionnaire(BaseModel):
    """The questionnaire as returned by the model, before verification."""

    model_config = _INTERNAL_CONFIG

    title: str | None = Field(alias="titulo", default=None)
    language: str = Field(alias="idioma")
    items: list[ExtractedItem]

    def to_public(self) -> Questionnaire:
        return Questionnaire(
            titulo=self.title,
            idioma=self.language,
            items=[item.to_public() for item in self.items],
        )
