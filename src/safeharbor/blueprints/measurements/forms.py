"""WTForms FlaskForm subclasses for the measurements blueprint."""

from __future__ import annotations

from decimal import Decimal

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import (
    DateTimeLocalField,
    DecimalField,
    HiddenField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from safeharbor.extensions import db
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.utils.units import compatible_units


class BatchUnitSelectField(SelectField):  # type: ignore[misc]
    """Batch unit field with the existing invalid-unit error text."""

    def pre_validate(self, form: FlaskForm) -> None:
        try:
            super().pre_validate(form)
        except ValidationError as exc:
            raise ValidationError("incompatible unit") from exc


class QuickAddForm(FlaskForm):  # type: ignore[misc]
    """Tank + parameter + value + unit + datetime. Choices populated per-request."""

    tank_id = SelectField("Tank", validators=[DataRequired()])
    parameter_key = SelectField("Parameter", validators=[DataRequired()])
    value = DecimalField(
        "Value",
        places=4,
        validators=[InputRequired(), NumberRange(min=Decimal("0"))],
    )
    value_unit = SelectField("Unit", validators=[DataRequired()])
    recorded_at = DateTimeLocalField(
        "Recorded at",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    note = StringField("Note", validators=[Optional(), Length(max=256)])
    submit = SubmitField("Log reading")


class MeasurementEditForm(FlaskForm):  # type: ignore[misc]
    """Edit value, unit, timestamp, and note for an existing measurement."""

    value = DecimalField(
        "Value",
        places=4,
        validators=[InputRequired(), NumberRange(min=Decimal("0"))],
    )
    value_unit = SelectField("Unit", validators=[DataRequired()])
    recorded_at = DateTimeLocalField(
        "Recorded at",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    note = StringField("Note", validators=[Optional(), Length(max=256)])
    submit = SubmitField("Save reading")


class BatchEntryFormBase(FlaskForm):  # type: ignore[misc]
    """Base for per-tank dynamic batch entry forms."""

    tank_id = HiddenField(validators=[DataRequired()])
    recorded_at = DateTimeLocalField(
        "Recorded at",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    note = StringField("Note", validators=[Optional(), Length(max=256)])
    submit = SubmitField("Log readings")


def parameter_types_for(tank: Tank) -> list[ParameterType]:
    """Return parameter types applicable to this tank water type, in display order."""
    parameter_types = db.session.scalars(
        select(ParameterType).order_by(ParameterType.display_order)
    ).all()
    applicable = [
        parameter_type
        for parameter_type in parameter_types
        if parameter_type.applies_to_water_type is None
        or parameter_type.applies_to_water_type == tank.water_type
    ]
    if tank.water_type == "fresh":
        applicable = [
            parameter_type for parameter_type in applicable if parameter_type.key != "salinity"
        ]
    elif tank.water_type == "salt":
        applicable = [parameter_type for parameter_type in applicable if parameter_type.key != "gh"]
    return list(applicable)


def build_batch_form_class(
    tank: Tank,
    *,
    default_temp_unit: str | None = None,
) -> type[BatchEntryFormBase]:
    """Build a per-tank form class with one value/unit pair per parameter."""
    attrs: dict[str, object] = {}
    for parameter_type in parameter_types_for(tank):
        attrs[f"{parameter_type.key}_value"] = DecimalField(
            parameter_type.display_name,
            places=4,
            validators=[Optional(), NumberRange(min=Decimal("0"))],
        )
        units = compatible_units(parameter_type.key, tank.water_type)
        default_unit = (
            default_temp_unit
            if parameter_type.key == "temperature" and default_temp_unit in units
            else units[0]
            if units
            else None
        )
        attrs[f"{parameter_type.key}_unit"] = BatchUnitSelectField(
            f"{parameter_type.display_name} unit",
            choices=[(unit, unit) for unit in units],
            default=default_unit,
            validators=[Optional()],
        )
    return type("BatchEntryForm", (BatchEntryFormBase,), attrs)
