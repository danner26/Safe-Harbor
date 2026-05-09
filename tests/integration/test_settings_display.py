"""Settings — Display preferences."""

from __future__ import annotations


def _login(client, db_session, *, units_pref=None, theme_pref=None, date_format_pref=None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(
        email="settings@x.com",
        password_hash=hash_password("test-pw-12345"),
        preferred_units=units_pref,
        theme_pref=theme_pref,
        date_format_pref=date_format_pref,
    )
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def test_display_requires_login(client, configured_user) -> None:
    resp = client.get("/settings/display", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_display_does_not_render_units_control(client, db_session) -> None:
    _login(client, db_session, units_pref="imperial")
    resp = client.get("/settings/display")
    assert resp.status_code == 200
    assert b'name="units"' not in resp.data
    assert b"Metric" not in resp.data
    assert b"Imperial" not in resp.data


def test_nav_includes_account_and_system(client, db_session) -> None:
    _login(client, db_session)

    resp = client.get("/settings/display")

    assert resp.status_code == 200
    assert b'href="/settings/display"' in resp.data
    assert b">Display</a>" in resp.data
    assert b'href="/settings/account"' in resp.data
    assert b">Account</a>" in resp.data
    assert b'href="/settings/system"' in resp.data
    assert b">System</a>" in resp.data
    assert b">Password</a>" not in resp.data


def test_post_does_not_change_units_pref(client, db_session) -> None:
    user = _login(client, db_session, units_pref="metric")
    client.post("/settings/display", data={"units": "imperial"})
    db_session.refresh(user)
    assert user.preferred_units == "metric"


def test_theme_only_post_preserves_existing_units_and_date_format(client, db_session) -> None:
    user = _login(
        client,
        db_session,
        units_pref="metric",
        theme_pref="dark",
        date_format_pref="iso",
    )

    client.post("/settings/display", data={"theme": "light"})

    db_session.refresh(user)
    assert user.preferred_units == "metric"
    assert user.theme_pref == "light"
    assert user.date_format_pref == "iso"


def test_post_redirects_back_to_display(client, db_session) -> None:
    _login(client, db_session)
    resp = client.post("/settings/display", data={"theme": "dark"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/settings/display" in resp.location
