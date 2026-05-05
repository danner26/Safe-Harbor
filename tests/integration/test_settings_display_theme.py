"""Settings display preferences - theme preference."""

from __future__ import annotations


def _login(client, db_session, *, email="theme@x.com", theme_pref=None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email=email,
        password_hash=hash_password("test-pw-12345"),
        theme_pref=theme_pref,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client) -> None:
    resp = client.post(
        "/settings/display",
        data={"units": "", "theme": "light", "date_format": ""},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_theme_renders_current_pref(client, db_session) -> None:
    _login(client, db_session, theme_pref="dark")

    resp = client.get("/settings/display")

    assert resp.status_code == 200
    assert b'name="theme" value="dark" checked' in resp.data


def test_theme_persists_per_user(client, db_session) -> None:
    user = _login(client, db_session, theme_pref=None)

    client.post(
        "/settings/display",
        data={"units": "", "theme": "light", "date_format": ""},
    )

    db_session.refresh(user)
    assert user.theme_pref == "light"


def test_theme_null_means_auto(client, db_session) -> None:
    user = _login(client, db_session, theme_pref="dark")

    client.post(
        "/settings/display",
        data={"units": "", "theme": "", "date_format": ""},
    )

    db_session.refresh(user)
    assert user.theme_pref is None


def test_theme_rejects_unknown_values(client, db_session) -> None:
    user = _login(client, db_session, theme_pref="dark")

    resp = client.post(
        "/settings/display",
        data={"units": "", "theme": "neon", "date_format": ""},
        follow_redirects=False,
    )

    db_session.refresh(user)
    assert resp.status_code == 200
    assert user.theme_pref == "dark"
