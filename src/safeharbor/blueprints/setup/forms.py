"""WTForms FlaskForm subclasses for the setup blueprint."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class SetupForm(FlaskForm):  # type: ignore[misc]
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=10)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    preferred_units = RadioField(
        "Preferred units",
        choices=[("imperial", "Imperial"), ("metric", "Metric")],
        default="imperial",
        validators=[DataRequired()],
    )
    submit = SubmitField("Create administrator")
