"""Home page — post-login dashboard."""

from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_login import current_user  # type: ignore[import-untyped, unused-ignore]
from sqlalchemy import select

from safeharbor.extensions import db
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import measurement_service, tank_service

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index() -> str:
    """Render the dashboard with live KPI strip + recent measurements."""
    tanks = tank_service.active_tanks(limit=6)
    most_recent = tanks[0] if tanks else None

    kpi_cards = measurement_service.kpi_context(
        most_recent,
        user=current_user,
        accept_language=request.headers.get("Accept-Language"),
    )
    pt_display, pt_unit = measurement_service.parameter_display_maps()
    unit_display_by_id = {unit.id: unit.display for unit in db.session.scalars(select(Unit)).all()}
    tank_display = {tank.id: tank.name for tank in tanks}
    tank_by_id = {tank.id: tank for tank in tanks}
    health_by_tank_id = tank_service.compute_tank_health_bulk(tanks)
    recent = measurement_service.recent_across_tanks(limit=10)
    recent_tank_ids = {row.tank_id for row in recent}
    missing_tank_ids = recent_tank_ids.difference(tank_display)
    if missing_tank_ids:
        recent_tanks = db.session.scalars(select(Tank).where(Tank.id.in_(missing_tank_ids))).all()
        tank_display.update({tank.id: tank.name for tank in recent_tanks})
        tank_by_id.update({tank.id: tank for tank in recent_tanks})

    return render_template(
        "home/index.html",
        tanks=tanks,
        kpi_cards=kpi_cards,
        recent=recent,
        pt_display=pt_display,
        pt_unit=pt_unit,
        unit_display_by_id=unit_display_by_id,
        tank_display=tank_display,
        tank_by_id=tank_by_id,
        health_by_tank_id=health_by_tank_id,
    )
