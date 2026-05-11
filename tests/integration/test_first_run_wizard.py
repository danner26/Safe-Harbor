"""First-run setup wizard integration coverage."""

from __future__ import annotations

import re
from unittest.mock import patch
from urllib.parse import urlsplit

from flask import Flask, url_for
from flask.testing import FlaskClient
from sqlalchemy import select


def _path(location: str | None) -> str:
    assert location is not None
    return urlsplit(location).path


def _endpoint_path(app: Flask, endpoint: str, **values: str) -> str:
    with app.test_request_context():
        return url_for(endpoint, **values)


def _csrf_token(response_data: bytes) -> str:
    match = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', response_data)
    assert match is not None
    return match.group(1).decode()


def _valid_setup_payload(*, csrf_token: str | None = None) -> dict[str, str]:
    payload = {
        "email": "Admin@Example.com",
        "password": "admin-password-12345",
        "confirm_password": "admin-password-12345",
        "preferred_units": "metric",
    }
    if csrf_token is not None:
        payload["csrf_token"] = csrf_token
    return payload


def _seed_user(db_session, *, email: str = "admin@x.com") -> User:  # noqa: F821
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email=email,
        password_hash=hash_password("admin-password-12345"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _user_count(db_session) -> int:
    from safeharbor.models.account import User

    return len(db_session.scalars(select(User)).all())


def test_empty_db_root_redirects_to_setup(app: Flask, client: FlaskClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert _path(response.location) == _endpoint_path(app, "setup.show_or_create")


def test_empty_db_login_redirects_to_setup(app: Flask, client: FlaskClient) -> None:
    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 302
    assert _path(response.location) == _endpoint_path(app, "setup.show_or_create")


def test_empty_db_healthz_remains_public(client: FlaskClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200


def test_empty_db_static_remains_public(app: Flask, client: FlaskClient) -> None:
    static_path = _endpoint_path(app, "static", filename="css/app.css")

    response = client.get(static_path)

    assert response.status_code in (200, 404)
    if response.location is not None:
        assert _path(response.location) != _endpoint_path(app, "setup.show_or_create")


def test_empty_db_valid_setup_creates_superuser_and_redirects_to_login(
    app: Flask, client: FlaskClient, db_session
) -> None:
    from safeharbor.models.account import User

    response = client.post(
        _endpoint_path(app, "setup.show_or_create"),
        data=_valid_setup_payload(),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _path(response.location) == _endpoint_path(app, "auth.login")
    users = db_session.scalars(select(User)).all()
    assert len(users) == 1
    assert users[0].email == "admin@example.com"
    assert users[0].is_superuser is True
    assert users[0].preferred_units == "metric"


def test_empty_db_setup_race_returns_404_and_leaves_session_clean(
    app: Flask, client: FlaskClient, db_session
) -> None:
    with patch(
        "safeharbor.blueprints.setup.views.create_first_admin",
        side_effect=ValueError("a user already exists"),
    ):
        response = client.post(
            _endpoint_path(app, "setup.show_or_create"),
            data=_valid_setup_payload(),
            follow_redirects=False,
        )

    assert response.status_code == 404
    assert _user_count(db_session) == 0


def test_empty_db_setup_rejects_missing_csrf_token(
    app: Flask, client: FlaskClient, db_session
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        _endpoint_path(app, "setup.show_or_create"),
        data=_valid_setup_payload(),
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert _user_count(db_session) == 0


def test_empty_db_setup_accepts_valid_csrf_token(
    app: Flask, client: FlaskClient, db_session
) -> None:
    from safeharbor.models.account import User

    app.config["WTF_CSRF_ENABLED"] = True
    form_response = client.get(_endpoint_path(app, "setup.show_or_create"))

    response = client.post(
        _endpoint_path(app, "setup.show_or_create"),
        data=_valid_setup_payload(csrf_token=_csrf_token(form_response.data)),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _path(response.location) == _endpoint_path(app, "auth.login")
    users = db_session.scalars(select(User)).all()
    assert len(users) == 1
    assert users[0].is_superuser is True


def test_empty_db_setup_rejects_mismatched_passwords(
    app: Flask, client: FlaskClient, db_session
) -> None:
    response = client.post(
        _endpoint_path(app, "setup.show_or_create"),
        data={
            "email": "admin@example.com",
            "password": "admin-password-12345",
            "confirm_password": "different-password-12345",
            "preferred_units": "imperial",
        },
    )

    assert response.status_code == 200
    assert b"Passwords must match" in response.data
    assert _user_count(db_session) == 0


def test_empty_db_setup_rejects_short_password(app: Flask, client: FlaskClient, db_session) -> None:
    response = client.post(
        _endpoint_path(app, "setup.show_or_create"),
        data={
            "email": "admin@example.com",
            "password": "short",
            "confirm_password": "short",
            "preferred_units": "imperial",
        },
    )

    assert response.status_code == 200
    assert b"Field must be at least 10 characters long." in response.data
    assert _user_count(db_session) == 0


def test_user_exists_setup_returns_404(client: FlaskClient, db_session) -> None:
    _seed_user(db_session)

    response = client.get("/setup")

    assert response.status_code == 404


def test_user_exists_root_uses_normal_app_flow(app: Flask, client: FlaskClient, db_session) -> None:
    _seed_user(db_session)

    response = client.get("/", follow_redirects=False)

    assert _path(response.location) != _endpoint_path(app, "setup.show_or_create")
    assert response.status_code in (200, 302)
