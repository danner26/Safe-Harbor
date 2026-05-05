"""POST /tanks/<id>/decommission + /restore — soft-delete cycle."""

from __future__ import annotations

from datetime import UTC, date, datetime


def _login(client, db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email="decomm@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def _seed(db_session, **kwargs):
    from safeharbor.models.tank import Tank

    t = Tank(
        name=kwargs.pop("name", "Reef 90"), water_type=kwargs.pop("water_type", "salt"), **kwargs
    )
    db_session.add(t)
    db_session.commit()
    return t


def test_decommission_sets_date_and_redirects(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session)
    resp = client.post(f"/tanks/{tank.id}/decommission", follow_redirects=False)
    assert resp.status_code == 302
    assert "/tanks" in resp.location
    db_session.refresh(tank)
    assert tank.decommission_date == datetime.now(UTC).date()


def test_decommissioned_tank_disappears_from_active_list(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Bye Tank")
    client.post(f"/tanks/{tank.id}/decommission")
    resp = client.get("/tanks")
    assert b"Bye Tank" not in resp.data


def test_decommissioned_tank_appears_in_decommissioned_filter(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Bye Tank")
    client.post(f"/tanks/{tank.id}/decommission")
    resp = client.get("/tanks?status=decommissioned")
    assert b"Bye Tank" in resp.data


def test_restore_nulls_decommission_date(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session, decommission_date=date(2024, 1, 1))
    resp = client.post(f"/tanks/{tank.id}/restore", follow_redirects=False)
    assert resp.status_code == 302
    db_session.refresh(tank)
    assert tank.decommission_date is None


def test_restored_tank_reappears_in_active_list(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Welcome Back", decommission_date=date(2024, 1, 1))
    client.post(f"/tanks/{tank.id}/restore")
    resp = client.get("/tanks")
    assert b"Welcome Back" in resp.data


def test_decommission_404_for_unknown_id(client, db_session) -> None:
    from uuid import uuid4

    _login(client, db_session)
    resp = client.post(f"/tanks/{uuid4()}/decommission")
    assert resp.status_code == 404
