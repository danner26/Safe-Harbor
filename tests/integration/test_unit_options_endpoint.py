"""Unit option fragment endpoint for measurement parameter changes."""

from __future__ import annotations

import re


def _login(client, db_session, *, preferred_units: str | None = None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="unit-options@example.com",
        password_hash=hash_password("test-pw-12345"),
        preferred_units=preferred_units,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_units_for_parameter_returns_only_valid_unit_options(client, db_session) -> None:
    _login(client, db_session)

    resp = client.get("/measurements/units-for-parameter/ph")

    assert resp.status_code == 200
    assert re.search(rb'<option selected value="pH">pH</option>', resp.data)
    assert b"degC" not in resp.data
    assert b"degF" not in resp.data
    assert b"ppm" not in resp.data


def test_units_for_parameter_rejects_unknown_parameter(client, db_session) -> None:
    _login(client, db_session)

    resp = client.get("/measurements/units-for-parameter/banana")

    assert resp.status_code == 400


def test_units_for_parameter_marks_install_preferred_temperature_default_selected(
    client, db_session
) -> None:
    _login(client, db_session, preferred_units="imperial")

    resp = client.get("/measurements/units-for-parameter/temperature")

    assert resp.status_code == 200
    assert re.search(rb'<option value="degC">degC</option>', resp.data)
    assert re.search(rb'<option selected value="degF">degF</option>', resp.data)
