import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import HTTP_STATUS_BY_CODE
from app.core.errors import DEFAULT_MESSAGES, AppError, ErrorCode
from app.main import create_app


def _app_with_failing_routes() -> FastAPI:
    app = create_app()

    @app.get("/no-items")
    def no_items() -> None:
        raise AppError(ErrorCode.NO_ITEMS)

    @app.get("/rate-limited")
    def rate_limited() -> None:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after_s=30)

    @app.get("/custom-message")
    def custom_message() -> None:
        raise AppError(ErrorCode.INVALID_FILE, "The DOCX archive is corrupted.")

    @app.get("/needs-param")
    def needs_param(limit: int) -> int:
        return limit

    @app.get("/crash")
    def crash() -> None:
        message = "secret internal detail"
        raise RuntimeError(message)

    return app


@pytest.fixture
def failing_client() -> TestClient:
    return TestClient(_app_with_failing_routes(), raise_server_exceptions=False)


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_error_code_has_http_status_and_default_message(code: ErrorCode) -> None:
    assert code in HTTP_STATUS_BY_CODE
    assert DEFAULT_MESSAGES[code]


def test_app_error_returns_its_code_status_and_default_message(
    failing_client: TestClient,
) -> None:
    response = failing_client.get("/no-items")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "NO_ITEMS",
            "message": DEFAULT_MESSAGES[ErrorCode.NO_ITEMS],
            "request_id": response.headers["X-Request-ID"],
        }
    }


def test_app_error_keeps_a_custom_message(failing_client: TestClient) -> None:
    response = failing_client.get("/custom-message")

    assert response.json()["error"]["message"] == "The DOCX archive is corrupted."


def test_rate_limited_error_sets_retry_after_header(failing_client: TestClient) -> None:
    response = failing_client.get("/rate-limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"


def test_unknown_route_returns_not_found_error(failing_client: TestClient) -> None:
    response = failing_client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_wrong_method_keeps_its_status_with_invalid_request_code(
    failing_client: TestClient,
) -> None:
    response = failing_client.post("/no-items")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_parameters_return_invalid_request_naming_the_field(
    failing_client: TestClient,
) -> None:
    response = failing_client.get("/needs-param", params={"limit": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert "query.limit" in error["message"]
    assert "not-a-number" not in error["message"]


def test_unexpected_exception_returns_internal_error_without_details(
    failing_client: TestClient,
) -> None:
    response = failing_client.get("/crash")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "secret" not in error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]
