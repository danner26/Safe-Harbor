"""Unit tests for settings account and display forms."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from flask import Flask
from flask_wtf import FlaskForm

from safeharbor.blueprints.settings.forms import (
    AccountDisplayNameForm,
    AccountEmailForm,
    AccountPasswordForm,
    DisplayPreferencesForm,
    EmailVerifyToggleForm,
)


@pytest.fixture
def form_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture
def request_context(form_app: Flask) -> Generator[None, None, None]:
    with form_app.test_request_context("/settings/account", method="POST"):
        yield


def test_account_forms_inherit_flaskform() -> None:
    for form_class in (
        AccountEmailForm,
        AccountPasswordForm,
        AccountDisplayNameForm,
        DisplayPreferencesForm,
        EmailVerifyToggleForm,
    ):
        assert issubclass(form_class, FlaskForm)


def test_email_form_requires_current_password(request_context: None) -> None:
    form = AccountEmailForm(data={"new_email": "new@example.com", "current_password": ""})

    assert form.validate() is False
    assert "current_password" in form.errors


def test_email_form_rejects_empty_new_email(request_context: None) -> None:
    form = AccountEmailForm(
        data={"new_email": "", "current_password": "correct horse battery staple"}
    )

    assert form.validate() is False
    assert "new_email" in form.errors


def test_email_form_validates_email_length(request_context: None) -> None:
    form = AccountEmailForm(
        data={
            "new_email": f"{'a' * 250}@example.com",
            "current_password": "correct horse battery staple",
        }
    )

    assert form.validate() is False
    assert "new_email" in form.errors


def test_password_form_rejects_mismatched_confirm(request_context: None) -> None:
    form = AccountPasswordForm(
        data={
            "current_password": "old password",
            "new_password": "new password long enough",
            "confirm_password": "different password",
        }
    )

    assert form.validate() is False
    assert "confirm_password" in form.errors


def test_password_form_rejects_empty_confirm(request_context: None) -> None:
    form = AccountPasswordForm(
        data={
            "current_password": "old password",
            "new_password": "new password long enough",
            "confirm_password": "",
        }
    )

    assert form.validate() is False
    assert "confirm_password" in form.errors


def test_password_form_enforces_new_password_length(request_context: None) -> None:
    form = AccountPasswordForm(
        data={
            "current_password": "old password",
            "new_password": "short",
            "confirm_password": "short",
        }
    )

    assert form.validate() is False
    assert "new_password" in form.errors


def test_username_form_requires_name_and_caps_length(request_context: None) -> None:
    blank_form = AccountDisplayNameForm(data={"username": ""})
    long_form = AccountDisplayNameForm(data={"username": "a" * 65})

    assert blank_form.validate() is False
    assert "username" in blank_form.errors
    assert long_form.validate() is False
    assert "username" in long_form.errors


def test_display_preferences_form_removes_units_and_preserves_display_options(
    request_context: None,
) -> None:
    form = DisplayPreferencesForm()

    assert not hasattr(form, "units")
    assert form.theme.choices == [
        ("", "System default"),
        ("light", "Light"),
        ("dark", "Dark"),
    ]
    assert form.date_format.choices == [
        ("", "Locale default"),
        ("us", "US (MM/DD/YYYY)"),
        ("iso", "ISO (YYYY-MM-DD)"),
    ]


def test_display_preferences_defaults_to_auto_system_and_locale(request_context: None) -> None:
    form = DisplayPreferencesForm()

    assert form.theme.data == ""
    assert form.date_format.data == ""


def test_email_verify_toggle_accepts_boolean(request_context: None) -> None:
    form = EmailVerifyToggleForm(data={"enabled": True})

    assert form.validate() is True
    assert form.enabled.data is True
