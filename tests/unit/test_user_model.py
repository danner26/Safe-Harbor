"""User model - preferences and CHECK constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, select
from sqlalchemy.exc import IntegrityError

from safeharbor.models.account import User


def test_user_preference_column_shape() -> None:
    columns = User.__table__.c
    check_constraints = [
        constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert columns.preferred_units.nullable is True
    assert columns.theme_pref.type.length == 8
    assert columns.theme_pref.nullable is True
    assert columns.date_format_pref.type.length == 8
    assert columns.date_format_pref.nullable is True
    assert any(
        str(constraint.sqltext) == "theme_pref IS NULL OR theme_pref IN ('light', 'dark')"
        for constraint in check_constraints
    )
    assert any(
        str(constraint.sqltext) == "date_format_pref IS NULL OR date_format_pref IN ('us', 'iso')"
        for constraint in check_constraints
    )


def test_user_preference_auto_nulls_are_valid(app, db_session) -> None:
    user = User(email="auto@example.com", password_hash="h")
    db_session.add(user)
    db_session.commit()

    fetched = db_session.scalar(select(User).where(User.email == "auto@example.com"))
    assert fetched is not None
    assert fetched.preferred_units is None
    assert fetched.theme_pref is None
    assert fetched.date_format_pref is None


def test_user_theme_pref_check_constraint(app, db_session) -> None:
    user = User(email="theme@example.com", password_hash="h", theme_pref="sepia")
    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_date_format_pref_check_constraint(app, db_session) -> None:
    user = User(email="date@example.com", password_hash="h", date_format_pref="eu")
    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.commit()
