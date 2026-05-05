"""Dashboard / — wire tank cards to real Tank rows + empty state."""

from __future__ import annotations

from datetime import date


def _login(client, db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email="d@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def _seed_tank(db_session, **kwargs):
    from safeharbor.models.tank import Tank

    t = Tank(name=kwargs.pop("name"), water_type=kwargs.pop("water_type", "fresh"), **kwargs)
    db_session.add(t)
    db_session.commit()
    return t


def test_dashboard_empty_state_when_zero_tanks(client, db_session) -> None:
    _login(client, db_session)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Add your first tank" in resp.data


def test_dashboard_renders_real_tanks(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Reef 90", water_type="salt")
    _seed_tank(db_session, name="Planted 40", water_type="fresh")
    resp = client.get("/")
    assert b"Reef 90" in resp.data
    assert b"Planted 40" in resp.data


def test_dashboard_excludes_decommissioned(client, db_session) -> None:
    _login(client, db_session)
    _seed_tank(db_session, name="Active 1")
    _seed_tank(
        db_session,
        name="Old Tank",
        decommission_date=date(2024, 1, 1),
    )
    resp = client.get("/")
    assert b"Active 1" in resp.data
    assert b"Old Tank" not in resp.data


def test_dashboard_limits_to_six_tanks(client, db_session) -> None:
    _login(client, db_session)
    for i in range(8):
        _seed_tank(db_session, name=f"Tank {i:02d}")
    resp = client.get("/")
    # Tank 7 (newest, 8th) should appear; Tank 1 (oldest of the limit-trimmed set) should not
    assert b"Tank 07" in resp.data
    assert b"Tank 01" not in resp.data
