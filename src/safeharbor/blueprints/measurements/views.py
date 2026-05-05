"""Measurements views for quick-add, batch entry, and history."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required  # type: ignore[import-untyped, unused-ignore]
from sqlalchemy import func, select
from werkzeug.wrappers import Response

from safeharbor.blueprints.measurements import measurements_bp
from safeharbor.blueprints.measurements.forms import (
    MeasurementEditForm,
    QuickAddForm,
    build_batch_form_class,
    parameter_types_for,
)
from safeharbor.extensions import db
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import measurement_service, tank_service
from safeharbor.utils.dates import parse_recorded_at_input, tank_local_naive_now
from safeharbor.utils.htmx import is_htmx_request
from safeharbor.utils.units import (
    PARAMETER_KEYS,
    _default_temp_unit,
    compatible_units,
    from_canonical,
)


def _temperature_unit_default() -> str:
    """Return the request-local temperature default unit."""
    return _default_temp_unit(
        current_user.preferred_units,
        request.headers.get("Accept-Language"),
    )


def _default_unit_for_parameter(parameter_key: str, units: list[str]) -> str | None:
    """Return the selected unit for a parameter option list."""
    if parameter_key == "temperature":
        temp_default = _temperature_unit_default()
        if temp_default in units:
            return temp_default
    return units[0] if units else None


def _populate_quick_add_choices(
    form: QuickAddForm,
    tank: Tank | None,
    *,
    default_temp_unit: str | None = None,
) -> None:
    """Wire up tank/parameter/value_unit dropdowns for QuickAddForm."""
    active_tanks = tank_service.active_tanks()
    form.tank_id.choices = [(str(t.id), t.name) for t in active_tanks]

    if tank is None and active_tanks:
        tank = active_tanks[0]
        form.tank_id.data = str(tank.id)

    if tank is None:
        form.parameter_key.choices = []
        form.value_unit.choices = []
        return

    pts = db.session.scalars(select(ParameterType).order_by(ParameterType.display_order)).all()
    applicable = [
        pt
        for pt in pts
        if pt.applies_to_water_type is None or pt.applies_to_water_type == tank.water_type
    ]
    # Filter salinity off freshwater + GH off saltwater (the NULL-applies-to UI rule).
    if tank.water_type == "fresh":
        applicable = [pt for pt in applicable if pt.key != "salinity"]
    elif tank.water_type == "salt":
        applicable = [pt for pt in applicable if pt.key != "gh"]
    form.parameter_key.choices = [(pt.key, pt.display_name) for pt in applicable]

    selected_param = form.parameter_key.data or (applicable[0].key if applicable else None)
    if selected_param is not None:
        try:
            units = compatible_units(selected_param, tank.water_type)
        except ValueError:
            units = []
        form.value_unit.choices = [(u, u) for u in units]
        if selected_param == "temperature" and default_temp_unit in units:
            form.value_unit.data = default_temp_unit
    else:
        form.value_unit.choices = []


def _resolve_tank_from_form_or_query(form: QuickAddForm) -> Tank | None:
    raw = form.tank_id.data or request.args.get("tank")
    if not raw:
        return None
    try:
        return tank_service.get_tank_or_none_unscoped(UUID(raw))
    except (ValueError, TypeError):
        return None


def _populate_edit_unit_choices(form: MeasurementEditForm, measurement: Measurement) -> None:
    """Wire compatible unit choices for the measurement's parameter and tank."""
    parameter_type = db.session.get(ParameterType, measurement.parameter_type_id)
    tank = db.session.get(Tank, measurement.tank_id)
    if parameter_type is None or tank is None:
        form.value_unit.choices = []
        return

    units = compatible_units(parameter_type.key, tank.water_type)
    form.value_unit.choices = [(unit, unit) for unit in units]


def _edit_form_data(
    measurement: Measurement,
    tank: Tank,
    *,
    default_temp_unit: str | None = None,
) -> dict[str, object]:
    """Return initial form data, preferring the original raw unit when present."""
    parameter_type = db.session.get(ParameterType, measurement.parameter_type_id)
    value = measurement.raw_value if measurement.raw_value is not None else measurement.value
    if parameter_type is None:
        value_unit = ""
    elif measurement.raw_unit_id is not None:
        raw_unit = db.session.get(Unit, measurement.raw_unit_id)
        value_unit = raw_unit.code if raw_unit is not None else ""
    elif parameter_type.key == "temperature" and default_temp_unit is not None:
        value_unit = default_temp_unit
        value = from_canonical(measurement.value, value_unit, parameter_type.key)
    else:
        canonical_unit = db.session.get(Unit, parameter_type.canonical_unit_id)
        value_unit = canonical_unit.code if canonical_unit is not None else ""

    recorded_at = measurement.recorded_at
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)

    return {
        "value": value,
        "value_unit": value_unit,
        "recorded_at": recorded_at.astimezone(ZoneInfo(str(tank.timezone))).replace(tzinfo=None),
        "note": measurement.note,
    }


def _quick_add_invalid_response(
    form: QuickAddForm,
    tank: Tank | None,
) -> tuple[str, int] | tuple[str, int, dict[str, str]]:
    if is_htmx_request():
        response = render_template(
            "measurements/_quick_add_form.html",
            form=form,
            selected_tank=tank,
        )
        return response, 200, {"Hx-Retarget": "#quick-add-form", "Hx-Reswap": "outerHTML"}
    response = render_template(
        "measurements/quick_add.html",
        form=form,
        just_logged=False,
        selected_tank=tank,
    )
    return response, 200


def _latest_measurements_by_tank(tanks: list[Tank]) -> dict[UUID, list[Measurement]]:
    """Return up to three latest per-parameter readings for each tank."""
    tank_ids = [tank.id for tank in tanks]
    if not tank_ids:
        return {}

    ranked_measurement_ids = (
        select(
            Measurement.id.label("measurement_id"),
            func.row_number()
            .over(
                partition_by=(Measurement.tank_id, Measurement.parameter_type_id),
                order_by=(Measurement.recorded_at.desc(), Measurement.id.desc()),
            )
            .label("row_number"),
        )
        .where(Measurement.tank_id.in_(tank_ids))
        .subquery()
    )
    latest_measurements = db.session.scalars(
        select(Measurement)
        .join(ranked_measurement_ids, ranked_measurement_ids.c.measurement_id == Measurement.id)
        .where(ranked_measurement_ids.c.row_number == 1)
        .order_by(Measurement.tank_id, Measurement.recorded_at.desc())
    ).all()

    latest_by_tank_id: dict[UUID, list[Measurement]] = {tank_id: [] for tank_id in tank_ids}
    for measurement in latest_measurements:
        tank_measurements = latest_by_tank_id[measurement.tank_id]
        if len(tank_measurements) < 3:
            tank_measurements.append(measurement)
    return latest_by_tank_id


@measurements_bp.route("/measurements", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def index() -> Response | str:
    """Measurements landing — pick a tank to log against."""
    tanks = tank_service.active_tanks()
    pt_display, pt_unit = measurement_service.parameter_display_maps()
    unit_display_by_id = {unit.id: unit.display for unit in db.session.scalars(select(Unit)).all()}
    context = {
        "tanks": tanks,
        "latest_by_tank_id": _latest_measurements_by_tank(tanks),
        "pt_display": pt_display,
        "pt_unit": pt_unit,
        "unit_display_by_id": unit_display_by_id,
    }
    return render_template("measurements/index.html", **context)


@measurements_bp.route("/measurements/<uuid:measurement_id>/edit", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def edit_get(measurement_id: UUID) -> str:
    """Render a pre-populated edit form for an existing measurement."""
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        abort(404)
    tank = db.session.get(Tank, measurement.tank_id)
    if tank is None:
        abort(404)

    form = MeasurementEditForm(
        data=_edit_form_data(
            measurement,
            tank,
            default_temp_unit=_temperature_unit_default(),
        )
    )
    _populate_edit_unit_choices(form, measurement)
    return render_template("measurements/edit.html", form=form, measurement=measurement)


@measurements_bp.route("/measurements/units-for-parameter/", defaults={"parameter_key": ""})
@measurements_bp.route("/measurements/units-for-parameter/<parameter_key>")
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def units_for_parameter(parameter_key: str) -> str:
    """Return unit <option> tags for the selected measurement parameter."""
    parameter_key = parameter_key or request.args.get("parameter_key", "")
    if parameter_key not in PARAMETER_KEYS:
        abort(400)

    units = compatible_units(parameter_key)
    return render_template(
        "measurements/_unit_options.html",
        units=units,
        selected_unit=_default_unit_for_parameter(parameter_key, units),
    )


@measurements_bp.route("/measurements/<uuid:measurement_id>/edit", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def edit_post(measurement_id: UUID) -> Response | str | tuple[str, int]:
    """Validate and persist edits to an existing measurement."""
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        abort(404)

    form = MeasurementEditForm()
    _populate_edit_unit_choices(form, measurement)
    if not form.validate_on_submit():
        return render_template("measurements/edit.html", form=form, measurement=measurement), 200

    tank = db.session.get(Tank, measurement.tank_id)
    if tank is None:
        abort(404)
    recorded_at = parse_recorded_at_input(form.recorded_at.data.isoformat(), tank)

    try:
        measurement_service.edit_measurement(
            measurement,
            value=form.value.data,
            value_unit=form.value_unit.data,
            recorded_at=recorded_at,
            note=form.note.data,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return render_template("measurements/edit.html", form=form, measurement=measurement), 200

    flash("Saved reading.", "success")
    return redirect(url_for("tanks.history", tank_id=measurement.tank_id))


@measurements_bp.route("/measurements/<uuid:measurement_id>/delete", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def delete_post(measurement_id: UUID) -> Response | tuple[str, int]:
    """Delete an existing measurement with full-page and HTMX responses."""
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        abort(404)

    tank_id = measurement.tank_id
    measurement_service.delete_measurement(measurement)
    db.session.commit()

    if is_htmx_request():
        return "", 200

    flash("Reading deleted.", "success")
    return redirect(url_for("tanks.history", tank_id=tank_id))


@measurements_bp.route("/measurements/quick-add", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def quick_add_get() -> str:
    """Render quick-add. Query params: ?tank=<uuid>, ?parameter=<key>, ?logged=1."""
    form = QuickAddForm()
    if request.args.get("tank"):
        form.tank_id.data = request.args["tank"]
    if request.args.get("parameter"):
        form.parameter_key.data = request.args["parameter"]
    tank = _resolve_tank_from_form_or_query(form)
    _populate_quick_add_choices(form, tank, default_temp_unit=_temperature_unit_default())
    if tank is None:
        tank = _resolve_tank_from_form_or_query(form)
    if not form.recorded_at.data:
        form.recorded_at.data = tank_local_naive_now(tank)
    just_logged = request.args.get("logged") == "1"
    return render_template(
        "measurements/quick_add.html",
        form=form,
        just_logged=just_logged,
        selected_tank=tank,
    )


@measurements_bp.route("/measurements/quick-add", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def quick_add_post() -> Response | str | tuple[str, int] | tuple[str, int, dict[str, str]]:
    """Validate, convert to canonical, persist, redirect with ?logged=1."""
    form = QuickAddForm()
    tank = _resolve_tank_from_form_or_query(form)
    _populate_quick_add_choices(form, tank)

    if not form.validate_on_submit() or tank is None:
        return _quick_add_invalid_response(form, tank)

    pt = db.session.scalar(
        select(ParameterType).where(ParameterType.key == form.parameter_key.data)
    )
    if pt is None:
        form.parameter_key.errors = [*form.parameter_key.errors, "unknown parameter"]
        return _quick_add_invalid_response(form, tank)

    try:
        recorded_at = parse_recorded_at_input(form.recorded_at.data.isoformat(), tank)
        measurement = measurement_service.record_measurement(
            tank=tank,
            parameter_type=pt,
            value=form.value.data,
            value_unit=form.value_unit.data,
            recorded_at=recorded_at,
            source="manual",
            recorded_by_user_id=current_user.id,
            note=form.note.data,
        )
        db.session.commit()
    except ValueError as exc:
        flash(str(exc), "error")
        return _quick_add_invalid_response(form, tank)

    if is_htmx_request():
        if measurement.raw_unit_id is not None:
            display_unit = db.session.get(Unit, measurement.raw_unit_id)
        else:
            display_unit = db.session.get(Unit, pt.canonical_unit_id)
        return render_template(
            "measurements/_quick_add_success.html",
            measurement=measurement,
            parameter=pt,
            tank=tank,
            value=measurement.raw_value if measurement.raw_value is not None else measurement.value,
            unit_code=display_unit.code if display_unit is not None else "",
            recorded_at=measurement.recorded_at,
        )

    flash(f"Logged {form.parameter_key.data} on {tank.name}.", "success")
    return redirect(
        url_for(
            "measurements.quick_add_get",
            tank=str(tank.id),
            parameter=form.parameter_key.data,
            logged=1,
        )
    )


@measurements_bp.route("/measurements/batch", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def batch_get() -> Response | str | tuple[str, int]:
    """Render batch entry. Query params: ?tank=<uuid>."""
    raw_tank_id = request.args.get("tank")
    if not raw_tank_id:
        flash("Pick a tank to batch-log readings.", "error")
        return redirect(url_for("measurements.index"))

    try:
        tank = tank_service.get_tank_or_none_unscoped(UUID(raw_tank_id))
    except (TypeError, ValueError):
        return "Invalid tank id", 400
    if tank is None:
        return "Tank not found", 404

    form_cls = build_batch_form_class(tank, default_temp_unit=_temperature_unit_default())
    form = form_cls(data={"tank_id": str(tank.id)})
    if not form.recorded_at.data:
        form.recorded_at.data = tank_local_naive_now(tank)

    return render_template(
        "measurements/batch.html",
        form=form,
        tank=tank,
        parameter_types=parameter_types_for(tank),
    )


@measurements_bp.route("/measurements/batch", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def batch_post() -> Response | str | tuple[str, int]:
    """Persist nonblank batch rows in one transaction."""
    raw_tank_id = request.args.get("tank") or request.form.get("tank_id")
    if not raw_tank_id:
        return "Missing tank id", 400

    try:
        tank = tank_service.get_tank_or_none_unscoped(UUID(raw_tank_id))
    except (TypeError, ValueError):
        return "Invalid tank id", 400
    if tank is None:
        return "Tank not found", 404

    form_cls = build_batch_form_class(tank)
    form = form_cls()
    parameter_types = parameter_types_for(tank)

    if not form.validate_on_submit():
        return render_template(
            "measurements/batch.html",
            form=form,
            tank=tank,
            parameter_types=parameter_types,
        ), 200

    recorded_at = parse_recorded_at_input(form.recorded_at.data.isoformat(), tank)

    rows_to_persist: list[tuple[ParameterType, Decimal, str]] = []
    for parameter_type in parameter_types:
        value_field = getattr(form, f"{parameter_type.key}_value")
        raw_value = value_field.data
        if raw_value is None:
            continue
        unit_field = getattr(form, f"{parameter_type.key}_unit")
        rows_to_persist.append((parameter_type, raw_value, unit_field.data))

    if not rows_to_persist:
        flash("Enter at least one reading.", "error")
        return render_template(
            "measurements/batch.html",
            form=form,
            tank=tank,
            parameter_types=parameter_types,
        ), 200

    try:
        for parameter_type, value, unit in rows_to_persist:
            measurement_service.record_measurement(
                tank=tank,
                parameter_type=parameter_type,
                value=value,
                value_unit=unit,
                recorded_at=recorded_at,
                source="manual",
                recorded_by_user_id=current_user.id,
                note=form.note.data,
            )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return render_template(
            "measurements/batch.html",
            form=form,
            tank=tank,
            parameter_types=parameter_types,
        ), 200

    flash(f"Logged {len(rows_to_persist)} readings on {tank.name}.", "success")
    return redirect(url_for("tanks.detail", tank_id=tank.id))
