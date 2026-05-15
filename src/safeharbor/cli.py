"""Custom Flask CLI commands.

Phase 0 ships an empty group; subsequent phases add `seed`, `import-csv`, etc.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import click
from flask import Flask
from flask.cli import AppGroup

_BACKUP_FILENAME_RE = re.compile(r"^safeharbor-backup-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.tar$")


def _parse_database_url(uri: str) -> tuple[str, int, str, str, str]:
    """Parse a PostgreSQL database URL into pg_dump connection pieces."""
    normalized = uri.replace("postgresql+psycopg", "postgresql", 1)
    parsed = urlparse(normalized)

    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise ValueError("Malformed PostgreSQL database URL") from exc

    dbname = unquote(parsed.path.removeprefix("/"))
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname is None
        or parsed.username is None
        or parsed.password is None
        or not dbname
    ):
        raise ValueError("Malformed PostgreSQL database URL")

    return parsed.hostname, port, unquote(parsed.username), unquote(parsed.password), dbname


def _apply_retention(backup_dir: Path, daily: int, weekly: int) -> list[Path]:
    """Delete backups outside the daily plus weekly retention windows."""
    backups = sorted(
        (
            path
            for path in backup_dir.glob("safeharbor-backup-*.tar")
            if _BACKUP_FILENAME_RE.match(path.name)
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    kept = set(backups[:daily])
    weekly_keys: set[tuple[int, int]] = set()
    for backup in backups:
        if len(weekly_keys) >= weekly:
            break
        week_key = datetime.fromtimestamp(
            backup.stat().st_mtime,
            tz=UTC,
        ).isocalendar()[:2]
        if week_key in weekly_keys:
            continue
        weekly_keys.add(week_key)
        kept.add(backup)

    deleted = []
    for backup in backups:
        if backup in kept:
            continue
        backup.unlink()
        deleted.append(backup)
    return deleted


def _default_output_path() -> str:
    """Return the default backup archive path under /backups."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"/backups/safeharbor-backup-{timestamp}.tar"


def _validate_tarball_structure(path: str) -> int:
    """Validate that a restore archive contains a database dump and uploads."""
    try:
        with tarfile.open(path, "r") as tf:
            members = tf.getmembers()
    except tarfile.TarError as exc:
        raise click.ClickException(f"Restore archive is not a readable tarball: {path}") from exc

    has_db_dump = any(member.name == "db.dump" for member in members)
    upload_file_count = sum(
        1 for member in members if member.name.startswith("uploads/") and member.isfile()
    )
    has_uploads = any(
        member.name == "uploads" or member.name.startswith("uploads/") for member in members
    )

    if not has_db_dump:
        raise click.ClickException("Restore archive is missing required db.dump member")
    if not has_uploads:
        raise click.ClickException("Restore archive is missing required uploads/ member")

    return upload_file_count


safeharbor_cli = AppGroup("safeharbor", help="Safe Harbor management commands.")


@safeharbor_cli.command("backup")
@click.option(
    "--output",
    default=None,
    type=str,
    help="Output tarball path (default: /backups/safeharbor-backup-<UTC>.tar)",
)
def backup_cmd(output: str | None) -> None:
    """Create a database and uploads backup tarball."""
    from flask import current_app

    try:
        retention_daily = int(os.environ.get("BACKUP_RETENTION_DAILY", "7"))
        retention_weekly = int(os.environ.get("BACKUP_RETENTION_WEEKLY", "4"))
    except ValueError as exc:
        raise click.BadParameter(
            "BACKUP_RETENTION_* must be non-negative integers: " + str(exc)
        ) from exc
    if retention_daily < 0 or retention_weekly < 0:
        raise click.BadParameter("BACKUP_RETENTION_* must be non-negative")

    output_path = output or _default_output_path()
    click.echo(f"writing to {output_path}")

    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    host, port, user, password, dbname = _parse_database_url(uri)
    upload_dir = Path(current_app.config["UPLOAD_DIR"])

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        subprocess.run(
            [
                "pg_dump",
                "-F",
                "c",
                "-h",
                host,
                "-p",
                str(port),
                "-U",
                user,
                "-d",
                dbname,
                "-f",
                str(td_path / "db.dump"),
            ],
            env={**os.environ, "PGPASSWORD": password},
            check=True,
        )

        with tarfile.open(f"{output_path}.tmp", "w") as tf:
            tf.add(str(td_path / "db.dump"), arcname="db.dump")
            if upload_dir.exists():
                tf.add(str(upload_dir), arcname="uploads")

        os.replace(f"{output_path}.tmp", output_path)

    deleted = _apply_retention(
        Path(output_path).parent,
        retention_daily,
        retention_weekly,
    )
    if deleted:
        click.echo(f"pruned {len(deleted)} old tarballs")

    click.echo(f"wrote {output_path} ({Path(output_path).stat().st_size} bytes)")


@safeharbor_cli.command("restore")
@click.option("--from", "from_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--yes", is_flag=True, default=False)
def restore_cmd(from_path: str, dry_run: bool, yes: bool) -> None:
    """Restore the database and uploads from a backup tarball."""
    from flask import current_app

    upload_file_count = _validate_tarball_structure(from_path)

    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(from_path, "r") as tf:
            tf.extractall(td, filter="data")

        dump_path = f"{td}/db.dump"
        result = subprocess.run(
            ["pg_restore", "--list", dump_path],
            check=True,
            capture_output=True,
            text=True,
        )
        table_count = result.stdout.count(" TABLE ")
        if dry_run:
            click.echo(
                f"would restore {table_count} tables, {upload_file_count} upload files "
                f"(total {Path(from_path).stat().st_size} bytes) from {from_path}"
            )
            return

        if not yes:
            confirmation = click.prompt(
                "Type 'restore' to confirm — this WILL OVERWRITE the database and uploads",
                type=str,
                default="",
                show_default=False,
            )
            if confirmation != "restore":
                click.echo("aborted", err=True)
                raise click.exceptions.Exit(code=1)

        host, port, user, password, dbname = _parse_database_url(
            current_app.config["SQLALCHEMY_DATABASE_URI"]
        )
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "-h",
                host,
                "-p",
                str(port),
                "-U",
                user,
                "-d",
                dbname,
                dump_path,
            ],
            env={**os.environ, "PGPASSWORD": password},
            check=True,
        )

        upload_dir = Path(current_app.config["UPLOAD_DIR"])
        for entry in upload_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        shutil.copytree(f"{td}/uploads", upload_dir, dirs_exist_ok=True)

    click.echo(
        f"restored {table_count} tables and {upload_file_count} upload files from {from_path}"
    )


@safeharbor_cli.command("hello")
def hello() -> None:
    """Smoke-test command: prints 'hello'."""
    click.echo("hello")


@safeharbor_cli.command("build-css")
def build_css() -> None:
    """Compile src/safeharbor/static/scss/app.scss → static/css/app.css.

    Bundles tokens + Bootstrap overrides + selected Bootstrap modules +
    custom components. Output is committed to the repo so deployment
    doesn't need a Sass toolchain.
    """
    from pathlib import Path

    import sass  # type: ignore[import-untyped,unused-ignore]

    pkg_dir = Path(__file__).parent
    scss_dir = pkg_dir / "static" / "scss"
    css_dir = pkg_dir / "static" / "css"
    css_dir.mkdir(parents=True, exist_ok=True)

    css = sass.compile(
        filename=str(scss_dir / "app.scss"),
        include_paths=[str(scss_dir)],
        output_style="compressed",
    )
    out = css_dir / "app.css"
    out.write_text(css)
    click.echo(f"wrote {out} ({len(css):,} bytes)")


@safeharbor_cli.command("create-admin")
def create_admin() -> None:
    """Create the first superuser. Refuses to run after any user exists."""
    from sqlalchemy import select

    from safeharbor.extensions import db
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import create_first_admin

    if db.session.scalar(select(User).limit(1)) is not None:
        click.echo(
            "Refusing: a user already exists. Use the web admin invite flow at /admin/invites.",
            err=True,
        )
        raise click.exceptions.Exit(code=1)

    email = click.prompt("Email", type=str)
    password = click.prompt("Password", type=str, hide_input=True)
    confirm = click.prompt("Confirm password", type=str, hide_input=True)
    preferred_units = click.prompt(
        "Unit system",
        type=click.Choice(["imperial", "metric"], case_sensitive=False),
        default="imperial",
        show_default=True,
    )

    if password != confirm:
        click.echo("Passwords do not match.", err=True)
        raise click.exceptions.Exit(code=1)
    if len(password) < 10:
        click.echo("Password must be at least 10 characters.", err=True)
        raise click.exceptions.Exit(code=1)

    try:
        u = create_first_admin(email, password, preferred_units)
    except ValueError:
        click.echo(
            "Refusing: a user already exists. Use the web admin invite flow at /admin/invites.",
            err=True,
        )
        raise click.exceptions.Exit(code=1) from None

    db.session.commit()
    click.echo(f"Created superuser {u.email} (id: {u.id})")


@safeharbor_cli.command("reset-password")
@click.argument("email")
def reset_password(email: str) -> None:
    """Set a new password for an existing user. Recovery hatch when the
    only superuser has lost their password."""
    from sqlalchemy import select

    from safeharbor.extensions import db
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = db.session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        click.echo(f"No user with email {email}.", err=True)
        raise click.exceptions.Exit(code=1)

    new = click.prompt("New password", type=str, hide_input=True)
    confirm = click.prompt("Confirm password", type=str, hide_input=True)
    if new != confirm:
        click.echo("Passwords do not match.", err=True)
        raise click.exceptions.Exit(code=1)
    if len(new) < 10:
        click.echo("Password must be at least 10 characters.", err=True)
        raise click.exceptions.Exit(code=1)

    user.password_hash = hash_password(new)
    db.session.commit()
    click.echo(f"Password updated for {user.email}")


# ──────────────────────────────────────────────────────────────────────────
# Phase 1c.2: idempotent reference-data seed.
# ──────────────────────────────────────────────────────────────────────────

# (code, display, dimension)
_SEED_UNITS: list[tuple[str, str, str]] = [
    ("degC", "°C", "temperature"),
    ("degF", "°F", "temperature"),
    ("ppt", "ppt", "salinity"),
    ("sg", "SG", "salinity"),
    ("ppm", "ppm", "concentration"),
    ("mg_per_l", "mg/L", "concentration"),
    ("dKH", "dKH", "alkalinity"),
    ("dGH", "dGH", "hardness"),
    ("pH", "pH", "dimensionless"),
]

# (key, display_name, canonical_unit_code, applies_to_water_type, display_order)
_SEED_PARAMETER_TYPES: list[tuple[str, str, str, str | None, int]] = [
    ("temperature", "Temperature", "degC", None, 10),
    ("ph", "pH", "pH", None, 20),
    ("salinity", "Salinity", "ppt", None, 30),  # UI hides on freshwater
    ("ammonia", "Ammonia (NH₃)", "ppm", None, 40),
    ("nitrite", "Nitrite (NO₂⁻)", "ppm", None, 50),
    ("nitrate", "Nitrate (NO₃⁻)", "ppm", None, 60),
    ("phosphate", "Phosphate (PO₄³⁻)", "ppm", None, 70),
    ("kh", "KH", "dKH", None, 80),
    ("gh", "GH", "dGH", None, 90),  # UI hides on saltwater
    ("calcium", "Calcium", "ppm", "salt", 100),
    ("magnesium", "Magnesium", "ppm", "salt", 110),
]

# (parameter_key, water_type, profile_key, min_value, max_value, source, stale_after_days)
_SEED_PARAMETER_RANGES: list[tuple[str, str, str, str, str, str, int]] = [
    (
        "temperature",
        "fresh",
        "tropical_fw_community",
        "22.0",
        "28.0",
        "Safe Harbor tropical freshwater preset",
        7,
    ),
    (
        "ph",
        "fresh",
        "tropical_fw_community",
        "6.5",
        "7.5",
        "Safe Harbor tropical freshwater preset",
        7,
    ),
    (
        "ammonia",
        "fresh",
        "tropical_fw_community",
        "0",
        "0.25",
        "Safe Harbor tropical freshwater preset",
        7,
    ),
    (
        "nitrite",
        "fresh",
        "tropical_fw_community",
        "0",
        "0.25",
        "Safe Harbor tropical freshwater preset",
        7,
    ),
    (
        "nitrate",
        "fresh",
        "tropical_fw_community",
        "0",
        "40.0",
        "Safe Harbor tropical freshwater preset",
        14,
    ),
    (
        "phosphate",
        "fresh",
        "tropical_fw_community",
        "0",
        "0.5",
        "Safe Harbor tropical freshwater preset",
        14,
    ),
    (
        "kh",
        "fresh",
        "tropical_fw_community",
        "4.0",
        "8.0",
        "Safe Harbor tropical freshwater preset",
        30,
    ),
    (
        "gh",
        "fresh",
        "tropical_fw_community",
        "4.0",
        "12.0",
        "Safe Harbor tropical freshwater preset",
        30,
    ),
    (
        "temperature",
        "fresh",
        "coldwater_fw",
        "18.3",
        "22.2",
        "Safe Harbor coldwater freshwater preset",
        7,
    ),
    ("ph", "fresh", "coldwater_fw", "6.8", "7.6", "Safe Harbor coldwater freshwater preset", 7),
    ("ammonia", "fresh", "coldwater_fw", "0", "0.25", "Safe Harbor coldwater freshwater preset", 7),
    ("nitrite", "fresh", "coldwater_fw", "0", "0.25", "Safe Harbor coldwater freshwater preset", 7),
    (
        "nitrate",
        "fresh",
        "coldwater_fw",
        "0",
        "20.0",
        "Safe Harbor coldwater freshwater preset",
        14,
    ),
    (
        "phosphate",
        "fresh",
        "coldwater_fw",
        "0",
        "0.5",
        "Safe Harbor coldwater freshwater preset",
        14,
    ),
    ("kh", "fresh", "coldwater_fw", "4.0", "10.0", "Safe Harbor coldwater freshwater preset", 30),
    ("gh", "fresh", "coldwater_fw", "6.0", "14.0", "Safe Harbor coldwater freshwater preset", 30),
    (
        "temperature",
        "fresh",
        "planted_fw",
        "22.2",
        "25.6",
        "Safe Harbor planted freshwater preset",
        7,
    ),
    ("ph", "fresh", "planted_fw", "6.5", "7.2", "Safe Harbor planted freshwater preset", 7),
    ("ammonia", "fresh", "planted_fw", "0", "0.25", "Safe Harbor planted freshwater preset", 7),
    ("nitrite", "fresh", "planted_fw", "0", "0.25", "Safe Harbor planted freshwater preset", 7),
    ("nitrate", "fresh", "planted_fw", "0", "20.0", "Safe Harbor planted freshwater preset", 14),
    ("phosphate", "fresh", "planted_fw", "0", "0.5", "Safe Harbor planted freshwater preset", 14),
    ("kh", "fresh", "planted_fw", "3.0", "8.0", "Safe Harbor planted freshwater preset", 30),
    ("gh", "fresh", "planted_fw", "3.0", "10.0", "Safe Harbor planted freshwater preset", 30),
    ("temperature", "salt", "reef_sw", "24.4", "26.7", "Safe Harbor reef saltwater preset", 7),
    ("ph", "salt", "reef_sw", "8.1", "8.4", "Safe Harbor reef saltwater preset", 7),
    ("salinity", "salt", "reef_sw", "33.0", "35.0", "Safe Harbor reef saltwater preset", 7),
    ("ammonia", "salt", "reef_sw", "0", "0.05", "Safe Harbor reef saltwater preset", 7),
    ("nitrite", "salt", "reef_sw", "0", "0.05", "Safe Harbor reef saltwater preset", 7),
    ("nitrate", "salt", "reef_sw", "0", "5.0", "Safe Harbor reef saltwater preset", 14),
    ("phosphate", "salt", "reef_sw", "0", "0.05", "Safe Harbor reef saltwater preset", 14),
    ("kh", "salt", "reef_sw", "8.0", "11.0", "Safe Harbor reef saltwater preset", 30),
    ("calcium", "salt", "reef_sw", "380", "450", "Safe Harbor reef saltwater preset", 30),
    ("magnesium", "salt", "reef_sw", "1280", "1350", "Safe Harbor reef saltwater preset", 30),
    ("temperature", "salt", "fowlr_sw", "24.4", "26.7", "Safe Harbor FOWLR saltwater preset", 7),
    ("ph", "salt", "fowlr_sw", "8.0", "8.4", "Safe Harbor FOWLR saltwater preset", 7),
    ("salinity", "salt", "fowlr_sw", "30.0", "35.0", "Safe Harbor FOWLR saltwater preset", 7),
    ("ammonia", "salt", "fowlr_sw", "0", "0.1", "Safe Harbor FOWLR saltwater preset", 7),
    ("nitrite", "salt", "fowlr_sw", "0", "0.1", "Safe Harbor FOWLR saltwater preset", 7),
    ("nitrate", "salt", "fowlr_sw", "0", "30.0", "Safe Harbor FOWLR saltwater preset", 14),
    ("phosphate", "salt", "fowlr_sw", "0", "0.5", "Safe Harbor FOWLR saltwater preset", 14),
    ("kh", "salt", "fowlr_sw", "7.0", "11.0", "Safe Harbor FOWLR saltwater preset", 30),
    ("calcium", "salt", "fowlr_sw", "350", "480", "Safe Harbor FOWLR saltwater preset", 30),
    ("magnesium", "salt", "fowlr_sw", "1150", "1400", "Safe Harbor FOWLR saltwater preset", 30),
    ("temperature", "brackish", "brackish", "23.9", "26.7", "Safe Harbor brackish preset", 7),
    ("ph", "brackish", "brackish", "7.4", "8.2", "Safe Harbor brackish preset", 7),
    ("salinity", "brackish", "brackish", "5.0", "15.0", "Safe Harbor brackish preset", 7),
    ("ammonia", "brackish", "brackish", "0", "0.25", "Safe Harbor brackish preset", 7),
    ("nitrite", "brackish", "brackish", "0", "0.25", "Safe Harbor brackish preset", 7),
    ("nitrate", "brackish", "brackish", "0", "30.0", "Safe Harbor brackish preset", 14),
    ("phosphate", "brackish", "brackish", "0", "0.5", "Safe Harbor brackish preset", 14),
    ("kh", "brackish", "brackish", "6.0", "12.0", "Safe Harbor brackish preset", 30),
    ("gh", "brackish", "brackish", "8.0", "18.0", "Safe Harbor brackish preset", 30),
]


@safeharbor_cli.command("seed")
def seed() -> None:
    """Idempotently seed units, parameter_types, parameter_ranges.

    Re-running is safe — existing rows (matched by natural key) are skipped.
    """
    from decimal import Decimal

    from sqlalchemy import select

    from safeharbor.extensions import db
    from safeharbor.models.parameter_range import ParameterRange
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.unit import Unit

    units_created = 0
    units_skipped = 0
    for code, display, dimension in _SEED_UNITS:
        if db.session.scalar(select(Unit).where(Unit.code == code)) is None:
            db.session.add(Unit(code=code, display=display, dimension=dimension))
            units_created += 1
        else:
            units_skipped += 1
    db.session.commit()

    pts_created = 0
    pts_skipped = 0
    for key, display_name, unit_code, applies_to, order in _SEED_PARAMETER_TYPES:
        if db.session.scalar(select(ParameterType).where(ParameterType.key == key)) is not None:
            pts_skipped += 1
            continue
        unit = db.session.scalar(select(Unit).where(Unit.code == unit_code))
        if unit is None:
            click.echo(f"warn: canonical unit {unit_code!r} missing for {key!r}", err=True)
            continue
        db.session.add(
            ParameterType(
                key=key,
                display_name=display_name,
                canonical_unit_id=unit.id,
                applies_to_water_type=applies_to,
                display_order=order,
            )
        )
        pts_created += 1
    db.session.commit()

    ranges_created = 0
    ranges_skipped = 0
    for (
        param_key,
        water_type,
        profile_key,
        lo,
        hi,
        source,
        stale_after_days,
    ) in _SEED_PARAMETER_RANGES:
        pt = db.session.scalar(select(ParameterType).where(ParameterType.key == param_key))
        if pt is None:
            click.echo(f"warn: parameter_type {param_key!r} missing", err=True)
            continue
        existing = db.session.scalar(
            select(ParameterRange)
            .where(ParameterRange.parameter_type_id == pt.id)
            .where(ParameterRange.water_type == water_type)
            .where(ParameterRange.profile_key == profile_key)
        )
        if existing is not None:
            if existing.stale_after_days != stale_after_days:
                click.echo(
                    "warn: parameter_range "
                    f"{param_key!r}/{water_type!r}/{profile_key!r} has stale_after_days "
                    f"{existing.stale_after_days}, expected {stale_after_days}; "
                    "leaving existing row unchanged",
                    err=True,
                )
            ranges_skipped += 1
            continue
        db.session.add(
            ParameterRange(
                parameter_type_id=pt.id,
                water_type=water_type,
                profile_key=profile_key,
                min_value=Decimal(lo),
                max_value=Decimal(hi),
                stale_after_days=stale_after_days,
                source=source,
            )
        )
        ranges_created += 1
    db.session.commit()

    click.echo(
        f"Seeded {units_created} units, {pts_created} parameter_types, "
        f"{ranges_created} parameter_ranges "
        f"(skipped {units_skipped + pts_skipped + ranges_skipped} already-present rows)."
    )


def register_cli(app: Flask) -> None:
    app.cli.add_command(safeharbor_cli)
