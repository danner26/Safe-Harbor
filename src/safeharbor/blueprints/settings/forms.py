"""WTForms FlaskForm subclasses for the settings blueprint."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, RadioField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class AccountEmailForm(FlaskForm):  # type: ignore[misc]
    new_email = StringField("New email", validators=[DataRequired(), Email(), Length(max=254)])
    current_password = PasswordField("Current password", validators=[DataRequired()])
    submit = SubmitField("Send verification")


class AccountPasswordForm(FlaskForm):  # type: ignore[misc]
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=12, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match")],
    )
    submit = SubmitField("Update password")


class AccountDisplayNameForm(FlaskForm):  # type: ignore[misc]
    username = StringField("Display name", validators=[DataRequired(), Length(max=64)])
    submit = SubmitField("Save display name")


class DisplayPreferencesForm(FlaskForm):  # type: ignore[misc]
    theme = RadioField(
        "Theme",
        choices=[
            ("", "System default"),
            ("light", "Light"),
            ("dark", "Dark"),
        ],
        default="",
    )
    date_format = SelectField(
        "Date format",
        choices=[
            ("", "Locale default"),
            ("us", "US (MM/DD/YYYY)"),
            ("iso", "ISO (YYYY-MM-DD)"),
        ],
        default="",
    )
    submit = SubmitField("Save preferences")


class EmailVerifyToggleForm(FlaskForm):  # type: ignore[misc]
    enabled = BooleanField("Enabled")
    submit = SubmitField("Save")
