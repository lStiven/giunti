from typing import Any

import pytest
from pydantic import ValidationError

from app.extraction.schema import ExtractedQuestionnaire, ItemType, Questionnaire


def _model_output() -> dict[str, Any]:
    return {
        "titulo": "Questionario di prova",
        "idioma": "it",
        "items": [
            {
                "numero": 1,
                "enunciado": "Mi sento nervoso",
                "tipo": "escala_likert",
                "alternativas": [{"valor": 0, "texto": "Mai"}, {"valor": 1, "texto": "Sempre"}],
                "respuesta_correcta": None,
                "pagina": 1,
            },
            {
                "numero": 2,
                "enunciado": "Quale figura completa la serie?",
                "tipo": "seleccion_multiple",
                "alternativas": [{"valor": "A", "texto": None}, {"valor": "B", "texto": None}],
                "respuesta_correcta": ["B"],
                "pagina": 2,
                "evidencia": "**B**",
            },
        ],
    }


def test_public_questionnaire_serializes_with_spanish_field_names() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    data = questionnaire.model_dump(mode="json")

    assert set(data) == {"titulo", "idioma", "total_items", "items"}
    assert set(data["items"][0]) == {
        "numero",
        "enunciado",
        "tipo",
        "alternativas",
        "premisas",
        "respuesta_correcta",
    }


def test_total_items_is_computed_from_the_items() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    assert questionnaire.model_dump(mode="json")["total_items"] == 2


def test_to_public_removes_page_and_evidence() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    item = questionnaire.model_dump(mode="json")["items"][1]

    assert "pagina" not in item
    assert "evidencia" not in item
    assert item["respuesta_correcta"] == ["B"]


def test_figure_alternatives_keep_null_text() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    alternatives = questionnaire.model_dump(mode="json")["items"][1]["alternativas"]

    assert alternatives == [{"valor": "A", "texto": None}, {"valor": "B", "texto": None}]


def test_likert_values_stay_numeric() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    assert questionnaire.items[0].alternatives[0].value == 0
    assert questionnaire.items[0].item_type is ItemType.LIKERT


def test_premises_default_to_empty_list() -> None:
    questionnaire = ExtractedQuestionnaire.model_validate(_model_output()).to_public()

    assert questionnaire.model_dump(mode="json")["items"][0]["premisas"] == []


def test_model_output_ignores_unknown_fields() -> None:
    output = _model_output()
    output["total_items"] = 99
    output["items"][0]["confianza"] = "alta"

    questionnaire = ExtractedQuestionnaire.model_validate(output).to_public()

    assert questionnaire.total_items == 2


def test_model_output_requires_the_source_page() -> None:
    output = _model_output()
    del output["items"][0]["pagina"]

    with pytest.raises(ValidationError):
        ExtractedQuestionnaire.model_validate(output)


@pytest.mark.parametrize(
    ("field", "value"),
    [("tipo", "ensayo"), ("numero", 0), ("enunciado", "")],
)
def test_model_output_rejects_invalid_item_fields(field: str, value: object) -> None:
    output = _model_output()
    output["items"][0][field] = value

    with pytest.raises(ValidationError):
        ExtractedQuestionnaire.model_validate(output)


def test_public_questionnaire_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Questionnaire.model_validate({"titulo": None, "idioma": "es", "items": [], "extra": 1})
