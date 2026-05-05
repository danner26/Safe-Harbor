"""Animals views."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required  # type: ignore[import-untyped, unused-ignore]
from flask_wtf import FlaskForm
from sqlalchemy import and_, func, select
from werkzeug.wrappers import Response

from safeharbor.blueprints.animals import animals_bp
from safeharbor.blueprints.animals.forms import (
    AnimalEditForm,
    AnimalForm,
    AnimalImageForm,
    DeceasedForm,
    EventNoteForm,
    MoveAnimalForm,
)
from safeharbor.extensions import db
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank
from safeharbor.services import animal_service, upload_service


def _preselect_tank(form: AnimalForm) -> None:
    tank_arg = request.args.get("tank")
    if not tank_arg:
        return
    try:
        tank_id = UUID(tank_arg)
    except ValueError:
        return
    if any(choice_id == str(tank_id) for choice_id, _label in form.tank_id.choices):
        form.tank_id.data = tank_id


@animals_bp.route("/animals/new", methods=["GET", "POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def new_animal() -> Response | str | tuple[str, int]:
    """Render and process the add-animal form."""
    form = AnimalForm()
    if request.method == "GET":
        _preselect_tank(form)

    if form.validate_on_submit():
        tank = db.session.get(Tank, form.tank_id.data)
        if tank is None or tank.decommission_date is not None:
            abort(400)

        animal = animal_service.create_animal(
            name=form.name.data or None,
            species=form.species.data,
            scientific_name=form.scientific_name.data or None,
            sex=form.sex.data or None,
            acquired_quantity=form.acquired_quantity.data,
            initial_tank=tank,
            acquired_at=form.acquired_at.data,
            notes=form.notes.data,
            initial_note=form.initial_note.data,
            recorded_by_user_id=current_user.id,
        )
        db.session.commit()
        return redirect(url_for("animals.detail_animal", animal_id=animal.id))

    return render_template("animals/form.html", form=form, mode="add"), 200


@animals_bp.route("/animals/<uuid:animal_id>/edit", methods=["GET", "POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def edit_animal(animal_id: UUID) -> Response | str | tuple[str, int]:
    """Render and process the edit-animal form.

    AnimalEditForm only declares editable fields so WTForms cannot apply forged
    acquisition fields; the forbidden-field check adds a visible audit signal.
    """
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    forbidden_field_names = {"acquired_quantity", "tank_id", "acquired_at"} & set(request.form)
    form = AnimalEditForm(obj=animal, forbidden_field_names=forbidden_field_names)

    if form.validate_on_submit():
        animal.name = form.name.data or None
        animal.species = form.species.data
        animal.scientific_name = form.scientific_name.data or None
        animal.sex = form.sex.data or None
        animal.notes = form.notes.data or None
        db.session.commit()
        return redirect(url_for("animals.detail_animal", animal_id=animal.id))

    return (
        render_template(
            "animals/form.html",
            form=form,
            mode="edit",
            animal=animal,
            image_form=AnimalImageForm(),
        ),
        200,
    )


@animals_bp.route("/animals/<uuid:animal_id>/image", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def upload_image(animal_id: UUID) -> Response:
    """Persist or replace the private photo for an existing animal."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    form = AnimalImageForm()
    if form.validate_on_submit():
        try:
            animal.image_path = upload_service.save_image(
                entity_type="animals",
                entity_id=animal.id,
                file_storage=form.image.data,
            )
        except ValueError:
            flash("Photo could not be processed. Choose a JPG, PNG, WebP, or HEIC image.", "error")
        else:
            db.session.commit()
            flash("Animal photo updated.", "success")
    else:
        flash("Choose a JPG, PNG, WebP, or HEIC image to upload.", "error")
    return redirect(url_for("animals.edit_animal", animal_id=animal.id))


@animals_bp.route("/animals/<uuid:animal_id>/image/remove", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def remove_image(animal_id: UUID) -> Response:
    """Remove the private photo for an existing animal."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    upload_service.remove_image(entity_type="animals", entity_id=animal.id)
    animal.image_path = None
    db.session.commit()
    flash("Animal photo removed.", "success")
    return redirect(url_for("animals.edit_animal", animal_id=animal.id))


@animals_bp.route("/animals/<uuid:animal_id>/image", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def serve_image(animal_id: UUID) -> Response:
    """Serve an existing animal photo from private upload storage."""
    animal = db.session.get(Animal, animal_id)
    if animal is None or animal.image_path is None:
        abort(404)
    return upload_service.serve_image_response(entity_type="animals", entity_id=animal.id)


@animals_bp.route("/animals", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def list_animals() -> str:
    """Render all tracked animals with current count and tank context."""
    event_totals = (
        select(
            AnimalEvent.animal_id,
            func.coalesce(func.sum(AnimalEvent.quantity_delta), 0).label("event_delta_total"),
        )
        .group_by(AnimalEvent.animal_id)
        .subquery()
    )
    acquisition_events = (
        select(
            AnimalEvent.animal_id,
            AnimalEvent.occurred_at,
            AnimalEvent.tank_id,
            func.row_number()
            .over(
                partition_by=AnimalEvent.animal_id,
                order_by=(AnimalEvent.occurred_at.asc(), AnimalEvent.id.asc()),
            )
            .label("row_number"),
        )
        .where(AnimalEvent.event_type == EventType.ACQUIRED.value)
        .subquery()
    )
    first_acquisitions = (
        select(
            acquisition_events.c.animal_id,
            acquisition_events.c.occurred_at.label("acquired_at"),
            acquisition_events.c.tank_id.label("acquired_tank_id"),
        )
        .where(acquisition_events.c.row_number == 1)
        .subquery()
    )
    latest_events = animal_service._latest_lifecycle_events_subquery()
    current_count = func.coalesce(event_totals.c.event_delta_total, 0).label("current_count")

    rows = db.session.execute(
        select(
            Animal,
            first_acquisitions.c.acquired_at,
            first_acquisitions.c.acquired_tank_id,
            latest_events.c.tank_id,
            Tank.name.label("tank_name"),
            current_count,
        )
        .outerjoin(event_totals, event_totals.c.animal_id == Animal.id)
        .outerjoin(first_acquisitions, first_acquisitions.c.animal_id == Animal.id)
        .outerjoin(latest_events, latest_events.c.animal_id == Animal.id)
        .outerjoin(
            Tank,
            and_(
                Tank.id == latest_events.c.tank_id,
                Tank.decommission_date.is_(None),
            ),
        )
        .order_by(Animal.created_at.asc(), Animal.id.asc())
    ).all()

    acquired_tank_ids = {
        acquired_tank_id
        for _animal, _acquired_at, acquired_tank_id, _tank_id, _tank_name, _count in rows
        if acquired_tank_id is not None
    }
    acquired_tank_by_id: dict[UUID, Tank] = {}
    if acquired_tank_ids:
        acquired_tank_by_id = {
            tank.id: tank
            for tank in db.session.scalars(select(Tank).where(Tank.id.in_(acquired_tank_ids))).all()
        }

    animal_rows = []
    for animal, acquired_at, acquired_tank_id, _tank_id, tank_name, count in rows:
        current_count_int = int(count or 0)
        status = "alive" if current_count_int > 0 else "deceased"
        animal_rows.append(
            {
                "animal": animal,
                "acquired_at": acquired_at if isinstance(acquired_at, datetime) else None,
                "acquired_tank": acquired_tank_by_id.get(acquired_tank_id),
                "tank_name": tank_name if current_count_int > 0 else None,
                "status": status,
            }
        )
    alive_count, deceased_count, tank_count = animal_service.list_summary()

    return render_template(
        "animals/list.html",
        animal_rows=animal_rows,
        alive_count=alive_count,
        deceased_count=deceased_count,
        tank_count=tank_count,
    )


@animals_bp.route("/animals/<uuid:animal_id>", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def detail_animal(animal_id: UUID) -> str:
    """Render one animal's current state and lifecycle timeline."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    return render_template("animals/detail.html", **_detail_context(animal))


def _detail_context(
    animal: Animal,
    *,
    deceased_form: DeceasedForm | None = None,
    note_form: EventNoteForm | None = None,
) -> dict[str, object]:
    events = animal_service.lifecycle_rows(animal)
    tank_ids = {row["tank_id"] for row in events if row["tank_id"] is not None}
    tank_by_id: dict[UUID, Tank] = {}
    if tank_ids:
        tank_by_id = {
            tank.id: tank
            for tank in db.session.scalars(select(Tank).where(Tank.id.in_(tank_ids))).all()
        }

    alive = animal_service.is_alive(animal)
    count = animal_service.current_count(animal)
    return {
        "animal": animal,
        "current_count": count,
        "current_tank": animal_service.current_tank(animal),
        "is_alive": alive,
        "events": events,
        "tank_by_id": tank_by_id,
        "can_delete": animal_service.can_delete_if_pristine(animal),
        "delete_form": FlaskForm(),
        "move_form": MoveAnimalForm() if alive else None,
        "deceased_form": deceased_form
        if deceased_form is not None
        else DeceasedForm(quantity=count)
        if alive
        else None,
        "note_form": note_form if note_form is not None else EventNoteForm(),
    }


@animals_bp.route("/animals/<uuid:animal_id>/move", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def move_animal(animal_id: UUID) -> Response:
    """Move an alive animal to another active tank."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    form = MoveAnimalForm()
    detail_url = url_for("animals.detail_animal", animal_id=animal.id)
    if not form.validate_on_submit():
        message = next(iter(form.errors.values()), ["Move could not be saved."])[0]
        flash(message, "error")
        return redirect(detail_url)

    to_tank = db.session.get(Tank, form.to_tank_id.data)
    if to_tank is None:
        flash("Destination tank not found.", "error")
        return redirect(detail_url)

    try:
        animal_service.move_animal(
            animal,
            to_tank=to_tank,
            occurred_at=form.occurred_at.data,
            note=form.note.data,
            recorded_by_user_id=current_user.id,
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(detail_url)

    db.session.commit()
    flash(f"Moved to {to_tank.name}.", "success")
    return redirect(detail_url)


@animals_bp.route("/animals/<uuid:animal_id>/deceased", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def mark_deceased(animal_id: UUID) -> Response | tuple[str, int]:
    """Record a deceased lifecycle event for an animal."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    form = DeceasedForm()
    detail_url = url_for("animals.detail_animal", animal_id=animal.id)
    if not form.validate_on_submit():
        message = next(iter(form.errors.values()), ["Deceased event could not be saved."])[0]
        flash(message, "error")
        return redirect(detail_url)

    try:
        animal_service.mark_deceased(
            animal,
            quantity=form.quantity.data,
            occurred_at=form.occurred_at.data,
            note=form.note.data,
            recorded_by_user_id=current_user.id,
        )
    except ValueError as exc:
        db.session.rollback()
        form.quantity.errors.append(str(exc))
        flash(str(exc), "error")
        return (
            render_template(
                "animals/detail.html",
                **_detail_context(animal, deceased_form=form),
            ),
            200,
        )

    db.session.commit()
    flash(f"Marked {form.quantity.data} deceased.", "success")
    return redirect(detail_url)


@animals_bp.route("/animals/<uuid:animal_id>/note", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def add_note(animal_id: UUID) -> Response:
    """Record a generic health note or observation for an animal."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    form = EventNoteForm()
    detail_url = url_for("animals.detail_animal", animal_id=animal.id)
    if not form.validate_on_submit():
        message = next(iter(form.errors.values()), ["Note could not be saved."])[0]
        flash(message, "error")
        return redirect(detail_url)

    try:
        animal_service.record_event(
            animal,
            event_type=form.event_type.data,
            occurred_at=form.occurred_at.data,
            note=form.note.data,
            recorded_by_user_id=current_user.id,
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(detail_url)

    db.session.commit()
    flash("Note added.", "success")
    return redirect(detail_url)


@animals_bp.route("/animals/<uuid:animal_id>/delete", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def delete_animal(animal_id: UUID) -> Response:
    """Delete a pristine animal and its initial acquired event."""
    animal = db.session.get(Animal, animal_id)
    if animal is None:
        abort(404)

    form = FlaskForm()
    detail_url = url_for("animals.detail_animal", animal_id=animal.id)
    if not form.validate_on_submit():
        message = next(iter(form.errors.values()), ["Delete could not be saved."])[0]
        flash(message, "error")
        return redirect(detail_url)

    try:
        animal_service.delete_if_pristine(animal)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(detail_url)

    db.session.commit()
    flash("Animal deleted.", "success")
    return redirect(url_for("animals.list_animals"))


__all__ = ["animals_bp"]
