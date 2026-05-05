"""Invite model — defaults, kind enum, basic field shapes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from safeharbor.models.account import User
from safeharbor.models.invite import Invite, InviteKind


def test_invite_kinds_are_invite_and_password_reset() -> None:
    assert InviteKind.INVITE.value == "invite"
    assert InviteKind.PASSWORD_RESET.value == "password_reset"


def test_invite_can_be_persisted(app, db_session) -> None:
    issuer = User(email="admin@example.com", password_hash="argon2$placeholder", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    expires = datetime.now(UTC) + timedelta(days=7)
    inv = Invite(
        email="newcomer@example.com",
        token_hash="sha256-hash-placeholder",
        kind=InviteKind.INVITE.value,
        issued_by=issuer.id,
        expires_at=expires,
    )
    db_session.add(inv)
    db_session.commit()
    assert isinstance(inv.id, UUID)
    assert inv.consumed_at is None
    assert inv.consumed_by is None

    fetched = db_session.scalar(select(Invite).where(Invite.id == inv.id))
    assert fetched is not None
    assert fetched.kind == "invite"


def test_invite_token_hash_is_unique(app, db_session) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    issuer = User(email="admin2@example.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    expires = datetime.now(UTC) + timedelta(days=7)
    db_session.add(
        Invite(
            email="a@x.com",
            token_hash="duplicate-hash",
            kind="invite",
            issued_by=issuer.id,
            expires_at=expires,
        )
    )
    db_session.commit()

    db_session.add(
        Invite(
            email="b@x.com",
            token_hash="duplicate-hash",
            kind="invite",
            issued_by=issuer.id,
            expires_at=expires,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_invite_kind_check_constraint(app, db_session) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    issuer = User(email="admin3@example.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    bogus = Invite(
        email="c@x.com",
        token_hash="hash-c",
        kind="bogus_kind",
        issued_by=issuer.id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()
