"""Dev-only routes: design-system styleguide + visual-test fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import Blueprint, abort, current_app, redirect, render_template, session, url_for
from sqlalchemy import delete, select
from werkzeug.datastructures import FileStorage

from safeharbor.blueprints.auth.decorators import public
from safeharbor.extensions import db

if TYPE_CHECKING:
    from safeharbor.models.account import User
    from safeharbor.models.tank import Tank

dev_bp = Blueprint("dev", __name__)

_VISUAL_ADMIN_EMAIL = "visual-admin@x.com"
_VISUAL_KEEPER_EMAIL = "visual-keeper@x.com"
_FIXTURE_NOTE_PREFIX = "visual-fixture:"
_FIXED_VISUAL_NOW = datetime(2026, 4, 15, 12, tzinfo=UTC)
_VISUAL_FIXTURE_DIR = Path("tests/visual/fixtures")


def _is_dev_or_test() -> bool:
    return bool(current_app.config.get("ENABLE_DEV_ROUTES", False))


def _visual_admin_password() -> str:
    password = current_app.config.get("DEV_VISUAL_ADMIN_PASSWORD")
    if not password:
        abort(500, description="DEV_VISUAL_ADMIN_PASSWORD is not configured")
    return str(password)


def _ensure_reference_data() -> None:
    """Run the idempotent seed CLI through Flask's test CLI runner."""
    result = current_app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    if result.exit_code != 0:
        abort(500, description=f"safeharbor seed failed: {result.output}")


def _ensure_visual_admin() -> Any:
    """Ensure the visual-test admin exists and is usable for Flask-Login."""
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    admin = db.session.scalar(select(User).where(User.email == _VISUAL_ADMIN_EMAIL))
    if admin is None:
        admin = User(
            email=_VISUAL_ADMIN_EMAIL,
            password_hash=hash_password(_visual_admin_password()),
            is_superuser=True,
        )
        db.session.add(admin)
        db.session.commit()
    return admin


def _ensure_visual_keeper(admin: User) -> Any:
    """Ensure a second fixture user exists for attribution-only screenshots."""
    from safeharbor.models.account import User

    keeper = db.session.scalar(select(User).where(User.email == _VISUAL_KEEPER_EMAIL))
    if keeper is None:
        keeper = User(
            email=_VISUAL_KEEPER_EMAIL,
            username=None,
            password_hash=admin.password_hash,
            is_superuser=False,
        )
        db.session.add(keeper)
    else:
        keeper.username = None
        keeper.is_superuser = False
    db.session.commit()
    return keeper


def _authenticate(admin: User) -> None:
    session["_user_id"] = str(admin.id)
    session["_fresh"] = True


def _visual_fixture_path(filename: str) -> Path | None:
    """Return a checked-in visual fixture asset path when it is present."""
    candidates = [
        Path.cwd() / _VISUAL_FIXTURE_DIR / filename,
        Path(current_app.root_path).parents[1] / _VISUAL_FIXTURE_DIR / filename,
        Path("/tmp") / _VISUAL_FIXTURE_DIR / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _generated_visual_fixture_stream(filename: str) -> BytesIO:
    """Build deterministic dev-fixture-only JPG bytes when tests are absent."""
    from PIL import Image, ImageDraw

    if filename == "sample-tank-photo.jpg":
        image = Image.new("RGB", (96, 64), "#d7f2ff")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 42, 95, 63), fill="#147c8c")
        draw.rectangle((8, 8, 87, 52), outline="#1f2937", width=3)
        draw.polygon([(18, 42), (40, 22), (63, 42)], fill="#f5c542")
        draw.ellipse((63, 18, 80, 32), fill="#ef6f4c")
    elif filename == "sample-animal-photo.jpg":
        image = Image.new("RGB", (64, 64), "#113f67")
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 16, 48, 44), fill="#ffb74d")
        draw.polygon([(44, 30), (58, 18), (58, 42)], fill="#ff8a65")
        draw.ellipse((18, 26, 23, 31), fill="#1f2937")
        draw.arc((5, 10, 55, 54), 200, 335, fill="#d7f2ff", width=2)
    else:
        abort(500, description=f"Unknown visual fixture asset: {filename}")

    stream = BytesIO()
    image.save(stream, format="JPEG", quality=90)
    stream.seek(0)
    return stream


def _save_visual_fixture_image(
    *,
    entity_type: str,
    entity_id: Any,
    filename: str,
) -> str:
    """Save one checked-in fixture JPG through the upload pipeline."""
    from safeharbor.services import upload_service

    fixture_path = _visual_fixture_path(filename)
    if fixture_path is None:
        generated_stream = _generated_visual_fixture_stream(filename)
        storage = FileStorage(stream=generated_stream, filename=filename, content_type="image/jpeg")
        return upload_service.save_image(
            entity_type=entity_type,
            entity_id=entity_id,
            file_storage=storage,
        )

    with fixture_path.open("rb") as fixture_stream:
        storage = FileStorage(stream=fixture_stream, filename=filename, content_type="image/jpeg")
        return upload_service.save_image(
            entity_type=entity_type,
            entity_id=entity_id,
            file_storage=storage,
        )


def _attach_visual_tank_photo(tank: Tank) -> None:
    tank.image_path = _save_visual_fixture_image(
        entity_type="tanks",
        entity_id=tank.id,
        filename="sample-tank-photo.jpg",
    )


def _clear_visual_tank_photo(tank: Tank, admin: User) -> None:
    from safeharbor.services import upload_service

    if tank.created_by_user_id != admin.id:
        return
    upload_service.remove_image(entity_type="tanks", entity_id=tank.id)
    tank.image_path = None


def _attach_visual_animal_photo(animal: Any) -> None:
    animal.image_path = _save_visual_fixture_image(
        entity_type="animals",
        entity_id=animal.id,
        filename="sample-animal-photo.jpg",
    )


def _clear_visual_animal_photo(animal: Any) -> None:
    from safeharbor.services import upload_service

    upload_service.remove_image(entity_type="animals", entity_id=animal.id)
    animal.image_path = None


def _default_visual_profile_key(water_type: str) -> str:
    """Return a valid profile for deterministic visual tanks by water type."""
    return {
        "fresh": "planted_fw",
        "salt": "reef_sw",
        "brackish": "brackish",
    }[water_type]


def _ensure_visual_tank(
    admin: User,
    *,
    name: str,
    water_type: str,
    profile_key: str | None = None,
) -> Any:
    """Ensure a named tank exists with stable visual fixture attributes."""
    from safeharbor.models.tank import Tank

    resolved_profile_key = profile_key or _default_visual_profile_key(water_type)
    tank = db.session.scalar(
        select(Tank).where(Tank.name == name, Tank.created_by_user_id == admin.id)
    )
    if tank is None:
        tank = Tank(
            name=name,
            water_type=water_type,
            profile_key=resolved_profile_key,
            volume_liters=Decimal("340.69"),
            equipment_notes="Eheim 2217\nRadion XR15",
            created_by_user_id=admin.id,
        )
        db.session.add(tank)
    else:
        tank.water_type = water_type
        tank.profile_key = resolved_profile_key
        tank.volume_liters = Decimal("340.69")
        tank.equipment_notes = "Eheim 2217\nRadion XR15"
        tank.decommission_date = None
        if tank.created_by_user_id is None:
            tank.created_by_user_id = admin.id
    db.session.commit()
    return tank


def _set_visual_active_tanks(admin: User, active_names: set[str]) -> None:
    """Make the local visual-fixture DB expose only the requested active tanks."""
    from safeharbor.models.tank import Tank

    for tank in db.session.scalars(select(Tank).where(Tank.created_by_user_id == admin.id)).all():
        tank.decommission_date = None if tank.name in active_names else date(2026, 4, 15)
    db.session.commit()


def _refresh_visual_measurements(tank: Tank, admin: User, rows: list[tuple[str, str, str]]) -> None:
    """Replace this tank's fixture-owned readings with fresh, chart-visible data."""
    from safeharbor.models.measurement import Measurement
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    db.session.execute(
        delete(Measurement)
        .where(Measurement.tank_id == tank.id)
        .where(Measurement.note.like(f"{_FIXTURE_NOTE_PREFIX}%"))
    )
    db.session.flush()

    for index, (parameter_key, value, unit) in enumerate(rows):
        parameter_type = db.session.scalar(
            select(ParameterType).where(ParameterType.key == parameter_key)
        )
        if parameter_type is None:
            abort(500, description=f"Missing seeded parameter type: {parameter_key}")
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=parameter_type,
            value=Decimal(value),
            value_unit=unit,
            recorded_at=_FIXED_VISUAL_NOW - timedelta(hours=index * 6),
            source="manual",
            recorded_by_user_id=admin.id,
            note=f"{_FIXTURE_NOTE_PREFIX}{parameter_key}-{index}",
        )
    db.session.commit()


def _tank_detail_rows() -> list[tuple[str, str, str]]:
    """Stable live-data rows used by tank-detail and dashboard visual fixtures."""
    return [
        ("temperature", "25.5", "degC"),
        ("ph", "8.2", "pH"),
        ("salinity", "35.0", "ppt"),
        ("nitrate", "4.0", "ppm"),
        ("calcium", "430", "ppm"),
    ]


def _tank_list_health_rows(water_type: str, rollup: str) -> list[tuple[str, str, str]]:
    """Rows that make tank-list fixture badges exercise distinct health states."""
    healthy_by_water_type = {
        "salt": [
            ("temperature", "25.5", "degC"),
            ("ph", "8.2", "pH"),
            ("salinity", "34.0", "ppt"),
            ("ammonia", "0.02", "ppm"),
            ("nitrite", "0.02", "ppm"),
            ("nitrate", "4.0", "ppm"),
            ("phosphate", "0.03", "ppm"),
            ("kh", "10.0", "dKH"),
            ("calcium", "420", "ppm"),
            ("magnesium", "1325", "ppm"),
        ],
        "fresh": [
            ("temperature", "25.0", "degC"),
            ("ph", "7.0", "pH"),
            ("ammonia", "0.10", "ppm"),
            ("nitrite", "0.10", "ppm"),
            ("nitrate", "20.0", "ppm"),
            ("phosphate", "0.20", "ppm"),
            ("kh", "6.0", "dKH"),
            ("gh", "8.0", "dGH"),
        ],
        "brackish": [
            ("temperature", "26.0", "degC"),
            ("ph", "8.0", "pH"),
            ("salinity", "10.0", "ppt"),
            ("ammonia", "0.10", "ppm"),
            ("nitrite", "0.10", "ppm"),
            ("nitrate", "20.0", "ppm"),
            ("phosphate", "0.20", "ppm"),
            ("kh", "10.0", "dKH"),
        ],
    }
    rows = list(healthy_by_water_type[water_type])
    if rollup == "watch":
        rows[0] = ("temperature", "22.2", "degC")
    elif rollup == "unhealthy":
        rows[3] = ("ammonia", "0.50", "ppm")
    return rows


def _refresh_visual_tank_health_measurements(
    tank: Tank,
    admin: User,
    *,
    expected_rollup: str,
    recorded_base: datetime,
) -> None:
    """Replace fixture-owned readings and verify the tank rolls up as intended."""
    from safeharbor.models.measurement import Measurement
    from safeharbor.services import measurement_service, tank_service

    db.session.execute(
        delete(Measurement)
        .where(Measurement.tank_id == tank.id)
        .where(Measurement.note.like(f"{_FIXTURE_NOTE_PREFIX}%"))
    )
    db.session.flush()

    for index, (parameter_key, value, unit) in enumerate(
        _tank_list_health_rows(tank.water_type, expected_rollup)
    ):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=_parameter_type_or_500(parameter_key),
            value=Decimal(value),
            value_unit=unit,
            recorded_at=recorded_base - timedelta(minutes=index),
            source="manual",
            recorded_by_user_id=admin.id,
            note=f"{_FIXTURE_NOTE_PREFIX} tank-list-health-{expected_rollup}-{parameter_key}",
        )
    health = tank_service.compute_tank_health(tank)
    if health.rollup != expected_rollup:
        abort(
            500,
            description=(
                f"Visual fixture tank {tank.name!r} expected {expected_rollup} "
                f"but computed {health.rollup}"
            ),
        )


def _history_rows() -> list[tuple[str, str, str]]:
    """Stable 30-row history fixture with varied saltwater parameters."""
    cycle = [
        ("temperature", "25.5", "degC"),
        ("ph", "8.2", "pH"),
        ("salinity", "35.0", "ppt"),
        ("nitrate", "4.0", "ppm"),
        ("calcium", "430", "ppm"),
        ("magnesium", "1330", "ppm"),
        ("kh", "9.0", "dKH"),
        ("temperature", "25.2", "degC"),
        ("ph", "8.1", "pH"),
        ("salinity", "34.8", "ppt"),
        ("nitrate", "5.0", "ppm"),
        ("calcium", "425", "ppm"),
        ("magnesium", "1320", "ppm"),
        ("kh", "8.8", "dKH"),
        ("temperature", "24.9", "degC"),
    ]
    return [*cycle, *cycle]


def _parameter_type_or_500(parameter_key: str) -> Any:
    """Return a seeded parameter type or abort with a helpful fixture error."""
    from safeharbor.models.parameter_type import ParameterType

    parameter_type = db.session.scalar(
        select(ParameterType).where(ParameterType.key == parameter_key)
    )
    if parameter_type is None:
        abort(500, description=f"Missing seeded parameter type: {parameter_key}")
    return parameter_type


def _seed_visual_reef_with_readings(admin: User, *, include_photo: bool = False) -> Any:
    """Ensure Visual Reef exists with deterministic live readings."""
    tank = _ensure_visual_tank(admin, name="Visual Reef", water_type="salt")
    _refresh_visual_measurements(tank, admin, _tank_detail_rows())
    if include_photo:
        _attach_visual_tank_photo(tank)
    else:
        _clear_visual_tank_photo(tank, admin)
    db.session.commit()
    return tank


def _seed_history_with_badges_and_attribution(admin: User) -> Any:
    """Seed five history rows covering ok/caution/danger badges and two users."""
    from safeharbor.models.measurement import Measurement
    from safeharbor.services import measurement_service

    keeper = _ensure_visual_keeper(admin)
    tank = _ensure_visual_tank(admin, name="Badge History Reef", water_type="salt")
    db.session.execute(
        delete(Measurement)
        .where(Measurement.tank_id == tank.id)
        .where(Measurement.note.like(f"{_FIXTURE_NOTE_PREFIX}%"))
    )
    db.session.flush()

    rows = [
        ("temperature", "25.5", "degC", admin.id, "temperature-ok"),
        ("temperature", "24.2", "degC", keeper.id, "temperature-caution"),
        ("temperature", "28.2", "degC", admin.id, "temperature-danger"),
        ("ph", "8.2", "pH", keeper.id, "ph-ok"),
        ("nitrate", "6.0", "ppm", admin.id, "nitrate-ok"),
    ]
    for index, (parameter_key, value, unit, user_id, note_slug) in enumerate(rows):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=_parameter_type_or_500(parameter_key),
            value=Decimal(value),
            value_unit=unit,
            recorded_at=_FIXED_VISUAL_NOW - timedelta(hours=index * 3),
            source="manual",
            recorded_by_user_id=user_id,
            note=f"{_FIXTURE_NOTE_PREFIX} {note_slug}",
        )
    db.session.commit()
    return tank


def _seed_measurement_edit_scene(admin: User) -> Any:
    """Seed one reading and return it for the edit-form visual fixture."""
    from safeharbor.models.measurement import Measurement
    from safeharbor.services import measurement_service

    tank = _ensure_visual_tank(admin, name="Edit Fixture Reef", water_type="salt")
    db.session.execute(
        delete(Measurement)
        .where(Measurement.tank_id == tank.id)
        .where(Measurement.note.like(f"{_FIXTURE_NOTE_PREFIX}%"))
    )
    db.session.flush()
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=_parameter_type_or_500("salinity"),
        value=Decimal("34.8"),
        value_unit="ppt",
        recorded_at=_FIXED_VISUAL_NOW,
        source="manual",
        recorded_by_user_id=admin.id,
        note=f"{_FIXTURE_NOTE_PREFIX} measurement edit fixture",
    )
    db.session.commit()
    return measurement


def _delete_visual_animals() -> None:
    """Remove fixture-owned animal rows before recreating deterministic scenes."""
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent
    from safeharbor.services import upload_service

    fixture_animals = db.session.scalars(
        select(Animal).where(Animal.notes.like(f"{_FIXTURE_NOTE_PREFIX}%"))
    ).all()
    fixture_animal_ids = [animal.id for animal in fixture_animals]
    for animal in fixture_animals:
        if animal.image_path:
            upload_service.remove_image(entity_type="animals", entity_id=animal.id)

    if fixture_animal_ids:
        db.session.execute(delete(AnimalEvent).where(AnimalEvent.animal_id.in_(fixture_animal_ids)))
        db.session.execute(delete(Animal).where(Animal.id.in_(fixture_animal_ids)))
    db.session.flush()


def _seed_animals_list_scene(
    admin: User, *, include_tank_photo: bool = False, include_animal_photos: bool = False
) -> Any:
    """Seed 3 tanks with 5 alive animal rows and 2 tombstoned rows."""
    from safeharbor.services import animal_service

    reef = _seed_visual_reef_with_readings(admin, include_photo=include_tank_photo)
    planted = _ensure_visual_tank(admin, name="Planted 40", water_type="fresh")
    tide = _ensure_visual_tank(admin, name="Mangrove tide", water_type="brackish")
    _delete_visual_animals()

    marigold = animal_service.create_animal(
        name="Marigold",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
        sex="female",
        acquired_quantity=1,
        initial_tank=reef,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=120),
        initial_note="Settled into the reef after a short quarantine.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list marigold",
    )
    kelpie = animal_service.create_animal(
        name="Kelpie",
        species="Royal gramma",
        scientific_name="Gramma loreto",
        sex=None,
        acquired_quantity=1,
        initial_tank=reef,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=96),
        initial_note="Prefers the cavework under the center arch.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list kelpie",
    )
    hermits = animal_service.create_animal(
        name="Reef cleanup crew",
        species="Blue-leg hermit crab",
        scientific_name="Clibanarius tricolor",
        sex=None,
        acquired_quantity=5,
        initial_tank=reef,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=80),
        initial_note="Group acclimated together.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list hermits",
    )
    animal_service.mark_deceased(
        hermits,
        quantity=2,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=14),
        note="Two losses after a molt-heavy week.",
        recorded_by_user_id=admin.id,
    )
    pearl = animal_service.create_animal(
        name="Pearl",
        species="Nerite snail",
        scientific_name="Neritina natalensis",
        sex=None,
        acquired_quantity=1,
        initial_tank=tide,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=52),
        initial_note="Added to the mangrove glass cleanup rotation.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list pearl",
    )
    shrimp = animal_service.create_animal(
        name="Planted shrimp colony",
        species="Amano shrimp",
        scientific_name="Caridina multidentata",
        sex=None,
        acquired_quantity=4,
        initial_tank=planted,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=44),
        initial_note="Introduced after the moss bed filled in.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list shrimp",
    )
    animal_service.mark_deceased(
        shrimp,
        quantity=1,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=5),
        note="One missing after filter service.",
        recorded_by_user_id=admin.id,
    )
    cardinal = animal_service.create_animal(
        name="Atlas",
        species="Banggai cardinalfish",
        scientific_name="Pterapogon kauderni",
        sex="male",
        acquired_quantity=1,
        initial_tank=reef,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=210),
        initial_note="Legacy livestock record imported by hand.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list cardinal",
    )
    animal_service.mark_deceased(
        cardinal,
        quantity=1,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=30),
        note="Recorded as deceased after a prolonged decline.",
        recorded_by_user_id=admin.id,
    )
    firefish = animal_service.create_animal(
        name="Lumen",
        species="Firefish",
        scientific_name="Nemateleotris magnifica",
        sex=None,
        acquired_quantity=1,
        initial_tank=tide,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=160),
        initial_note="Kept in the brackish transition tank for observation.",
        recorded_by_user_id=admin.id,
        notes=f"{_FIXTURE_NOTE_PREFIX} animals-list firefish",
    )
    animal_service.mark_deceased(
        firefish,
        quantity=1,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=75),
        note="Tombstoned historical record.",
        recorded_by_user_id=admin.id,
    )
    if include_animal_photos:
        for animal in (marigold, kelpie, hermits, pearl, shrimp, cardinal, firefish):
            _attach_visual_animal_photo(animal)
    else:
        for animal in (marigold, kelpie, hermits, pearl, shrimp, cardinal, firefish):
            _clear_visual_animal_photo(animal)
    db.session.commit()
    return reef


def _seed_animal_detail_scene(admin: User, *, include_photo: bool = False) -> Any:
    """Seed one alive individual with four stable timeline events."""
    from safeharbor.models.animal_event import EventType
    from safeharbor.services import animal_service

    reef = _seed_visual_reef_with_readings(admin)
    planted = _ensure_visual_tank(admin, name="Planted 40", water_type="fresh")
    _delete_visual_animals()
    animal = animal_service.create_animal(
        name="Beacon",
        species="Yellow watchman goby",
        scientific_name="Cryptocentrus cinctus",
        sex="male",
        acquired_quantity=1,
        initial_tank=planted,
        acquired_at=_FIXED_VISUAL_NOW - timedelta(days=70),
        initial_note="Arrived alert and eating in quarantine.",
        recorded_by_user_id=admin.id,
        notes=(
            f"{_FIXTURE_NOTE_PREFIX} Pairs well with the pistol shrimp burrow near the front glass."
        ),
    )
    animal_service.move_animal(
        animal,
        to_tank=reef,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=45),
        note="Moved to the reef after stable salinity checks.",
        recorded_by_user_id=admin.id,
    )
    animal_service.record_event(
        animal,
        event_type=EventType.HEALTH_NOTE,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=21),
        note="Minor fin nick healed without intervention.",
        recorded_by_user_id=admin.id,
    )
    animal_service.record_event(
        animal,
        event_type=EventType.OBSERVATION,
        occurred_at=_FIXED_VISUAL_NOW - timedelta(days=3),
        note="Actively guarding the front burrow during feeding.",
        recorded_by_user_id=admin.id,
    )
    if include_photo:
        _attach_visual_animal_photo(animal)
    else:
        _clear_visual_animal_photo(animal)
    db.session.commit()
    return animal


@dev_bp.route("/dev/styleguide")
@public
def styleguide():  # type: ignore[no-untyped-def]
    """Render the design-system reference page. 404 in production."""
    if not _is_dev_or_test():
        abort(404)
    return render_template("dev/styleguide.html")


@dev_bp.route("/__test/visual-fixtures/login-as-admin", methods=["GET"])
@public
def visual_login_as_admin():  # type: ignore[no-untyped-def]
    """Test-only: ensure a known admin exists, log in via session, redirect to /admin/invites."""
    if not _is_dev_or_test():
        abort(404)
    admin = _ensure_visual_admin()
    _authenticate(admin)
    return redirect(url_for("auth.admin_invites"))


@dev_bp.route("/__test/visual-fixtures/invite-link", methods=["GET"])
@public
def visual_invite_link():  # type: ignore[no-untyped-def]
    """Test-only: ensure a fresh invite exists for visual-fixture@x.com,
    return a redirect to /register/<token>."""
    if not _is_dev_or_test():
        abort(404)
    from safeharbor.models.invite import Invite, InviteKind
    from safeharbor.services.auth_service import issue_invite_token

    admin = _ensure_visual_admin()

    # Drop any old fixture invites
    db.session.execute(delete(Invite).where(Invite.email == "visual-fixture@x.com"))
    db.session.commit()

    token, _ = issue_invite_token(
        email="visual-fixture@x.com", kind=InviteKind.INVITE, issued_by=admin.id
    )
    db.session.commit()
    return redirect(url_for("auth.register_with_token", token=token))


@dev_bp.route("/__test/visual-fixtures/seed-tanks", methods=["GET"])
@public
def visual_seed_tanks():  # type: ignore[no-untyped-def]
    """Test-only: idempotently seed three tanks (one per water type) and redirect to /tanks.

    Used by tests/visual/test_visual.py::test_tanks_list_light.
    """
    if not _is_dev_or_test():
        abort(404)
    from safeharbor.models.tank import Tank

    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    recorded_base = datetime.now(UTC)

    seeds = [
        ("Reef 90", "salt", "reef_sw", "healthy", _FIXED_VISUAL_NOW - timedelta(minutes=3)),
        ("Planted 40", "fresh", "planted_fw", "watch", _FIXED_VISUAL_NOW - timedelta(minutes=2)),
        (
            "Mangrove tide",
            "brackish",
            "brackish",
            "unhealthy",
            _FIXED_VISUAL_NOW - timedelta(minutes=1),
        ),
    ]
    for name, water_type, profile_key, expected_rollup, created_at in seeds:
        existing = db.session.scalar(
            select(Tank).where(Tank.name == name, Tank.created_by_user_id == admin.id)
        )
        if existing is None:
            existing = Tank(
                name=name,
                water_type=water_type,
                profile_key=profile_key,
                created_by_user_id=admin.id,
            )
            db.session.add(existing)
            db.session.flush()
        existing.water_type = water_type
        existing.profile_key = profile_key
        existing.volume_liters = None
        existing.setup_date = None
        existing.substrate = None
        existing.equipment_notes = None
        existing.created_at = created_at
        existing.updated_at = created_at
        existing.decommission_date = None
        _clear_visual_tank_photo(existing, admin)
        _refresh_visual_tank_health_measurements(
            existing,
            admin,
            expected_rollup=expected_rollup,
            recorded_base=recorded_base,
        )
    _set_visual_active_tanks(admin, {"Reef 90", "Planted 40", "Mangrove tide"})
    return redirect(url_for("tanks.list_tanks"))


@dev_bp.route("/__test/visual-fixtures/seed-tank-detail", methods=["GET"])
@public
def visual_seed_tank_detail():  # type: ignore[no-untyped-def]
    """Test-only: seed a tank with live readings and redirect to its detail page.

    Used by tests/visual/test_visual.py::test_tank_detail_light to capture the
    tank-detail page with data-bearing KPI, Recent, and chart states.
    """
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _seed_visual_reef_with_readings(admin)
    _seed_animals_list_scene(admin)
    _set_visual_active_tanks(admin, {"Visual Reef", "Planted 40", "Mangrove tide"})
    return redirect(url_for("tanks.detail", tank_id=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-tank-with-photo", methods=["GET"])
@public
def visual_seed_tank_with_photo():  # type: ignore[no-untyped-def]
    """Test-only: seed a photo-bearing tank detail scene and redirect to it."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _seed_animals_list_scene(admin, include_tank_photo=True)
    _set_visual_active_tanks(admin, {"Visual Reef", "Planted 40", "Mangrove tide"})
    return redirect(url_for("tanks.detail", tank_id=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-animals-list", methods=["GET"])
@public
def visual_seed_animals_list():  # type: ignore[no-untyped-def]
    """Test-only: seed an animals list scene and redirect to /animals."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    _seed_animals_list_scene(admin)
    _set_visual_active_tanks(admin, {"Visual Reef", "Planted 40", "Mangrove tide"})
    return redirect(url_for("animals.list_animals"))


@dev_bp.route("/__test/visual-fixtures/seed-animal-detail", methods=["GET"])
@public
def visual_seed_animal_detail():  # type: ignore[no-untyped-def]
    """Test-only: seed a single-animal timeline scene and redirect to detail."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    animal = _seed_animal_detail_scene(admin)
    _set_visual_active_tanks(admin, {"Visual Reef", "Planted 40"})
    return redirect(url_for("animals.detail_animal", animal_id=animal.id))


@dev_bp.route("/__test/visual-fixtures/seed-animal-with-photo", methods=["GET"])
@public
def visual_seed_animal_with_photo():  # type: ignore[no-untyped-def]
    """Test-only: seed a photo-bearing animal detail scene and redirect to it."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    animal = _seed_animal_detail_scene(admin, include_photo=True)
    _set_visual_active_tanks(admin, {"Visual Reef", "Planted 40"})
    return redirect(url_for("animals.detail_animal", animal_id=animal.id))


@dev_bp.route("/__test/visual-fixtures/seed-home-dashboard", methods=["GET"])
@public
def visual_seed_home_dashboard():  # type: ignore[no-untyped-def]
    """Test-only: seed dashboard data and redirect to home."""
    if not _is_dev_or_test():
        abort(404)

    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    _seed_visual_reef_with_readings(admin)
    _set_visual_active_tanks(admin, {"Visual Reef"})
    return redirect(url_for("home.index"))


@dev_bp.route("/__test/visual-fixtures/seed-settings-system-admin", methods=["GET"])
@public
def visual_seed_settings_system_admin():  # type: ignore[no-untyped-def]
    """Test-only: ensure visual admin has system privileges and redirect to settings."""
    if not _is_dev_or_test():
        abort(404)
    admin = _ensure_visual_admin()
    admin.is_superuser = True
    db.session.commit()
    _authenticate(admin)
    return redirect(url_for("settings.system"))


@dev_bp.route("/__test/visual-fixtures/seed-quick-add", methods=["GET"])
@public
def visual_seed_quick_add():  # type: ignore[no-untyped-def]
    """Test-only: seed admin + saltwater tank and redirect to quick-add."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _ensure_visual_tank(admin, name="Visual Reef", water_type="salt")
    _set_visual_active_tanks(admin, {"Visual Reef"})
    return redirect(url_for("measurements.quick_add_get", tank=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-batch-entry", methods=["GET"])
@public
def visual_seed_batch_entry():  # type: ignore[no-untyped-def]
    """Test-only: seed admin + saltwater tank and redirect to batch entry."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _ensure_visual_tank(admin, name="Visual Reef", water_type="salt")
    _set_visual_active_tanks(admin, {"Visual Reef"})
    return redirect(url_for("measurements.batch_get", tank=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-history-with-data", methods=["GET"])
@public
def visual_seed_history_with_data():  # type: ignore[no-untyped-def]
    """Test-only: seed a tank with 30 readings and redirect to history."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _ensure_visual_tank(admin, name="Visual Reef", water_type="salt")
    _refresh_visual_measurements(
        tank,
        admin,
        _history_rows(),
    )
    _set_visual_active_tanks(admin, {"Visual Reef"})
    return redirect(url_for("tanks.history", tank_id=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-history-with-badges-and-attribution", methods=["GET"])
@public
def visual_seed_history_with_badges_and_attribution():  # type: ignore[no-untyped-def]
    """Test-only: seed history rows with range badges and recorder attribution."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    tank = _seed_history_with_badges_and_attribution(admin)
    _set_visual_active_tanks(admin, {"Badge History Reef"})
    return redirect(url_for("tanks.history", tank_id=tank.id))


@dev_bp.route("/__test/visual-fixtures/seed-measurement-edit", methods=["GET"])
@public
def visual_seed_measurement_edit():  # type: ignore[no-untyped-def]
    """Test-only: seed one reading and redirect to its edit form."""
    if not _is_dev_or_test():
        abort(404)
    _ensure_reference_data()
    admin = _ensure_visual_admin()
    _authenticate(admin)
    measurement = _seed_measurement_edit_scene(admin)
    _set_visual_active_tanks(admin, {"Edit Fixture Reef"})
    return redirect(url_for("measurements.edit_get", measurement_id=measurement.id))
