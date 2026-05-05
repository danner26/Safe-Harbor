"""WTForms FlaskForm subclasses for the animals blueprint."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    DateTimeLocalField,
    IntegerField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from safeharbor.services import tank_service


def _default_datetime() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)


def _active_tank_choices() -> list[tuple[str, str]]:
    return [(str(tank.id), tank.name) for tank in tank_service.active_tanks()]


class AnimalForm(FlaskForm):  # type: ignore[misc]
    """Animal add/edit form. Add-only fields are hidden by later templates."""

    name = StringField("Name", validators=[Optional(), Length(max=64)])
    species = StringField("Species", validators=[DataRequired(), Length(max=64)])
    scientific_name = StringField("Scientific name", validators=[Optional(), Length(max=96)])
    sex = SelectField(
        "Sex",
        choices=[
            ("", "Unknown / not specified"),
            ("male", "Male"),
            ("female", "Female"),
            ("unknown", "Unknown"),
        ],
        validators=[Optional()],
    )
    acquired_quantity = IntegerField(
        "Acquired quantity",
        validators=[DataRequired(), NumberRange(min=1)],
    )
    tank_id = SelectField("Tank", coerce=UUID, validators=[DataRequired()])
    acquired_at = DateTimeLocalField(
        "Acquired at",
        format="%Y-%m-%dT%H:%M",
        default=_default_datetime,
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=512)])
    initial_note = StringField("Initial note", validators=[Optional(), Length(max=512)])
    submit = SubmitField("Save")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.tank_id.choices = _active_tank_choices()


class AnimalEditForm(FlaskForm):  # type: ignore[misc]
    """Animal edit form for descriptive fields only."""

    name = StringField("Name", validators=[Optional(), Length(max=64)])
    species = StringField("Species", validators=[DataRequired(), Length(max=64)])
    scientific_name = StringField("Scientific name", validators=[Optional(), Length(max=96)])
    sex = SelectField(
        "Sex",
        choices=[
            ("", "Unknown / not specified"),
            ("male", "Male"),
            ("female", "Female"),
            ("unknown", "Unknown"),
        ],
        validators=[Optional()],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=512)])
    submit = SubmitField("Save")

    def __init__(
        self,
        *args: object,
        forbidden_field_names: set[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._forbidden_field_names = forbidden_field_names or set()

    def validate(self, extra_validators: Any | None = None) -> bool:
        is_valid = cast(bool, super().validate(extra_validators))
        if self._forbidden_field_names:
            message = "Acquisition fields cannot be changed here."
            if message not in self.form_errors:
                self.form_errors.append(message)
            return False
        return is_valid


class AnimalImageForm(FlaskForm):  # type: ignore[misc]
    """Animal private photo upload form."""

    image = FileField(
        "Photo",
        validators=[
            FileRequired(),
            FileAllowed(["jpg", "jpeg", "png", "webp", "heic"]),
        ],
    )
    submit = SubmitField("Upload photo")


class MoveAnimalForm(FlaskForm):  # type: ignore[misc]
    """Animal move form."""

    to_tank_id = SelectField(
        "To tank",
        coerce=UUID,
        validators=[DataRequired()],
    )
    # Choice validation rejects forged IDs outside the active-tank choices.
    occurred_at = DateTimeLocalField(
        "Occurred at",
        format="%Y-%m-%dT%H:%M",
        default=_default_datetime,
        validators=[DataRequired()],
    )
    note = StringField("Note", validators=[Optional(), Length(max=512)])
    submit = SubmitField("Move")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.to_tank_id.choices = _active_tank_choices()


class DeceasedForm(FlaskForm):  # type: ignore[misc]
    """Animal deceased-count form."""

    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    occurred_at = DateTimeLocalField(
        "Occurred at",
        format="%Y-%m-%dT%H:%M",
        default=_default_datetime,
        validators=[DataRequired()],
    )
    note = TextAreaField("Note", validators=[Optional(), Length(max=512)])
    submit = SubmitField("Mark deceased")


class EventNoteForm(FlaskForm):  # type: ignore[misc]
    """Generic animal timeline event form."""

    event_type = RadioField(
        "Event type",
        choices=[
            ("health_note", "Health note"),
            ("observation", "Observation"),
        ],
        default="health_note",
        validators=[DataRequired()],
    )
    occurred_at = DateTimeLocalField(
        "Occurred at",
        format="%Y-%m-%dT%H:%M",
        default=_default_datetime,
        validators=[DataRequired()],
    )
    note = TextAreaField("Note", validators=[DataRequired(), Length(min=1, max=512)])
    submit = SubmitField("Add to timeline")
