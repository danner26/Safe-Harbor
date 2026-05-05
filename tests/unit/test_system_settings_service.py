"""System settings service tests."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from safeharbor.extensions import db
from safeharbor.models import SystemSetting, User
from safeharbor.services import system_settings_service


def test_get_helpers_return_defaults_when_missing(app, db_session) -> None:
    assert system_settings_service.get_str("aquarium_name", "Safe Harbor") == "Safe Harbor"
    assert system_settings_service.get_bool("allow_invites", False) is False


def test_get_str_returns_stored_string(app, db_session) -> None:
    db_session.add(SystemSetting(key="aquarium_name", value="Reef Lab"))
    db_session.commit()

    assert system_settings_service.get_str("aquarium_name", "Safe Harbor") == "Reef Lab"


def test_get_bool_returns_bool_always(app, db_session) -> None:
    db_session.add_all(
        [
            SystemSetting(key="allow_invites", value="true"),
            SystemSetting(key="maintenance_mode", value="false"),
        ]
    )
    db_session.commit()

    assert system_settings_service.get_bool("allow_invites", False) is True
    assert system_settings_service.get_bool("maintenance_mode", True) is False
    assert isinstance(system_settings_service.get_bool("allow_invites", False), bool)
    assert isinstance(system_settings_service.get_bool("maintenance_mode", True), bool)


def test_get_bool_raises_on_unrecognized_value(app, db_session) -> None:
    db_session.add(SystemSetting(key="allow_invites", value="TRUE"))
    db_session.commit()

    try:
        system_settings_service.get_bool("allow_invites", False)
    except ValueError as exc:
        assert "allow_invites" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-lowercase bool setting")


def test_set_value_inserts_and_updates_setting(app, db_session) -> None:
    first_user_id = UUID("018f1111-1111-7111-8111-111111111111")
    second_user_id = UUID("018f2222-2222-7222-8222-222222222222")
    db_session.add_all(
        [
            User(
                id=first_user_id,
                email="first-admin@example.com",
                password_hash="not-used-in-service-test",
            ),
            User(
                id=second_user_id,
                email="second-admin@example.com",
                password_hash="not-used-in-service-test",
            ),
        ]
    )
    db_session.commit()

    system_settings_service.set_value(
        key="aquarium_name",
        value="Reef Lab",
        updated_by_user_id=first_user_id,
    )
    inserted = db_session.scalar(select(SystemSetting).where(SystemSetting.key == "aquarium_name"))

    assert inserted is not None
    assert inserted.value == "Reef Lab"
    assert inserted.updated_by_user_id == first_user_id

    system_settings_service.set_value(
        key="aquarium_name",
        value="Frag Room",
        updated_by_user_id=second_user_id,
    )
    updated = db_session.scalars(select(SystemSetting).where(SystemSetting.key == "aquarium_name"))

    rows = updated.all()
    assert len(rows) == 1
    assert rows[0].value == "Frag Room"
    assert rows[0].updated_by_user_id == second_user_id


def test_set_value_does_not_commit(app, db_session, monkeypatch) -> None:
    def fail_commit() -> None:
        raise AssertionError("system_settings_service.set_value must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    system_settings_service.set_value(
        key="allow_invites",
        value="true",
        updated_by_user_id=None,
    )

    fetched = db_session.scalar(select(SystemSetting).where(SystemSetting.key == "allow_invites"))
    assert fetched is not None
    assert fetched.value == "true"
