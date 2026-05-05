"""Settings display preferences - date format preference."""

from __future__ import annotations


def _login(client, db_session, *, date_format_pref=None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="date-format@x.com",
        password_hash=hash_password("test-pw-12345"),
        date_format_pref=date_format_pref,
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
        data={"units": "", "theme": "", "date_format": "us"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_date_format_renders_current_pref(client, db_session) -> None:
    _login(client, db_session, date_format_pref="iso")

    resp = client.get("/settings/display")

    assert resp.status_code == 200
    assert b'<option selected value="iso">' in resp.data


def test_date_format_persists_per_user(client, db_session) -> None:
    user = _login(client, db_session, date_format_pref=None)

    client.post(
        "/settings/display",
        data={"units": "", "theme": "", "date_format": "us"},
    )

    db_session.refresh(user)
    assert user.date_format_pref == "us"


def test_date_format_null_means_locale_default(client, db_session) -> None:
    user = _login(client, db_session, date_format_pref="iso")

    client.post(
        "/settings/display",
        data={"units": "", "theme": "", "date_format": ""},
    )

    db_session.refresh(user)
    assert user.date_format_pref is None
