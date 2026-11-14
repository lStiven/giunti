import re

from fastapi.testclient import TestClient


def test_response_gets_a_generated_request_id(client: TestClient) -> None:
    response = client.get("/health")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_valid_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "client-trace.42"})

    assert response.headers["X-Request-ID"] == "client-trace.42"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id\twith spaces"})

    assert response.headers["X-Request-ID"] != "bad id\twith spaces"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
