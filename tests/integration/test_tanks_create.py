"""GET /tanks/new + POST /tanks — create flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser

import pytest


class _SelectedOptionParser(HTMLParser):
    def __init__(self, *, select_name: str) -> None:
        super().__init__()
        self._select_name = select_name
        self._in_select = False
        self.selected_value: str | None = None
        self.option_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "select" and attr_map.get("name") == self._select_name:
            self._in_select = True
            return
        if tag == "option" and self._in_select:
            if (value := attr_map.get("value")) is not None:
                self.option_values.append(value)
            if "selected" in attr_map:
                self.selected_value = attr_map.get("value")

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._in_select:
            self._in_select = False


def _selected_option_value(html: bytes, *, select_name: str) -> str | None:
    parser = _SelectedOptionParser(select_name=select_name)
    parser.feed(html.decode())
    return parser.selected_value


def _option_values(html: bytes, *, select_name: str) -> list[str]:
    parser = _SelectedOptionParser(select_name=select_name)
    parser.feed(html.decode())
    return parser.option_values


def _login(client, db_session, *, units_pref=None, accept_language="en-US"):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(
        email="creator@x.com",
        password_hash=hash_password("test-pw-12345"),
        preferred_units=units_pref,
    )
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    client.environ_base["HTTP_ACCEPT_LANGUAGE"] = accept_language
    return u


def test_new_form_renders(client, db_session) -> None:
    _login(client, db_session)
    resp = client.get("/tanks/new")
    assert resp.status_code == 200
    assert b'name="name"' in resp.data
    assert b'name="water_type"' in resp.data
    assert b'name="profile_key"' in resp.data
    assert b'name="volume"' in resp.data
    assert b'name="volume_unit"' in resp.data


def test_new_form_water_type_has_htmx_profile_filter_attributes(client, db_session) -> None:
    _login(client, db_session)
    resp = client.get("/tanks/new")
    assert resp.status_code == 200
    assert b'hx-get="/tanks/profile-options/"' in resp.data
    assert b'hx-target="#profile_key"' in resp.data
    assert b'hx-swap="innerHTML"' in resp.data
    assert b'hx-trigger="change"' in resp.data
    assert b'hx-include="#water_type"' in resp.data


def test_new_form_default_unit_imperial_for_us_locale(client, db_session) -> None:
    _login(client, db_session, units_pref=None, accept_language="en-US")
    resp = client.get("/tanks/new")
    # Imperial users get gallons selected by default
    assert (
        b'value="gal" selected' in resp.data
        or b'<option selected value="gal">' in resp.data
        or b'value="gal" checked' in resp.data
    )


def test_new_form_explicit_metric_pref_overrides_locale(client, db_session) -> None:
    _login(client, db_session, units_pref="metric", accept_language="en-US")
    resp = client.get("/tanks/new")
    assert b'value="L" selected' in resp.data or b'<option selected value="L">' in resp.data


def test_new_form_pre_populates_default_tz_for_no_js_clients(client, db_session) -> None:
    _login(client, db_session)
    resp = client.get("/tanks/new")
    assert resp.status_code == 200
    assert _selected_option_value(resp.data, select_name="timezone") == "UTC"


def test_new_form_default_profile_matches_water_type(client, db_session) -> None:
    from safeharbor.models.tank import profiles_for_water_type

    _login(client, db_session)
    resp = client.get("/tanks/new")
    assert resp.status_code == 200
    assert (
        _selected_option_value(resp.data, select_name="profile_key")
        == profiles_for_water_type("fresh")[0]
    )


@pytest.mark.parametrize("water_type", ["salt", "brackish"])
def test_new_form_requested_water_type_defaults_to_matching_profile(
    client,
    db_session,
    water_type: str,
) -> None:
    from safeharbor.models.tank import profiles_for_water_type

    _login(client, db_session)
    resp = client.get(f"/tanks/new?water_type={water_type}")
    assert resp.status_code == 200
    assert _selected_option_value(resp.data, select_name="water_type") == water_type
    assert (
        _selected_option_value(resp.data, select_name="profile_key")
        == profiles_for_water_type(water_type)[0]
    )


def test_create_no_js_uses_rendered_default_timezone(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.tank import Tank

    user = _login(client, db_session)
    form_resp = client.get("/tanks/new")
    selected_timezone = _selected_option_value(form_resp.data, select_name="timezone")
    assert selected_timezone == "UTC"

    resp = client.post(
        "/tanks",
        data={
            "name": "No JS Tank",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": selected_timezone,
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    tank = db_session.scalar(select(Tank).where(Tank.name == "No JS Tank"))
    assert tank is not None
    assert tank.created_by_user_id == user.id
    assert tank.timezone == "UTC"


def test_create_minimal(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.tank import Tank

    user = _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "Reef 90",
            "water_type": "salt",
            "profile_key": "reef_sw",
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/tanks/" in resp.location
    tank = db_session.scalar(select(Tank).where(Tank.name == "Reef 90"))
    assert tank is not None
    assert tank.water_type == "salt"
    assert tank.created_by_user_id == user.id


def test_create_persists_profile_key(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.tank import Tank

    _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "Goldfish",
            "water_type": "fresh",
            "profile_key": "coldwater_fw",
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    tank = db_session.scalar(select(Tank).where(Tank.name == "Goldfish"))
    assert tank is not None
    assert tank.profile_key == "coldwater_fw"


def test_create_rejects_mismatched_water_type_and_profile(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.tank import Tank

    _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "Mismatch Tank",
            "water_type": "salt",
            "profile_key": "coldwater_fw",
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Profile &#39;coldwater_fw&#39; is not valid for &#39;salt&#39; tanks." in resp.data
    assert db_session.scalar(select(Tank).where(Tank.name == "Mismatch Tank")) is None


def test_create_invalid_post_re_renders_filtered_profile_choices(client, db_session) -> None:
    _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "",
            "water_type": "salt",
            "profile_key": "reef_sw",
            "volume": "",
            "volume_unit": "L",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert _option_values(resp.data, select_name="profile_key") == ["reef_sw", "fowlr_sw"]
    assert _selected_option_value(resp.data, select_name="profile_key") == "reef_sw"


def test_create_with_volume_in_gallons_stores_as_liters(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.tank import Tank

    _login(client, db_session)
    client.post(
        "/tanks",
        data={
            "name": "Reef 90",
            "water_type": "salt",
            "profile_key": "reef_sw",
            "volume": "90",
            "volume_unit": "gal",
            "setup_date": "",
            "substrate": "",
            "equipment_notes": "",
            "timezone": "UTC",
        },
    )
    tank = db_session.scalar(select(Tank).where(Tank.name == "Reef 90"))
    assert tank is not None
    # 90 gal x 3.785411784 = 340.6870605... -> quantized to 340.69
    assert tank.volume_liters == Decimal("340.69")


def test_create_rejects_missing_name(client, db_session) -> None:
    _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume_unit": "L",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 200  # form re-rendered
    assert b'value="" required' in resp.data or b"This field is required" in resp.data


def test_create_rejects_future_setup_date(client, db_session) -> None:
    _login(client, db_session)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    resp = client.post(
        "/tanks",
        data={
            "name": "Future Tank",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume_unit": "L",
            "setup_date": tomorrow,
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 200
    assert b"future" in resp.data.lower()


def test_create_rejects_negative_volume(client, db_session) -> None:
    _login(client, db_session)
    resp = client.post(
        "/tanks",
        data={
            "name": "Bad",
            "water_type": "fresh",
            "profile_key": "tropical_fw_community",
            "volume": "-5",
            "volume_unit": "L",
            "timezone": "UTC",
        },
    )
    assert resp.status_code == 200
    assert b"Number must be at least" in resp.data or b"must be" in resp.data.lower()
