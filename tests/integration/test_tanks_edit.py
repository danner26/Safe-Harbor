"""GET /tanks/<id>/edit + POST /tanks/<id> — update flow."""

from __future__ import annotations

from decimal import Decimal


def _login(client, db_session, *, units_pref=None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(
        email="editor@x.com",
        password_hash=hash_password("test-pw-12345"),
        preferred_units=units_pref,
    )
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


def test_edit_form_prefilled(client, db_session) -> None:
    _login(client, db_session)
    tank = _seed(db_session, name="Original Name", water_type="fresh")
    resp = client.get(f"/tanks/{tank.id}/edit")
    assert resp.status_code == 200
    assert b"Original Name" in resp.data
    assert b'value="fresh" selected' in resp.data or b'<option selected value="fresh">' in resp.data


def test_edit_form_volume_displayed_in_user_pref_unit(client, db_session) -> None:
    _login(client, db_session, units_pref="imperial")
    # 340.69 L = 90.00 gal
    tank = _seed(db_session, name="Reef 90", volume_liters=Decimal("340.69"))
    resp = client.get(f"/tanks/{tank.id}/edit")
    # The volume input renders the gal value
    assert b'value="90.00"' in resp.data or b'value="90"' in resp.data
    assert b'value="gal" selected' in resp.data or b'<option selected value="gal">' in resp.data


def test_update_persists_changes(client, db_session) -> None:

    _login(client, db_session)
    tank = _seed(db_session, name="Before")
    client.post(
        f"/tanks/{tank.id}",
        data={
            "name": "After",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume": "60",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "sand",
            "equipment_notes": "",
            "timezone": "UTC",
        },
        follow_redirects=False,
    )
    db_session.refresh(tank)
    assert tank.name == "After"
    assert tank.volume_liters == Decimal("60.00")
    assert tank.substrate == "sand"


def test_update_404_for_unknown_id(client, db_session) -> None:
    from uuid import uuid4

    _login(client, db_session)
    resp = client.post(
        f"/tanks/{uuid4()}",
        data={
            "name": "X",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume_unit": "L",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 404
