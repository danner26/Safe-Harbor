"""WTForms FlaskForm subclasses for the auth blueprint."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional


class LoginForm(FlaskForm):  # type: ignore[misc]
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember this device")
    submit = SubmitField("Log in")


class RegisterForm(FlaskForm):  # type: ignore[misc]
    # email is rendered read-only and pre-filled from the invite; not validated here
    username = StringField("Display name", validators=[Optional(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=10)])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    submit = SubmitField("Create account")


class ChangePasswordForm(FlaskForm):  # type: ignore[misc]
    current = PasswordField("Current password", validators=[DataRequired()])
    password = PasswordField("New password", validators=[DataRequired(), Length(min=10)])
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    submit = SubmitField("Update password")


class PasswordResetForm(FlaskForm):  # type: ignore[misc]
    password = PasswordField("New password", validators=[DataRequired(), Length(min=10)])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    submit = SubmitField("Set password")


class IssueInviteForm(FlaskForm):  # type: ignore[misc]
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Issue invite")
