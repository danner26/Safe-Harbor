"""Admin-initiated password-reset redemption."""

from __future__ import annotations


def _seed_admin_and_user(db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    admin = User(
        email="admin@x.com", password_hash=hash_password("admin-pw-12345"), is_superuser=True
    )
    user = User(email="alice@x.com", password_hash=hash_password("old-password-x"))
    db_session.add_all([admin, user])
    db_session.commit()
    return admin, user


def _issue_reset(app, db_session, admin_id, email: str) -> str:
    from safeharbor.models.invite import InviteKind
    from safeharbor.services.auth_service import issue_invite_token

    with app.app_context():
        token, _ = issue_invite_token(
            email=email, kind=InviteKind.PASSWORD_RESET, issued_by=admin_id
        )
        db_session.commit()
    return token


def test_reset_get_with_valid_token_renders_form(client, app, db_session) -> None:
    admin, user = _seed_admin_and_user(db_session)
    token = _issue_reset(app, db_session, admin.id, user.email)

    resp = client.get(f"/password-reset/{token}")
    assert resp.status_code == 200
    assert b'name="password"' in resp.data


def test_reset_get_with_bogus_token_shows_error(client) -> None:
    resp = client.get("/password-reset/bogus")
    assert resp.status_code == 200
    assert b"invalid or expired" in resp.data.lower()


def test_reset_post_updates_password_and_logs_in(client, app, db_session) -> None:
    from safeharbor.services.auth_service import verify_password

    admin, user = _seed_admin_and_user(db_session)
    token = _issue_reset(app, db_session, admin.id, user.email)

    resp = client.post(
        f"/password-reset/{token}",
        data={"password": "shiny-new-password", "confirm": "shiny-new-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db_session.refresh(user)
    assert verify_password("shiny-new-password", user.password_hash) is True
    assert verify_password("old-password-x", user.password_hash) is False


def test_reset_post_consumes_token(client, app, db_session) -> None:
    admin, user = _seed_admin_and_user(db_session)
    token = _issue_reset(app, db_session, admin.id, user.email)

    client.post(
        f"/password-reset/{token}",
        data={"password": "shiny-new-password", "confirm": "shiny-new-password"},
    )
    # Second redemption rejected
    resp = client.post(
        f"/password-reset/{token}",
        data={"password": "shiny-new-password", "confirm": "shiny-new-password"},
    )
    assert resp.status_code == 200
    assert b"invalid or expired" in resp.data.lower()


def test_reset_post_rejects_short_password(client, app, db_session) -> None:
    admin, user = _seed_admin_and_user(db_session)
    token = _issue_reset(app, db_session, admin.id, user.email)
    resp = client.post(f"/password-reset/{token}", data={"password": "x", "confirm": "x"})
    assert resp.status_code == 200
    assert b"at least 10" in resp.data or b"too short" in resp.data.lower()
