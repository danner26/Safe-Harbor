"""Tank views — list, detail, create, edit, decommission, restore."""

from __future__ import annotations

import os
from urllib.parse import urlencode
from uuid import UUID

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required  # type: ignore[import-untyped, unused-ignore]
from sqlalchemy import select
from werkzeug.wrappers import Response

from safeharbor.blueprints.tanks import tanks_bp
from safeharbor.blueprints.tanks.forms import TankForm, TankImageForm
from safeharbor.extensions import db
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import WaterType, profiles_for_water_type
from safeharbor.models.unit import Unit
from safeharbor.services import animal_service, measurement_service, tank_service, upload_service
from safeharbor.utils.dates import format_recorded_at
from safeharbor.utils.htmx import is_htmx_request
from safeharbor.utils.units import (
    PARAMETER_KEYS,
    liters_to_display,
    parse_volume_input,
    resolve_unit_pref,
)

_CHART_RANGE_TOKENS = {"24h", "7d", "30d", "1y"}
_TANK_PROFILE_LABELS = {
    "tropical_fw_community": "Tropical Freshwater Community",
    "coldwater_fw": "Coldwater Freshwater (Goldfish)",
    "planted_fw": "Planted Freshwater",
    "reef_sw": "Reef Saltwater",
    "fowlr_sw": "Fish-Only Saltwater (FOWLR)",
    "brackish": "Brackish",
}


def _tank_profile_label(profile_key: str) -> str:
    """Return the user-facing label for a tank profile key."""
    return _TANK_PROFILE_LABELS.get(profile_key, "Unknown profile")


def _profile_options_for_water_type(water_type: str) -> list[tuple[str, str]]:
    """Return profile option values and labels for the requested water type."""
    return [
        (profile_key, _tank_profile_label(profile_key))
        for profile_key in profiles_for_water_type(water_type)
    ]


def _default_volume_unit() -> str:
    """Return 'L' or 'gal' based on the current user's pref + Accept-Language fallback."""
    pref = getattr(current_user, "preferred_units", None)
    accept_language = request.headers.get("Accept-Language")
    return "gal" if resolve_unit_pref(pref, accept_language) == "imperial" else "L"


@tanks_bp.route("/tanks", methods=["GET"])
def list_tanks() -> str:
    """List active tanks by default; the status query can show soft-deleted rows.

    ?view=table switches the layout from cards to a data table.
    """
    status_filter = request.args.get("status", "active")
    view = request.args.get("view", "cards")
    if status_filter == "decommissioned":
        tanks = tank_service.decommissioned_tanks()
    else:
        tanks = tank_service.active_tanks()
    health_by_tank_id = tank_service.compute_tank_health_bulk(tanks)
    return render_template(
        "tanks/list.html",
        tanks=tanks,
        status_filter=status_filter,
        view=view,
        health_by_tank_id=health_by_tank_id,
    )


@tanks_bp.route("/tanks/profile-options/", defaults={"water_type": ""}, methods=["GET"])
@tanks_bp.route("/tanks/profile-options/<water_type>", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def profile_options_for_water_type(water_type: str) -> str:
    """Return tank profile <option> tags for the selected water type."""
    water_type = water_type or request.args.get("water_type", "")
    if water_type not in {known_water_type.value for known_water_type in WaterType}:
        abort(400)

    return render_template(
        "tanks/_profile_options.html",
        profiles=_profile_options_for_water_type(water_type),
    )


@tanks_bp.route("/tanks/new", methods=["GET"])
def new_tank() -> str:
    """Render the empty tank creation form with a sensible default unit."""
    form = TankForm()
    if not form.is_submitted():
        requested_water_type = request.args.get("water_type")
        if requested_water_type in {known_water_type.value for known_water_type in WaterType}:
            form.water_type.data = requested_water_type
        form.volume_unit.data = _default_volume_unit()
        if form.timezone.data is None:
            form.timezone.data = (
                current_app.config.get("DEFAULT_TZ") or os.environ.get("DEFAULT_TZ") or "UTC"
            )
        default_water_type = form.water_type.data or "fresh"
        form.profile_key.choices = _profile_options_for_water_type(default_water_type)
        profiles = profiles_for_water_type(default_water_type)
        if profiles and not form.profile_key.data:
            form.profile_key.data = profiles[0]
    return render_template("tanks/form.html", form=form, image_form=None, tank=None)


@tanks_bp.route("/tanks", methods=["POST"])
def create_tank() -> Response | str | tuple[str, int]:
    """Validate the tank form and persist a new tank row on success."""
    form = TankForm()
    if form.validate_on_submit():
        liters = (
            parse_volume_input(form.volume.data, form.volume_unit.data)
            if form.volume.data is not None
            else None
        )
        tank = tank_service.create_tank(
            name=form.name.data,
            water_type=form.water_type.data,
            profile_key=form.profile_key.data,
            volume_liters=liters,
            setup_date=form.setup_date.data,
            substrate=form.substrate.data,
            equipment_notes=form.equipment_notes.data,
            timezone=form.timezone.data,
            created_by_user_id=current_user.id,
        )
        db.session.commit()
        flash(f"Created tank {tank.name}.", "success")
        return redirect(url_for("tanks.detail", tank_id=tank.id))
    return render_template("tanks/form.html", form=form, image_form=None, tank=None), 200


@tanks_bp.route("/tanks/<uuid:tank_id>", methods=["GET"])
def detail(tank_id: UUID) -> str:
    """Render the tank detail page with live KPI, recent history, and chart data."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)

    health = tank_service.compute_tank_health(tank)
    kpi_cards = measurement_service.kpi_context(
        tank,
        user=current_user,
        accept_language=request.headers.get("Accept-Language"),
    )
    pt_display, pt_unit = measurement_service.parameter_display_maps()
    unit_display_by_id = {unit.id: unit.display for unit in db.session.scalars(select(Unit)).all()}
    recent = measurement_service.history_for_tank(tank, limit=10)
    tank_display = {tank.id: tank.name}
    tank_by_id = {tank.id: tank}
    chart_parameters = [
        ("temperature", "Temperature"),
        ("ph", "pH"),
        *([] if tank.water_type == "fresh" else [("salinity", "Salinity")]),
        ("nitrate", "Nitrate"),
    ]

    return render_template(
        "tanks/detail.html",
        tank=tank,
        kpi_cards=kpi_cards,
        recent=recent,
        pt_display=pt_display,
        pt_unit=pt_unit,
        unit_display_by_id=unit_display_by_id,
        tank_display=tank_display,
        tank_by_id=tank_by_id,
        chart_parameters=chart_parameters,
        health=health,
        tank_profile_label=_tank_profile_label(tank.profile_key),
        inhabitants=animal_service.animals_on_tank(tank),
    )


@tanks_bp.route("/tanks/<uuid:tank_id>/edit", methods=["GET"])
def edit(tank_id: UUID) -> str:
    """Pre-fill the tank form with stored values; convert liters to user-pref unit."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)
    form = TankForm(obj=tank)
    image_form = TankImageForm()
    if not form.is_submitted():
        # Convert stored liters back to user pref unit for display.
        pref = getattr(current_user, "preferred_units", None)
        accept_language = request.headers.get("Accept-Language")
        value, unit = liters_to_display(tank.volume_liters, pref, accept_language)
        form.volume.data = value
        form.volume_unit.data = unit
    return render_template("tanks/form.html", form=form, image_form=image_form, tank=tank)


@tanks_bp.route("/tanks/<uuid:tank_id>", methods=["POST"])
def update_tank(tank_id: UUID) -> Response | str | tuple[str, int]:
    """Validate the tank form and persist changes to an existing tank on success."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)
    form = TankForm()
    if form.validate_on_submit():
        liters = (
            parse_volume_input(form.volume.data, form.volume_unit.data)
            if form.volume.data is not None
            else None
        )
        tank_service.update_tank(
            tank,
            name=form.name.data,
            water_type=form.water_type.data,
            profile_key=form.profile_key.data,
            volume_liters=liters,
            setup_date=form.setup_date.data,
            substrate=form.substrate.data,
            equipment_notes=form.equipment_notes.data,
            timezone=form.timezone.data,
        )
        db.session.commit()
        flash(f"Saved {tank.name}.", "success")
        return redirect(url_for("tanks.detail", tank_id=tank.id))
    return render_template(
        "tanks/form.html",
        form=form,
        image_form=TankImageForm(),
        tank=tank,
    ), 200


@tanks_bp.route("/tanks/<uuid:tank_id>/image", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def upload_image(tank_id: UUID) -> Response:
    """Persist or replace the private photo for an existing tank."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)

    form = TankImageForm()
    if form.validate_on_submit():
        try:
            tank.image_path = upload_service.save_image(
                entity_type="tanks",
                entity_id=tank.id,
                file_storage=form.image.data,
            )
        except ValueError:
            flash("Photo could not be processed. Choose a JPG, PNG, WebP, or HEIC image.", "error")
        else:
            db.session.commit()
            flash("Tank photo updated.", "success")
    else:
        flash("Choose a JPG, PNG, WebP, or HEIC image to upload.", "error")
    return redirect(url_for("tanks.edit", tank_id=tank.id))


@tanks_bp.route("/tanks/<uuid:tank_id>/image/remove", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def remove_image(tank_id: UUID) -> Response:
    """Remove the private photo for an existing tank."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)

    upload_service.remove_image(entity_type="tanks", entity_id=tank.id)
    tank.image_path = None
    db.session.commit()
    flash("Tank photo removed.", "success")
    return redirect(url_for("tanks.edit", tank_id=tank.id))


@tanks_bp.route("/tanks/<uuid:tank_id>/image", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def serve_image(tank_id: UUID) -> Response:
    """Serve an existing tank photo from private upload storage."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None or tank.image_path is None:
        abort(404)
    return upload_service.serve_image_response(entity_type="tanks", entity_id=tank.id)


@tanks_bp.route("/tanks/<uuid:tank_id>/decommission", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def decommission_tank(tank_id: UUID) -> Response | str:
    """Soft-delete the tank by setting decommission_date to today."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)
    tank_service.decommission(tank)
    db.session.commit()
    if is_htmx_request():
        return render_template("tanks/_decommission_button.html", tank=tank)
    flash("Tank decommissioned.", "success")
    return redirect(url_for("tanks.list_tanks"))


@tanks_bp.route("/tanks/<uuid:tank_id>/restore", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def restore_tank(tank_id: UUID) -> Response | str:
    """Restore a decommissioned tank by nulling its decommission_date."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)
    tank_service.restore(tank)
    db.session.commit()
    if is_htmx_request():
        return render_template("tanks/_decommission_button.html", tank=tank)
    flash(f"Restored {tank.name}.", "success")
    return redirect(url_for("tanks.detail", tank_id=tank.id))


@tanks_bp.route("/tanks/<uuid:tank_id>/history", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def history(tank_id: UUID) -> Response | str | tuple[str, int]:
    """Render paginated measurement history for one tank."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)

    try:
        params = tank_service.parse_history_query_params(request.args)
    except ValueError as exc:
        flash(str(exc), "error")
        return _render_history_page(
            tank=tank,
            rows=[],
            parameter_key=request.args.get("parameter") or None,
            from_str=request.args.get("from") or None,
            to_str=request.args.get("to") or None,
            page=1,
            has_next=False,
            prev_url=None,
            next_url=None,
        ), 400

    parameter_key = params.parameter_keys[0] if params.parameter_keys else None
    rows = measurement_service.history_for_tank(
        tank,
        parameter_key=parameter_key,
        from_dt=params.from_date,
        to_dt=params.to_date,
        limit=params.page_size + 1,
        offset=(params.page - 1) * params.page_size,
    )
    has_next = len(rows) > params.page_size
    rows = rows[: params.page_size]

    query_args: dict[str, str] = {}
    if parameter_key is not None:
        query_args["parameter"] = parameter_key
    from_str = request.args.get("from") or None
    to_str = request.args.get("to") or None
    if from_str is not None:
        query_args["from"] = from_str
    if to_str is not None:
        query_args["to"] = to_str

    def page_url(next_page: int) -> str:
        args = {"page": str(next_page), **query_args}
        return f"{url_for('tanks.history', tank_id=tank.id)}?{urlencode(args)}"

    prev_url = page_url(params.page - 1) if params.page > 1 else None
    next_url = page_url(params.page + 1) if has_next else None

    return _render_history_page(
        tank=tank,
        rows=rows,
        parameter_key=parameter_key,
        from_str=from_str,
        to_str=to_str,
        page=params.page,
        has_next=has_next,
        prev_url=prev_url,
        next_url=next_url,
    )


def _render_history_page(
    *,
    tank: object,
    rows: object,
    parameter_key: str | None,
    from_str: str | None,
    to_str: str | None,
    page: int,
    has_next: bool,
    prev_url: str | None,
    next_url: str | None,
) -> str:
    parameter_types = db.session.scalars(
        select(ParameterType).order_by(ParameterType.display_order, ParameterType.display_name)
    ).all()
    pt_display, pt_unit = measurement_service.parameter_display_maps()
    unit_display_by_id = {unit.id: unit.display for unit in db.session.scalars(select(Unit)).all()}
    return render_template(
        "measurements/history.html",
        tank=tank,
        rows=rows,
        parameter_types=parameter_types,
        pt_display=pt_display,
        pt_unit=pt_unit,
        unit_display_by_id=unit_display_by_id,
        parameter_key=parameter_key,
        from_str=from_str,
        to_str=to_str,
        page=page,
        has_next=has_next,
        prev_url=prev_url,
        next_url=next_url,
    )


@tanks_bp.route("/tanks/<uuid:tank_id>/chart-data", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def chart_data(tank_id: UUID) -> Response | tuple[str, int]:
    """Return Plotly-ready measurement points for one tank and parameter."""
    tank = tank_service.get_tank_or_none_unscoped(tank_id)
    if tank is None:
        abort(404)

    parameter_key = request.args.get("parameter", "")
    range_token = request.args.get("range", "")

    if parameter_key not in PARAMETER_KEYS:
        return "Invalid parameter", 400

    if range_token not in _CHART_RANGE_TOKENS:
        return "Unknown range", 400

    series = measurement_service.time_series_for_chart(
        tank,
        parameter_key=parameter_key,
        range_token=range_token,
    )
    return jsonify(
        {
            "data": [
                {
                    "recorded_at": recorded_at.isoformat(),
                    "recorded_at_local": format_recorded_at(recorded_at, tank, fmt="iso"),
                    "value": str(value),
                }
                for recorded_at, value in series
            ],
        }
    )
