"""HTMX tank decommission/restore button swaps."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from flask import Flask


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
        rb'<input[^>]+name="csrf_token"[^>]+value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _seed_tank(
    db_session: Any,
    *,
    name: str = "Reef 90",
    decommission_date: date | None = None,
) -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type="salt", decommission_date=decommission_date)
    db_session.add(tank)
    db_session.commit()
    return tank


def test_unauthenticated_redirects_to_login(client: Any, db_session: Any) -> None:
    tank = _seed_tank(db_session)

    resp = client.post(f"/tanks/{tank.id}/decommission", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_htmx_decommission_returns_restore_button_fragment(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    token = _csrf_token(client.get(f"/tanks/{tank.id}").data)

    resp = client.post(
        f"/tanks/{tank.id}/decommission",
        data={"csrf_token": token},
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )

    body = resp.data.decode()
    assert resp.status_code == 200
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    assert "Restore" in body
    assert "Decommission" not in body
    assert f'hx-post="/tanks/{tank.id}/restore"' in body
    assert 'hx-target="this"' in body
    assert 'hx-swap="outerHTML"' in body
    assert 'name="csrf_token"' in body
    db_session.refresh(tank)
    assert tank.decommission_date == datetime.now(UTC).date()


def test_htmx_restore_returns_decommission_button_fragment(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session, decommission_date=date(2024, 1, 1))
    token = _csrf_token(client.get(f"/tanks/{tank.id}").data)

    resp = client.post(
        f"/tanks/{tank.id}/restore",
        data={"csrf_token": token},
        headers={"Hx-Request": "true", "X-CSRFToken": token},
        follow_redirects=False,
    )

    body = resp.data.decode()
    assert resp.status_code == 200
    assert "<html" not in body.lower()
    assert "<body" not in body.lower()
    assert "Decommission" in body
    assert "Restore" not in body
    assert f'hx-post="/tanks/{tank.id}/decommission"' in body
    assert 'hx-target="this"' in body
    assert 'hx-swap="outerHTML"' in body
    assert 'name="csrf_token"' in body
    db_session.refresh(tank)
    assert tank.decommission_date is None


def test_full_page_decommission_redirects(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    token = _csrf_token(client.get(f"/tanks/{tank.id}").data)

    resp = client.post(
        f"/tanks/{tank.id}/decommission",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location is not None
    assert resp.location.endswith("/tanks")


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/decommission",
        headers={"Hx-Request": "true"},
        follow_redirects=False,
    )

    assert resp.status_code == 400
