"""GET /tanks/<id> — detail view with canvas-faithful empty states."""

from __future__ import annotations

from datetime import date
from typing import Any

from flask import url_for


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email="viewer@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def _login_with_units(client: Any, db_session: Any, units_pref: str | None) -> Any:
    user = _login(client, db_session)
    user.preferred_units = units_pref
    db_session.commit()
    return user


def _seed(db_session: Any, **kwargs: Any) -> Any:
    from safeharbor.models.tank import Tank

    t = Tank(
        name=kwargs.pop("name", "Reef 90"), water_type=kwargs.pop("water_type", "salt"), **kwargs
    )
    db_session.add(t)
    db_session.commit()
    return t


def test_detail_404_for_unknown_id(client: Any, db_session: Any) -> None:
    from uuid import uuid4

    _login(client, db_session)
    resp = client.get(f"/tanks/{uuid4()}")
    assert resp.status_code == 404


def test_detail_renders_tank_metadata(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Reef 90", water_type="salt")
    resp = client.get(f"/tanks/{tank.id}")
    assert resp.status_code == 200
    assert b"Reef 90" in resp.data
    assert b"Saltwater" in resp.data


def test_hero_photo_renders_when_image_path_set(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Reef 90", image_path="tanks/reef-90.webp")

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'src="{url_for("tanks.serve_image", tank_id=tank.id)}"' in body
    assert 'alt="Reef 90 photo"' in body
    assert 'class="tphoto' not in body


def test_placeholder_renders_when_image_path_null(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Reef 90", image_path=None)

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'class="tphoto salt"' in body
    assert url_for("tanks.serve_image", tank_id=tank.id) not in body


def test_detail_shows_edit_button_for_active_tank(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Active 1")
    resp = client.get(f"/tanks/{tank.id}")
    assert b"Edit" in resp.data
    assert b"Decommission" in resp.data
    assert b"Restore" not in resp.data


def test_detail_shows_restore_button_for_decommissioned_tank(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Old", decommission_date=date(2024, 1, 1))
    resp = client.get(f"/tanks/{tank.id}")
    assert b"Restore" in resp.data
    assert b"Decommission" not in resp.data or b"Decommissioned" in resp.data  # banner ok


def test_detail_shows_empty_state_for_measurements(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session)
    resp = client.get(f"/tanks/{tank.id}")
    assert b"No readings yet" in resp.data


def test_detail_shows_empty_state_for_animals(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session)
    resp = client.get(f"/tanks/{tank.id}")
    assert "No animals on this tank yet — Add one →" in resp.data.decode()


def test_detail_renders_equipment_notes_with_newlines(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session, equipment_notes="Eheim 2217\nFluval 3.0 LED")
    resp = client.get(f"/tanks/{tank.id}")
    # <pre> with white-space: pre-wrap preserves the newlines as text
    assert b"Eheim 2217" in resp.data
    assert b"Fluval 3.0 LED" in resp.data


def test_tank_detail_kpi_strip_uses_latest_measurements(
    client: Any, db_session: Any, app: Any
) -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])
    user = _login_with_units(client, db_session, "metric")
    tank = _seed(db_session, name="Reef 90", water_type="salt")
    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=datetime.now(UTC),
        source="manual",
        recorded_by_user_id=user.id,
        note=None,
    )
    db_session.commit()

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "25.0" in body
    assert "°C" in body
    assert "trend-chart" in body
    assert "vendor/plotly/plotly.js-cartesian.min.js" in body
    assert '<div class="card" style="padding: 0; overflow: hidden;">' not in body


def test_tank_detail_log_a_reading_button_links_quick_add(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed(db_session)

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f"/measurements/quick-add?tank={tank.id}" in body


def test_tank_detail_decommission_confirm_js_escapes_tank_name(
    client: Any, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Bob's Reef")

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Decommission Bob\\u0027s Reef?" in body
