"""GET /tanks — list view (active + decommissioned filters; cards + table)."""

from __future__ import annotations

from datetime import date


def _login(client, db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email="lister@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def _seed_tank(
    db_session,
    *,
    name: str,
    water_type: str = "fresh",
    decommission_date=None,
):
    from safeharbor.models.tank import Tank

    t = Tank(name=name, water_type=water_type, decommission_date=decommission_date)
    db_session.add(t)
    db_session.commit()
    return t


def test_tanks_list_requires_login(client, configured_user) -> None:
    resp = client.get("/tanks", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_tanks_list_empty_state(client, db_session) -> None:
    _login(client, db_session)
    resp = client.get("/tanks")
    assert resp.status_code == 200
    assert b"No tanks yet" in resp.data
    assert b"Add your first tank" in resp.data or b"Add tank" in resp.data


def test_tanks_list_renders_active_tanks(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Reef 90", water_type="salt")
    _seed_tank(db_session, name="Planted 40", water_type="fresh")
    resp = client.get("/tanks")
    assert resp.status_code == 200
    assert b"Reef 90" in resp.data
    assert b"Planted 40" in resp.data


def test_tanks_list_excludes_decommissioned_by_default(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Active 1")
    _seed_tank(
        db_session,
        name="Old Tank",
        decommission_date=date(2024, 1, 1),
    )
    resp = client.get("/tanks")
    assert b"Active 1" in resp.data
    assert b"Old Tank" not in resp.data


def test_tanks_list_decommissioned_filter(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Active 1")
    _seed_tank(db_session, name="Old Tank", decommission_date=date(2024, 1, 1))
    resp = client.get("/tanks?status=decommissioned")
    assert b"Old Tank" in resp.data
    assert b"Active 1" not in resp.data


def test_tanks_list_table_view_query_param(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Reef 90", water_type="salt")
    resp = client.get("/tanks?view=table")
    assert resp.status_code == 200
    assert b"<table" in resp.data
    assert b"Reef 90" in resp.data
