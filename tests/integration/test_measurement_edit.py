"""GET + POST /measurements/<id>/edit - measurement edit flow."""

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


def _seed_tank(
    db_session: Any,
    *,
    name: str = "Reef 90",
    water_type: str = "salt",
    timezone: str = "UTC",
) -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type=water_type, timezone=timezone)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_measurement(
    app: Flask,
    db_session: Any,
    *,
    value: Decimal = Decimal("78"),
    value_unit: str = "degF",
    parameter_key: str = "temperature",
    note: str | None = "morning",
    tank_timezone: str = "UTC",
) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = _seed_tank(db_session, timezone=tank_timezone)
    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == parameter_key)
    )
    assert parameter_type is not None
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=value,
        value_unit=value_unit,
        recorded_at=datetime(2026, 4, 30, 13, 45, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=note,
    )
    db_session.commit()
    return measurement


def _edit_payload(**overrides: Any) -> dict[str, str]:
    payload = {
        "value": "79.5",
        "value_unit": "degF",
        "recorded_at": "2026-05-01T09:30",
        "note": "after water change",
        "submit": "Save reading",
    }
    payload.update({key: str(value) for key, value in overrides.items()})
    return payload


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.get(f"/measurements/{uuid4()}/edit", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_get_returns_form_pre_populated_from_existing_measurement(
    client: Any,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.get(f"/measurements/{measurement.id}/edit")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Edit reading" in body
    assert f'action="/measurements/{measurement.id}/edit"' in body
    assert 'name="csrf_token"' in body
    assert 'name="value"' in body
    assert 'value="78.0000"' in body
    assert 'name="value_unit"' in body
    assert '<option selected value="degF">degF</option>' in body
    assert 'name="recorded_at"' in body
    assert 'value="2026-04-30T13:45"' in body
    assert 'name="note"' in body
    assert 'value="morning"' in body
    assert re.search(r'name="tank_id"', body) is None
    assert re.search(r'name="parameter_type"', body) is None
    assert re.search(r'name="parameter_key"', body) is None


def test_get_prefills_recorded_at_in_tank_local_time(
    client: Any,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(
        app,
        db_session,
        tank_timezone="America/Los_Angeles",
    )

    resp = client.get(f"/measurements/{measurement.id}/edit")

    assert resp.status_code == 200
    assert 'value="2026-04-30T06:45"' in resp.data.decode()


def test_get_404_on_unknown_measurement(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get(f"/measurements/{uuid4()}/edit")

    assert resp.status_code == 404


def test_history_row_links_to_edit_form(client: Any, app: Flask, db_session: Any) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}/history")

    assert resp.status_code == 200
    assert f'href="/measurements/{measurement.id}/edit"' in resp.data.decode()


def test_recent_table_links_to_edit_form(client: Any, app: Flask, db_session: Any) -> None:
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}")

    assert resp.status_code == 200
    assert f'href="/measurements/{measurement.id}/edit"' in resp.data.decode()


def test_post_updates_measurement(client: Any, app: Flask, db_session: Any) -> None:
    from safeharbor.models.measurement import Measurement

    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.post(
        f"/measurements/{measurement.id}/edit",
        data=_edit_payload(),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.expire_all()
    edited = db_session.get(Measurement, measurement.id)
    assert edited is not None
    assert edited.value == Decimal("26.3889")
    assert edited.raw_value == Decimal("79.5000")
    assert edited.note == "after water change"
    assert edited.recorded_at == datetime(2026, 5, 1, 9, 30, tzinfo=UTC)


def test_post_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)

    resp = client.post(
        f"/measurements/{measurement.id}/edit",
        data=_edit_payload(),
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_post_redirects_to_history_with_flash(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    measurement = _seed_measurement(app, db_session)
    form_resp = client.get(f"/measurements/{measurement.id}/edit")

    resp = client.post(
        f"/measurements/{measurement.id}/edit",
        data={"csrf_token": _csrf_token(form_resp.data), **_edit_payload()},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert f"/tanks/{measurement.tank_id}/history" in resp.request.path
    assert b"Saved reading." in resp.data


def test_post_invalid_unit_re_renders_form_with_error(
    client: Any,
    app: Flask,
    db_session: Any,
) -> None:
    from safeharbor.models.measurement import Measurement

    _login(client, db_session)
    measurement = _seed_measurement(
        app,
        db_session,
        value=Decimal("8.1"),
        value_unit="pH",
        parameter_key="ph",
        note="before",
    )

    resp = client.post(
        f"/measurements/{measurement.id}/edit",
        data=_edit_payload(value="8.3", value_unit="degF"),
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Not a valid choice" in resp.data
    db_session.expire_all()
    unchanged = db_session.get(Measurement, measurement.id)
    assert unchanged is not None
    assert unchanged.value == Decimal("8.1000")
    assert unchanged.note == "before"
