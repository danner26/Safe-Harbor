"""Integration tests for measurement history range badges."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import event, select


@pytest.fixture
def template_app() -> Generator[Flask, None, None]:
    template_dir = Path(__file__).parents[2] / "src" / "safeharbor" / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    with app.app_context():
        yield app


def _render_badge(template_app: Flask, status: str) -> str:
    with template_app.app_context():
        template = template_app.jinja_env.get_template("measurements/_range_badge.html")
        return template.render(status=status)


def test_badge_partial_renders_nothing_for_ok(template_app: Flask) -> None:
    rendered = _render_badge(template_app, "ok")

    assert rendered.strip() == ""


def test_badge_partial_renders_caution_pill(template_app: Flask) -> None:
    rendered = _render_badge(template_app, "caution")

    assert 'class="badge bg-warning text-dark"' in rendered
    assert "Caution" in rendered


def test_badge_partial_renders_danger_pill(template_app: Flask) -> None:
    rendered = _render_badge(template_app, "danger")

    assert 'class="badge bg-danger"' in rendered
    assert "Out of range" in rendered


def test_badge_partial_has_aria_label(template_app: Flask) -> None:
    caution = _render_badge(template_app, "caution")
    danger = _render_badge(template_app, "danger")

    assert 'aria-label="Approaching range bound"' in caution
    assert 'aria-label="Out of safe range"' in danger


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="history-range@example.com", password_hash=hash_password("test-pw-12345"))
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
    values: list[Decimal],
    profile_key: str = "reef_sw",
) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = Tank(name="History Reef", water_type="salt", profile_key=profile_key)
    db_session.add(tank)
    db_session.commit()

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for index, value in enumerate(values):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=temperature,
            value=value,
            value_unit="degC",
            recorded_at=base + timedelta(minutes=index),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    db_session.commit()
    return tank


def _history_row_for_temperature(body: str) -> str:
    marker = "Temperature"
    tbody_at = body.index("<tbody>")
    marker_at = body.index(marker, tbody_at)
    start = body.rindex("<tr", 0, marker_at)
    end = body.index("</tr>", marker_at)
    return body[start:end]


def test_unauthenticated_redirects_to_login(client: FlaskClient) -> None:
    response = client.get(f"/tanks/{uuid4()}/history", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_history_row_with_in_range_value_shows_no_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, values=[Decimal("25.5")])

    response = client.get(f"/tanks/{tank.id}/history")
    body = response.data.decode()

    assert response.status_code == 200
    row = _history_row_for_temperature(body)
    assert "Temperature" in row
    assert " °C" in row
    assert "Out of range" not in row
    assert "Caution" not in row


def test_history_row_with_danger_value_shows_danger_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, values=[Decimal("30.0")])

    response = client.get(f"/tanks/{tank.id}/history")
    body = response.data.decode()

    assert response.status_code == 200
    row = _history_row_for_temperature(body)
    assert 'class="badge bg-danger"' in row
    assert "Out of range" in row


def test_history_row_uses_tank_profile_for_caution_badge(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temperature(
        app,
        db_session,
        values=[Decimal("24.5")],
        profile_key="reef_sw",
    )

    response = client.get(f"/tanks/{tank.id}/history")
    body = response.data.decode()

    assert response.status_code == 200
    row = _history_row_for_temperature(body)
    assert 'class="badge bg-warning text-dark"' in row
    assert "Caution" in row


def test_history_constant_query_count(client: FlaskClient, app: Flask, db_session: Any) -> None:
    from safeharbor.extensions import db
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    _login(client, db_session)
    tank = _seed_tank_with_temperature(app, db_session, values=[Decimal("25.0")])
    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None

    counts: list[int] = []

    def count_queries() -> None:
        count = 0

        def before_cursor_execute(*args: Any) -> None:
            nonlocal count
            count += 1

        event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get(f"/tanks/{tank.id}/history")
        finally:
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        counts.append(count)

    count_queries()
    base = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)
    for index in range(5):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=temperature,
            value=Decimal("25.0"),
            value_unit="degC",
            recorded_at=base + timedelta(minutes=index),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    db_session.commit()
    count_queries()

    assert counts[1] <= counts[0] + 1
