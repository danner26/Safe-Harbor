"""WTForms FlaskForm subclasses for the tanks blueprint."""

from __future__ import annotations

import zoneinfo
from datetime import UTC, datetime
from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import DateField, DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import (
    AnyOf,
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from safeharbor.models import TANK_PROFILES
from safeharbor.models.tank import profiles_for_water_type

_TANK_PROFILE_CHOICES = [
    ("tropical_fw_community", "Tropical Freshwater Community"),
    ("coldwater_fw", "Coldwater Freshwater (Goldfish)"),
    ("planted_fw", "Planted Freshwater"),
    ("reef_sw", "Reef Saltwater"),
    ("fowlr_sw", "Fish-Only Saltwater (FOWLR)"),
    ("brackish", "Brackish"),
]
_TANK_PROFILE_LABELS = dict(_TANK_PROFILE_CHOICES)


def profile_choices_for_water_type(water_type: str) -> list[tuple[str, str]]:
    """Return profile SelectField choices for a water type."""
    return [
        (profile_key, _TANK_PROFILE_LABELS[profile_key])
        for profile_key in profiles_for_water_type(water_type)
    ]


def _setup_date_not_in_future(_form: FlaskForm, field: DateField) -> None:
    if field.data and field.data > datetime.now(UTC).date():
        raise ValidationError("Setup date can't be in the future.")


class TankForm(FlaskForm):  # type: ignore[misc]
    name = StringField("Name", validators=[DataRequired(), Length(max=128)])
    water_type = SelectField(
        "Water type",
        choices=[
            ("fresh", "Freshwater"),
            ("salt", "Saltwater"),
            ("brackish", "Brackish"),
        ],
        validators=[DataRequired()],
    )
    profile_key = SelectField(
        "Tank profile",
        choices=_TANK_PROFILE_CHOICES,
        validate_choice=False,
        validators=[InputRequired(), AnyOf(TANK_PROFILES)],
    )
    volume = DecimalField(
        "Volume",
        places=2,
        validators=[Optional(), NumberRange(min=Decimal("0.01"))],
    )
    volume_unit = SelectField(
        "Unit",
        choices=[("L", "Liters"), ("gal", "Gallons")],
        validators=[DataRequired()],
    )
    setup_date = DateField(
        "Setup date",
        validators=[Optional(), _setup_date_not_in_future],
    )
    substrate = StringField("Substrate", validators=[Optional(), Length(max=256)])
    equipment_notes = TextAreaField(
        "Equipment notes",
        validators=[Optional(), Length(max=4096)],
    )
    timezone = SelectField(
        "Timezone",
        choices=[(tz, tz) for tz in sorted(zoneinfo.available_timezones())],
        validators=[
            InputRequired(),
            AnyOf(sorted(zoneinfo.available_timezones())),
        ],
    )
    submit = SubmitField("Save")

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        water_type = self.water_type.data or "fresh"
        self.profile_key.choices = profile_choices_for_water_type(water_type)

    def validate_profile_key(self, field: SelectField) -> None:
        """Reject tank profiles that do not belong to the selected water type."""
        water_type = self.water_type.data
        if water_type not in {choice[0] for choice in self.water_type.choices}:
            return
        if field.data not in profiles_for_water_type(water_type):
            raise ValidationError(
                f"Profile {field.data!r} is not valid for {self.water_type.data!r} tanks."
            )


class TankImageForm(FlaskForm):  # type: ignore[misc]
    image = FileField(
        "Photo",
        validators=[
            FileRequired(),
            FileAllowed(["jpg", "jpeg", "png", "webp", "heic"]),
        ],
    )
    submit = SubmitField("Upload photo")
