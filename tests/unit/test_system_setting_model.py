"""SystemSetting model — singleton-ish keyed settings table."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from safeharbor.models import SystemSetting, User


def test_system_setting_can_be_persisted_with_required_fields(app, db_session) -> None:
    setting = SystemSetting(key="aquarium_name", value="Safe Harbor")

    db_session.add(setting)
    db_session.commit()

    fetched = db_session.scalar(select(SystemSetting).where(SystemSetting.key == "aquarium_name"))
    assert fetched is not None
    assert fetched.key == "aquarium_name"
    assert fetched.value == "Safe Harbor"
    assert fetched.updated_at is not None
    assert fetched.updated_by_user_id is None


def test_system_setting_column_shape(app, db_session) -> None:
    inspector = inspect(db_session.bind)
    columns = {column["name"]: column for column in inspector.get_columns("system_settings")}
    pk = inspector.get_pk_constraint("system_settings")
    foreign_keys = inspector.get_foreign_keys("system_settings")

    assert pk["constrained_columns"] == ["key"]
    assert columns["key"]["type"].length == 64
    assert columns["value"]["type"].length == 256
    assert columns["value"]["nullable"] is False
    assert columns["updated_at"]["nullable"] is False
    assert columns["updated_by_user_id"]["nullable"] is True
    assert any(
        fk["constrained_columns"] == ["updated_by_user_id"]
        and fk["referred_table"] == "users"
        and fk["referred_columns"] == ["id"]
        for fk in foreign_keys
    )


def test_system_setting_accepts_updated_by_user_id(app, db_session) -> None:
    user_id = UUID("018f1111-1111-7111-8111-111111111111")
    db_session.add(
        User(id=user_id, email="admin@example.com", password_hash="not-used-in-model-test")
    )
    db_session.commit()
    setting = SystemSetting(key="theme", value="dark", updated_by_user_id=user_id)

    db_session.add(setting)
    db_session.commit()

    fetched = db_session.scalar(select(SystemSetting).where(SystemSetting.key == "theme"))
    assert fetched is not None
    assert fetched.updated_by_user_id == user_id
