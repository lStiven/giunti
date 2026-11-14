import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedClient, require_extraction_quota
from app.auth.rate_limit import Quota
from app.core.config import LLMCatalog, LLMModelConfig, ProviderInfo, Settings
from app.extraction.routes import get_extractor
from app.extraction.service import QuestionnaireExtractor
from app.llm.client import Completion, ImagePart, Message, TextPart
from app.llm.structured import StructuredRunner
from app.main import app
from tests.base.pdf_builders import questionnaire_pdf

FLASH = LLMModelConfig(id="flash", model="gemini/flash")
OTHER = LLMModelConfig(id="other", model="gemini/other")
SETTINGS = Settings(render_dpi=50, render_max_px=400, max_pages=5)

ITEMS: list[dict[str, Any]] = [
    {
        "numero": 1,
        "enunciado": "Quale e la capitale d'Italia?",
        "tipo": "seleccion_multiple",
        "alternativas": [
            {"valor": "A", "texto": "Milano"},
            {"valor": "B", "texto": "Roma"},
            {"valor": "C", "texto": "Napoli"},
            {"valor": "D", "texto": "Torino"},
        ],
        "premisas": [],
        "respuesta_correcta": ["B"],
        "pagina": 1,
        "evidencia": "**B) Roma**",
    },
    {
        "numero": 2,
        "enunciado": "Questa domanda e molto lunga e continua.",
        "tipo": "desarrollo",
        "alternativas": [],
        "premisas": [],
        "respuesta_correcta": None,
        "pagina": 1,
        "evidencia": None,
    },
]


def _answer(items: list[dict[str, Any]]) -> Completion:
    body = {"titulo": None, "idioma": "it", "items": items}
    return Completion(json.dumps(body), input_tokens=120, output_tokens=80)


@dataclass
class ScriptedBackend:
    answers: list[Completion]
    calls: list[tuple[str, list[Message]]] = field(default_factory=list)

    async def complete(self, model: LLMModelConfig, messages: Sequence[Message]) -> Completion:
        self.calls.append((model.id, list(messages)))
        return self.answers.pop(0)


def _install(backend: ScriptedBackend, models: Sequence[LLMModelConfig] = (FLASH, OTHER)) -> None:
    providers = {"gemini": ProviderInfo(label="Gemini", description="")} if models else {}
    catalog = LLMCatalog(
        default_model=models[0].id if models else "", providers=providers, models=list(models)
    )
    runner = StructuredRunner(catalog, backend, max_retries=0, repair_attempts=1)
    app.dependency_overrides[get_extractor] = lambda: QuestionnaireExtractor(runner, SETTINGS)
    app.dependency_overrides[require_extraction_quota] = lambda: AuthenticatedClient(
        id="test", quota=Quota(per_minute=100, daily=100)
    )


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _post(filename: str = "verifica.pdf", data: bytes | None = None, **form: str) -> Any:  # noqa: ANN401
    files = {"file": (filename, data if data is not None else questionnaire_pdf())}
    return TestClient(app).post("/api/v1/questionnaires", files=files, data=form)


def test_questionnaire_is_returned_with_the_public_contract() -> None:
    _install(ScriptedBackend([_answer(ITEMS)]))

    response = _post()

    assert response.status_code == 200
    body = response.json()
    assert body["titulo"] is None
    assert body["idioma"] == "it"
    assert body["total_items"] == 2
    first = body["items"][0]
    assert set(first) == {
        "numero",
        "enunciado",
        "tipo",
        "alternativas",
        "premisas",
        "respuesta_correcta",
    }
    assert first["respuesta_correcta"] == ["B"]


def test_run_details_are_returned_in_headers() -> None:
    _install(ScriptedBackend([_answer(ITEMS)]))

    response = _post()

    assert response.headers["X-LLM-Model"] == "flash"
    assert response.headers["X-LLM-Input-Tokens"] == "120"
    assert response.headers["X-LLM-Output-Tokens"] == "80"
    assert response.headers["X-LLM-Repairs"] == "0"
    assert int(response.headers["X-LLM-Duration-Ms"]) >= 0
    assert json.loads(response.headers["X-Extraction-Warnings"]) == []


def test_document_pages_are_sent_as_text_and_image() -> None:
    backend = ScriptedBackend([_answer(ITEMS)])
    _install(backend)

    _post()

    user_parts = backend.calls[0][1][1].parts
    assert isinstance(user_parts[0], TextPart)
    assert user_parts[0].text.startswith("=== Page 1 ===\n1. Quale e la capitale d'Italia?")
    assert "**B) Roma**" in user_parts[0].text
    assert isinstance(user_parts[1], ImagePart)


def test_chosen_model_is_used() -> None:
    backend = ScriptedBackend([_answer(ITEMS)])
    _install(backend)

    response = _post(model="other")

    assert response.headers["X-LLM-Model"] == "other"
    assert backend.calls[0][0] == "other"


def test_unknown_model_is_rejected_before_calling_any_model() -> None:
    backend = ScriptedBackend([])
    _install(backend)

    response = _post(model="does-not-exist")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert backend.calls == []


def test_server_without_enabled_models_explains_it() -> None:
    _install(ScriptedBackend([]), models=())

    response = _post()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NO_MODELS_AVAILABLE"


def test_document_without_items_fails_with_no_items() -> None:
    _install(ScriptedBackend([_answer([])]))

    response = _post()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ITEMS"


def test_unsupported_file_fails_with_unsupported_format() -> None:
    _install(ScriptedBackend([]))

    response = _post(filename="notes.txt", data=b"hello")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_invented_content_is_sent_back_and_reported_when_it_persists() -> None:
    invented = [{**ITEMS[0], "enunciado": "Qual è il fiume più lungo del mondo?"}, ITEMS[1]]
    backend = ScriptedBackend([_answer(invented), _answer(invented)])
    _install(backend)

    response = _post()

    assert response.status_code == 200
    assert response.headers["X-LLM-Repairs"] == "1"
    warnings = json.loads(response.headers["X-Extraction-Warnings"])
    assert len(warnings) == 1
    assert "the enunciado was not found on page 1" in warnings[0]


def test_rule_breaking_answer_is_repaired() -> None:
    broken = [{**ITEMS[0], "respuesta_correcta": ["E"]}, ITEMS[1]]
    backend = ScriptedBackend([_answer(broken), _answer(ITEMS)])
    _install(backend)

    response = _post()

    assert response.status_code == 200
    assert response.json()["items"][0]["respuesta_correcta"] == ["B"]
    repair_request = backend.calls[1][1][-1].parts[0]
    assert isinstance(repair_request, TextPart)
    assert "respuesta_correcta 'E' is not the valor of any alternativa" in repair_request.text
