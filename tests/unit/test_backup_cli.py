"""Backup CLI helper coverage."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from safeharbor.cli import _apply_retention, _default_output_path, _parse_database_url


def _create_backup(tmp_path: Path, dt: datetime) -> Path:
    path = tmp_path / f"safeharbor-backup-{dt.strftime('%Y-%m-%dT%H-%M-%SZ')}.tar"
    path.write_text("backup")
    timestamp = dt.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def test_parse_database_url_extracts_components() -> None:
    result = _parse_database_url("postgresql+psycopg://safeharbor:secret@db:5432/safeharbor")

    assert result == ("db", 5432, "safeharbor", "secret", "safeharbor")


def test_parse_database_url_handles_default_port_and_decodes_pieces() -> None:
    result = _parse_database_url("postgresql+psycopg://safe%20harbor:s%40cr%2Fet@db/safe%20harbor")

    assert result == ("db", 5432, "safe harbor", "s@cr/et", "safe harbor")


def test_retention_keeps_most_recent_daily(tmp_path: Path) -> None:
    base = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    backups = [_create_backup(tmp_path, base - timedelta(days=index)) for index in range(10)]
    expected = set(backups[:7])

    _apply_retention(tmp_path, daily=7, weekly=0)

    remaining = set(tmp_path.glob("safeharbor-backup-*.tar"))
    assert remaining == expected
    assert len(remaining) == 7


def test_retention_keeps_one_per_iso_week(tmp_path: Path) -> None:
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    backups = [_create_backup(tmp_path, base - timedelta(weeks=index)) for index in range(5)]
    expected = set(backups[:4])

    _apply_retention(tmp_path, daily=0, weekly=4)

    remaining = set(tmp_path.glob("safeharbor-backup-*.tar"))
    assert remaining == expected
    assert len(remaining) == 4


def test_retention_set_union_dedupes(tmp_path: Path) -> None:
    base = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    backups = [_create_backup(tmp_path, base - timedelta(days=index)) for index in range(14)]
    daily_kept = set(backups[:7])
    weekly_kept: set[Path] = set()
    seen_weeks: set[tuple[int, int]] = set()
    for backup in backups:
        week = datetime.fromtimestamp(backup.stat().st_mtime, tz=UTC).isocalendar()[:2]
        if week in seen_weeks:
            continue
        seen_weeks.add(week)
        weekly_kept.add(backup)
        if len(seen_weeks) == 3:
            break
    expected = daily_kept | weekly_kept

    _apply_retention(tmp_path, daily=7, weekly=3)

    remaining = set(tmp_path.glob("safeharbor-backup-*.tar"))
    assert remaining == expected
    assert len(remaining) == len(expected)


def test_default_output_path_format() -> None:
    assert re.match(
        r"^/backups/safeharbor-backup-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.tar$",
        _default_output_path(),
    )
