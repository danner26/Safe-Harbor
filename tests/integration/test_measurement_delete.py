"""POST /measurements/<id>/delete - measurement delete flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flask import Flask
from sqlalchemy import select


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="keeper@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _seed_reference_data(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank(db_session: Any, *, name: str = "Reef 90", water_type: str = "salt") -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type=water_type)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_measurement(
    app: Flask,
    db_session: Any,
    *,
    note: str | None = "morning typo",
) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("78"),
        value_unit="degF",
        recorded_at=datetime(2026, 4, 30, 13, 45, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=note,
    )
    db_session.commit()
    return measurement


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.post(f"/measurements/{uuid4()}/delete", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_post_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.post(f"/measurements/{measurement.id}/delete", follow_redirects=False)

    assert resp.status_code == 400


def test_full_page_path_redirects_with_flash(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.measurement import Measurement

    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)
    measurement_id = measurement.id
    tank_id = measurement.tank_id
    form_resp = client.get(f"/tanks/{tank_id}/history")

    resp = client.post(
        f"/measurements/{measurement_id}/delete",
        data={"csrf_token": _csrf_token(form_resp.data)},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert resp.request.path == f"/tanks/{tank_id}/history"
    assert b"Reading deleted." in resp.data
    assert db_session.get(Measurement, measurement_id) is None


def test_htmx_path_returns_empty_200(app: Flask, client: Any, db_session: Any) -> None:
    from safeharbor.models.measurement import Measurement

    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)
    measurement_id = measurement.id
    form_resp = client.get(f"/tanks/{measurement.tank_id}/history")
    token = _csrf_token(form_resp.data)

    resp = client.post(
        f"/measurements/{measurement_id}/delete",
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert resp.data == b""
    assert db_session.get(Measurement, measurement_id) is None


def test_row_removed_after_delete(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session, note="delete me")
    measurement_id = measurement.id
    tank_id = measurement.tank_id
    form_resp = client.get(f"/tanks/{tank_id}/history")
    token = _csrf_token(form_resp.data)

    resp = client.post(
        f"/measurements/{measurement_id}/delete",
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )
    history_resp = client.get(f"/tanks/{tank_id}/history")

    assert resp.status_code == 200
    assert str(measurement_id).encode() not in history_resp.data
    assert b"delete me" not in history_resp.data


def test_404_on_unknown_measurement(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.post(f"/measurements/{uuid4()}/delete", follow_redirects=False)

    assert resp.status_code == 404


def test_history_row_renders_delete_modal_trigger(
    client: Any,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}/history")

    body = resp.data.decode()
    assert f'data-bs-target="#delete-measurement-{measurement.id}"' in body
    assert f'action="/measurements/{measurement.id}/delete"' in body
    assert f'hx-post="/measurements/{measurement.id}/delete"' in body
    assert 'hx-target="closest tr"' in body
    assert 'hx-swap="outerHTML"' in body


def test_recent_table_renders_delete_modal_trigger(
    client: Any,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}")

    body = resp.data.decode()
    assert f'data-bs-target="#delete-measurement-{measurement.id}"' in body
    assert f'action="/measurements/{measurement.id}/delete"' in body
