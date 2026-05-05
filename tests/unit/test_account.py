"""Account model helpers."""

from __future__ import annotations

from safeharbor.models.account import User


def test_display_username_returns_username_when_set() -> None:
    user = User(email="keeper@example.com", username="Reef Keeper", password_hash="h")

    assert user.display_username() == "Reef Keeper"


def test_display_username_falls_back_to_email_prefix() -> None:
    user = User(email="keeper@example.com", username=None, password_hash="h")

    assert user.display_username() == "keeper"


def test_display_username_never_returns_empty() -> None:
    user = User(email="@example.com", username="", password_hash="h")

    assert user.display_username() == "user"
