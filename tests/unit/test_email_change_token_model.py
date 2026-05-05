"""EmailChangeToken model - pending single-use email update tokens."""

from __future__ import annotations

from sqlalchemy import CheckConstraint

from safeharbor.models import EmailChangeToken


def test_email_change_token_declares_expected_table_name() -> None:
    assert EmailChangeToken.__tablename__ == "email_change_tokens"


def test_email_change_token_column_shape() -> None:
    columns = EmailChangeToken.__table__.c
    user_id_foreign_keys = list(columns.user_id.foreign_keys)
    check_constraints = [
        constraint
        for constraint in EmailChangeToken.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert columns.id.primary_key is True
    assert columns.token.type.length == 64
    assert columns.token.unique is True
    assert columns.token.nullable is False
    assert columns.user_id.nullable is False
    assert columns.new_email.type.length == 254
    assert columns.new_email.nullable is False
    assert columns.expires_at.nullable is False
    assert columns.used_at.nullable is True
    assert columns.created_at.nullable is False
    assert columns.created_at.server_default is not None
    assert len(user_id_foreign_keys) == 1
    assert user_id_foreign_keys[0].target_fullname == "users.id"
    assert user_id_foreign_keys[0].ondelete == "CASCADE"
    assert any(
        str(constraint.sqltext) == "used_at IS NULL OR used_at >= created_at"
        for constraint in check_constraints
    )


def test_email_change_token_has_pending_partial_index() -> None:
    index = next(
        idx
        for idx in EmailChangeToken.__table__.indexes
        if idx.name == "email_change_tokens_user_pending_idx"
    )

    assert [column.name for column in index.columns] == ["user_id", "used_at"]
    assert str(index.dialect_options["postgresql"]["where"]) == "used_at IS NULL"
