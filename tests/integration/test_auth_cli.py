"""Auth-related Flask CLI commands."""

from __future__ import annotations


def test_create_admin_via_flask_test_cli_runner(app, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.account import User

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "create-admin"],
        input="founder@x.com\nstrong-pw-12345\nstrong-pw-12345\nimperial\n",
    )
    assert result.exit_code == 0, result.output
    u = db_session.scalar(select(User).where(User.email == "founder@x.com"))
    assert u is not None
    assert u.is_superuser is True
    assert u.is_active is True
    # Password is hashed
    assert u.password_hash.startswith("$argon2")


def test_create_admin_refuses_when_users_exist(app, db_session) -> None:
    from safeharbor.models.account import User

    db_session.add(User(email="someone@x.com", password_hash="h"))
    db_session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "create-admin"],
        input="another@x.com\nstrong-pw-12345\nstrong-pw-12345\n",
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower() or "refusing" in result.output.lower()


def test_create_admin_validates_password_match(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "create-admin"],
        input="x@x.com\npw-1234567890\nDIFFERENT-pw-12\nimperial\n",
    )
    assert result.exit_code != 0


def test_create_admin_validates_password_length(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "create-admin"],
        input="x@x.com\nshort\nshort\nimperial\n",
    )
    assert result.exit_code != 0
    assert "10" in result.output or "characters" in result.output.lower()


def test_reset_password_updates_existing_user(app, db_session) -> None:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password, verify_password

    u = User(email="reset@x.com", password_hash=hash_password("old-12345-old"))
    db_session.add(u)
    db_session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "reset-password", "reset@x.com"],
        input="new-secret-12345\nnew-secret-12345\n",
    )
    assert result.exit_code == 0, result.output
    db_session.refresh(u)
    assert verify_password("new-secret-12345", u.password_hash) is True


def test_reset_password_rejects_unknown_email(app) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "reset-password", "ghost@x.com"],
        input="new-secret-12345\nnew-secret-12345\n",
    )
    assert result.exit_code != 0
