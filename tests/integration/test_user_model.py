"""User model can be created, persisted, and queried."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from safeharbor.models.account import User


def test_user_can_be_persisted(app, db_session) -> None:
    user = User(email="daniel@example.com", password_hash="argon2$placeholder")
    db_session.add(user)
    db_session.commit()
    assert isinstance(user.id, UUID)

    fetched = db_session.scalar(select(User).where(User.email == "daniel@example.com"))
    assert fetched is not None
    assert fetched.id == user.id


def test_user_email_uniqueness(app, db_session) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    db_session.add(User(email="a@x.com", password_hash="h1"))
    db_session.commit()

    db_session.add(User(email="a@x.com", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_defaults(app, db_session) -> None:
    u = User(email="b@x.com", password_hash="h")
    db_session.add(u)
    db_session.commit()
    assert u.is_active is True
    assert u.is_superuser is False
    assert u.preferred_units is None
