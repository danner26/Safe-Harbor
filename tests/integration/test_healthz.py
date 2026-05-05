"""/healthz returns 200 with three sub-checks."""

from __future__ import annotations


def test_healthz_returns_200(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_payload_shape(client) -> None:
    response = client.get("/healthz")
    body = response.get_json()
    assert body["status"] == "ok"
    assert "db" in body
    assert "redis" in body


def test_healthz_db_check_green(client) -> None:
    response = client.get("/healthz")
    body = response.get_json()
    assert body["db"] == "ok"
