"""Integration tests for KPI range badges on dashboard and tank detail."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from flask import Flask
from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="kpi-range@example.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_reference_data(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank_with_temperature(
    app: Flask,
    db_session: Any,
    *,
    value: Decimal | None,
) -> Any:
    from sqlalchemy import select

    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = Tank(name="Badge Reef", water_type="salt", profile_key="reef_sw")
    db_session.add(tank)
    db_session.commit()

    if value is None:
        return tank

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temperature,
        value=value,
        value_unit="degC",
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()
    return tank


def _card_for_label(body: str, label: str) -> str:
    label_marker = f'<div class="kpi-label">{label}</div>'
    start = body.index(label_marker)
    next_card = body.find('<div class="kpi-card', start + len(label_marker))
    if next_card == -1:
        return body[start:]
    return body[start:next_card]


def test_unauthenticated_redirects_to_login(client: FlaskClient, configured_user) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_kpi_card_with_in_range_value_shows_no_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, value=Decimal("25.5"))

    dashboard = client.get("/")
    detail = client.get(f"/tanks/{tank.id}")
    dashboard_temperature = _card_for_label(dashboard.data.decode(), "Temperature")
    detail_temperature = _card_for_label(detail.data.decode(), "Temperature")

    assert dashboard.status_code == 200
    assert detail.status_code == 200
    assert "Out of range" not in dashboard_temperature
    assert "Caution" not in dashboard_temperature
    assert "Out of range" not in detail_temperature
    assert "Caution" not in detail_temperature


def test_kpi_card_with_out_of_range_value_shows_danger_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, value=Decimal("30.0"))

    dashboard = client.get("/")
    detail = client.get(f"/tanks/{tank.id}")
    dashboard_temperature = _card_for_label(dashboard.data.decode(), "Temperature")
    detail_temperature = _card_for_label(detail.data.decode(), "Temperature")

    assert 'class="badge bg-danger"' in dashboard_temperature
    assert "Out of range" in dashboard_temperature
    assert 'class="badge bg-danger"' in detail_temperature
    assert "Out of range" in detail_temperature


def test_kpi_card_with_caution_value_shows_caution_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, value=Decimal("24.5"))

    dashboard = client.get("/")
    detail = client.get(f"/tanks/{tank.id}")
    dashboard_temperature = _card_for_label(dashboard.data.decode(), "Temperature")
    detail_temperature = _card_for_label(detail.data.decode(), "Temperature")

    assert 'class="badge bg-warning text-dark"' in dashboard_temperature
    assert "Caution" in dashboard_temperature
    assert 'class="badge bg-warning text-dark"' in detail_temperature
    assert "Caution" in detail_temperature


def test_kpi_card_with_no_measurement_shows_no_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, value=None)

    dashboard = client.get("/")
    detail = client.get(f"/tanks/{tank.id}")
    dashboard_temperature = _card_for_label(dashboard.data.decode(), "Temperature")
    detail_temperature = _card_for_label(detail.data.decode(), "Temperature")

    assert "&mdash;" in dashboard_temperature
    assert "&mdash;" in detail_temperature
    assert "Out of range" not in dashboard_temperature
    assert "Caution" not in dashboard_temperature
    assert "Out of range" not in detail_temperature
    assert "Caution" not in detail_temperature
