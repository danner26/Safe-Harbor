"""Auth-gating coverage for measurement and tank history routes."""

from __future__ import annotations

from typing import Any

TANK_ID = "00000000-0000-0000-0000-000000000001"


def test_quick_add_get_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.get("/measurements/quick-add")

    assert response.status_code == 302
    assert "/login" in response.location


def test_quick_add_post_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.post("/measurements/quick-add")

    assert response.status_code == 302
    assert "/login" in response.location


def test_batch_get_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.get(f"/measurements/batch?tank={TANK_ID}")

    assert response.status_code == 302
    assert "/login" in response.location


def test_batch_post_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.post("/measurements/batch", data={"tank_id": TANK_ID})

    assert response.status_code == 302
    assert "/login" in response.location


def test_tanks_history_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.get(f"/tanks/{TANK_ID}/history")

    assert response.status_code == 302
    assert "/login" in response.location


def test_tanks_chart_data_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    response = client.get(f"/tanks/{TANK_ID}/chart-data?parameter=temperature&range=30d")

    assert response.status_code == 302
    assert "/login" in response.location
