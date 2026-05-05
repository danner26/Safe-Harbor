"""Integration guards for flash alert close controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _login_with_flash(client: Any, db_session: Any) -> None:
    from safeharbor.models.account import User

    user = User(email="alert-dismiss@example.com", password_hash="h")
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_flashes"] = [("success", "Saved successfully")]


def test_alert_dismiss_button_renders_with_icon(client: Any, db_session: Any) -> None:
    _login_with_flash(client, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'class="btn-close"' in body

    css = Path("src/safeharbor/static/css/app.css").read_text()
    assert ".btn-close" in css
    assert "data:image/svg+xml,%3Csvg" in css
    assert "fill='currentColor'" in css


def test_alert_dismiss_handler_is_loaded(client: Any, db_session: Any) -> None:
    _login_with_flash(client, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "document.addEventListener('click'" in body
    assert "closest('.alert .btn-close')" in body
