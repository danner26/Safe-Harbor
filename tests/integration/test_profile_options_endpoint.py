"""GET /tanks/profile-options/<water_type> HTMX fragment."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _OptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.options: list[tuple[str | None, str, bool]] = []
        self._current_value: str | None = None
        self._current_selected = False
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "option":
            return
        attr_map = dict(attrs)
        self._current_value = attr_map.get("value")
        self._current_selected = "selected" in attr_map
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_value is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "option" or self._current_value is None:
            return
        self.options.append(
            (
                self._current_value,
                "".join(self._current_text).strip(),
                self._current_selected,
            )
        )
        self._current_value = None
        self._current_selected = False
        self._current_text = []


def _login(client: Any, db_session: Any) -> None:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="profile-options@x.com",
        password_hash=hash_password("test-pw-12345"),
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _options(html: bytes) -> list[tuple[str | None, str, bool]]:
    parser = _OptionParser()
    parser.feed(html.decode())
    return parser.options


def test_profile_options_returns_filtered_profiles_per_water_type(
    client: Any, db_session: Any
) -> None:
    _login(client, db_session)

    fresh = client.get("/tanks/profile-options/fresh")
    salt = client.get("/tanks/profile-options/salt")
    brackish = client.get("/tanks/profile-options/brackish")

    assert fresh.status_code == 200
    assert [value for value, _label, _selected in _options(fresh.data)] == [
        "tropical_fw_community",
        "coldwater_fw",
        "planted_fw",
    ]
    assert salt.status_code == 200
    assert [value for value, _label, _selected in _options(salt.data)] == [
        "reef_sw",
        "fowlr_sw",
    ]
    assert brackish.status_code == 200
    assert [value for value, _label, _selected in _options(brackish.data)] == ["brackish"]


def test_profile_options_rejects_unknown_water_type(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/tanks/profile-options/marine")

    assert resp.status_code == 400


def test_profile_options_selects_first_applicable_profile(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/tanks/profile-options/salt")

    assert resp.status_code == 200
    options = _options(resp.data)
    assert options[0] == ("reef_sw", "Reef Saltwater", True)
    assert [selected for _value, _label, selected in options] == [True, False]
