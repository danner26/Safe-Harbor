"""HTMX quick-add success swap flow."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from flask import Flask
from sqlalchemy import select


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email=f"keeper-{uuid4()}@x.com",
        password_hash=hash_password("test-pw-12345"),
    )
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


def _valid_payload(tank_id: object, *, csrf_token: str | None = None) -> dict[str, str]:
    payload = {
        "tank_id": str(tank_id),
        "parameter_key": "temperature",
        "value": "78",
        "value_unit": "degF",
        "recorded_at": "2026-04-30T13:45",
        "note": "midday",
    }
    if csrf_token is not None:
        payload["csrf_token"] = csrf_token
    return payload


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.post("/measurements/quick-add", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_htmx_path_returns_success_fragment(app: Flask, client: Any, db_session: Any) -> None:
    from safeharbor.models.measurement import Measurement

    app.config["WTF_CSRF_ENABLED"] = True
    user = _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    form_resp = client.get(f"/measurements/quick-add?tank={tank.id}")
    token = _csrf_token(form_resp.data)

    resp = client.post(
        "/measurements/quick-add",
        data=_valid_payload(tank.id, csrf_token=token),
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )

    body = resp.data.decode()
    assert resp.status_code == 200
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    assert "Logged." in body
    assert "Temperature" in body
    assert "78.0000 degF" in body
    assert "Reef 90" in body
    assert "Apr 30, 2026" in body
    assert "Log another" in body
    assert "hx-on:click" in body
    assert f'href="/tanks/{tank.id}"' in body
    assert 'target="_top"' in body

    rows = db_session.scalars(select(Measurement)).all()
    assert len(rows) == 1
    assert rows[0].recorded_by_user_id == user.id


def test_full_page_path_redirects(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    form_resp = client.get(f"/measurements/quick-add?tank={tank.id}")

    resp = client.post(
        "/measurements/quick-add",
        data=_valid_payload(tank.id, csrf_token=_csrf_token(form_resp.data)),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location is not None
    assert "logged=1" in resp.location
    assert f"tank={tank.id}" in resp.location


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)

    resp = client.post(
        "/measurements/quick-add",
        data=_valid_payload(tank.id),
        headers={"Hx-Request": "true"},
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_invalid_input_re_renders_form(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    form_resp = client.get(f"/measurements/quick-add?tank={tank.id}")
    token = _csrf_token(form_resp.data)

    resp = client.post(
        "/measurements/quick-add",
        data={
            **_valid_payload(tank.id, csrf_token=token),
            "value": "",
        },
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )

    body = resp.data.decode()
    assert resp.status_code == 200
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    form_start = body.index('<form id="quick-add-form"')
    form_end = body.index("</form>")
    banner_start = body.index("Could not log reading.")
    assert form_start < banner_start < form_end
    assert "Could not log reading." in body
    assert "Check the highlighted fields and try again." in body
    assert '<form id="quick-add-form"' in body
    assert 'hx-post="/measurements/quick-add"' in body
    assert 'hx-target="#qa-success-region"' in body
    assert 'hx-swap="innerHTML"' in body
    assert "hx-on::after-request" in body
    assert "data-qa-validation-banner" in body
    assert 'name="value"' in body
    assert 'name="parameter_key"' in body
    assert 'id="qa-success-region"' not in body
    assert resp.headers.get("Hx-Retarget") == "#quick-add-form"
    assert resp.headers.get("Hx-Reswap") == "outerHTML"
