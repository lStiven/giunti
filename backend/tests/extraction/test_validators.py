from typing import Any

import pytest

from app.extraction.schema import ExtractedQuestionnaire
from app.extraction.validators import questionnaire_rules

RULES = questionnaire_rules(pages=[1, 2])


def _item(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    item: dict[str, Any] = {
        "numero": 1,
        "enunciado": "Quale e la capitale d'Italia?",
        "tipo": "seleccion_multiple",
        "alternativas": [{"valor": "A", "texto": "Milano"}, {"valor": "B", "texto": "Roma"}],
        "respuesta_correcta": ["B"],
        "evidencia": "**B) Roma**",
        "pagina": 1,
    }
    return {**item, **fields}


def _errors(*items: dict[str, Any], idioma: str = "it") -> list[str]:
    questionnaire = ExtractedQuestionnaire.model_validate(
        {"titulo": None, "idioma": idioma, "items": list(items)}
    )
    return RULES(questionnaire)


def test_valid_questionnaire_has_no_errors() -> None:
    assert (
        _errors(
            _item(),
            _item(
                numero=2,
                tipo="desarrollo",
                alternativas=[],
                respuesta_correcta=None,
                evidencia=None,
            ),
        )
        == []
    )


def test_language_must_be_an_iso_639_1_code() -> None:
    assert _errors(_item(), idioma="italiano") == [
        "idioma: 'italiano' is not an ISO 639-1 code such as 'it'."
    ]


def test_item_numbers_must_be_unique() -> None:
    assert _errors(_item(), _item()) == ["Item numbers 1 are repeated; numbers must be unique."]


def test_item_must_start_on_the_pages_to_extract() -> None:
    message = (
        "items[0] (numero 1): pagina 3 is outside the pages to extract (1-2); extract only "
        "items that start on them."
    )

    assert _errors(_item(pagina=3)) == [message]


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        (
            {"alternativas": [{"valor": "A", "texto": "x"}], "respuesta_correcta": None},
            "tipo seleccion_multiple needs at least 2 alternativas.",
        ),
        (
            {
                "tipo": "verdadero_falso",
                "alternativas": [{"valor": "V", "texto": "Vero"}],
                "respuesta_correcta": None,
            },
            "tipo verdadero_falso needs exactly 2 alternativas.",
        ),
        (
            {"tipo": "desarrollo", "respuesta_correcta": None, "evidencia": None},
            "tipo desarrollo must have alternativas [].",
        ),
        (
            {"tipo": "escala_likert"},
            "tipo escala_likert must have respuesta_correcta null.",
        ),
        (
            {"premisas": [{"valor": 1, "texto": "x"}]},
            "premisas must be [] unless tipo is emparejamiento.",
        ),
        (
            {
                "alternativas": [{"valor": "A", "texto": "x"}, {"valor": "A", "texto": "y"}],
                "respuesta_correcta": None,
            },
            "alternativas repeat the valor A; each valor must be unique.",
        ),
    ],
)
def test_item_shape_rules(fields: dict[str, Any], error: str) -> None:
    assert f"items[0] (numero 1): {error}" in _errors(_item(**fields))


def test_answer_must_be_one_of_the_alternatives() -> None:
    assert _errors(_item(respuesta_correcta=["E"])) == [
        "items[0] (numero 1): respuesta_correcta 'E' is not the valor of any alternativa."
    ]


def test_answer_needs_evidence() -> None:
    assert _errors(_item(evidencia=None)) == [
        "items[0] (numero 1): respuesta_correcta needs the evidencia that marks it in the document."
    ]


def test_numeric_values_match_answers_given_as_strings() -> None:
    item = _item(
        alternativas=[{"valor": 1, "texto": "x"}, {"valor": 2, "texto": "y"}],
        respuesta_correcta=["2"],
    )

    assert _errors(item) == []


def test_matching_answers_are_premise_alternative_pairs() -> None:
    matching = _item(
        tipo="emparejamiento",
        premisas=[{"valor": 1, "texto": "Roma"}, {"valor": 2, "texto": "Parigi"}],
        alternativas=[{"valor": "a", "texto": "Francia"}, {"valor": "b", "texto": "Italia"}],
        respuesta_correcta=["1-b", "2-a", "3-c", "1b"],
        evidencia="1-b, 2-a",
    )

    errors = _errors(matching)

    assert len(errors) == 2
    assert all("must be 'premise-alternative'" in error for error in errors)
    assert "'3-c'" in errors[0]
    assert "'1b'" in errors[1]
