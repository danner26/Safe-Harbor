"""Safe Harbor CLI command coverage."""

from __future__ import annotations

from sqlalchemy import select

from safeharbor.models.account import User


def _run_create_admin(app, *, unit_input: str) -> object:
    runner = app.test_cli_runner()
    return runner.invoke(
        args=["safeharbor", "create-admin"],
        input=f"admin@x.com\nsupersecure-pw\nsupersecure-pw\n{unit_input}\n",
    )


def _created_admin(db_session) -> User:
    user = db_session.scalar(select(User).where(User.email == "admin@x.com"))
    assert user is not None
    return user


def test_create_admin_accepts_imperial(app, db_session) -> None:
    result = _run_create_admin(app, unit_input="imperial")

    assert result.exit_code == 0
    assert _created_admin(db_session).preferred_units == "imperial"


def test_create_admin_accepts_metric(app, db_session) -> None:
    result = _run_create_admin(app, unit_input="metric")

    assert result.exit_code == 0
    assert _created_admin(db_session).preferred_units == "metric"


def test_create_admin_defaults_units_to_imperial(app, db_session) -> None:
    result = _run_create_admin(app, unit_input="")

    assert result.exit_code == 0
    assert _created_admin(db_session).preferred_units == "imperial"


def test_create_admin_rejects_invalid_units(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["safeharbor", "create-admin"],
        input="admin@x.com\nsupersecure-pw\nsupersecure-pw\nkelvin\nimperial\n",
    )

    assert result.exit_code == 0
    assert "not one of" in result.output.lower()
    assert _created_admin(db_session).preferred_units == "imperial"
