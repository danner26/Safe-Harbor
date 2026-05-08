"""Entrypoint coverage for pre-upgrade backup behavior."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ENTRYPOINT = Path("docker/docker-entrypoint.sh")
FLASK_APP_COMMAND = "--app safeharbor.wsgi:app"
DB_CURRENT_COMMAND = f"{FLASK_APP_COMMAND} db current"
DB_HEADS_COMMAND = f"{FLASK_APP_COMMAND} db heads"
DB_UPGRADE_COMMAND = f"{FLASK_APP_COMMAND} db upgrade -d migrations"
SEED_COMMAND = f"{FLASK_APP_COMMAND} safeharbor seed"
BACKUP_COMMAND_PREFIX = (
    f"{FLASK_APP_COMMAND} safeharbor backup --output /backups/pre-upgrade-"
)


def _write_fake_flask(bin_dir: Path) -> Path:
    flask_path = bin_dir / "flask"
    flask_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

record() {
  printf '%s\\n' "$*" >> "${FAKE_FLASK_LOG}"
}

record "$*"

if [[ "$*" == "--app safeharbor.wsgi:app db current" ]]; then
  printf '%s\\n' "${FAKE_DB_CURRENT:-}"
  exit 0
fi

if [[ "$*" == "--app safeharbor.wsgi:app db heads" ]]; then
  printf '%s\\n' "${FAKE_DB_HEADS:-}"
  exit 0
fi

if [[ "$*" == "--app safeharbor.wsgi:app safeharbor backup --output /backups/pre-upgrade-"* ]]; then
  if [[ "${FAKE_BACKUP_FAIL:-0}" == "1" ]]; then
    exit 42
  fi
  output=""
  previous=""
  for arg in "$@"; do
    if [[ "$previous" == "--output" ]]; then
      output="$arg"
      break
    fi
    previous="$arg"
  done
  if [[ -z "$output" ]]; then
    exit 43
  fi
  printf '%s\\n' "$output" > "${FAKE_BACKUP_DIR}/requested-output.txt"
  printf 'fake backup\\n' > "${FAKE_BACKUP_DIR}/$(basename "$output")"
  exit 0
fi

if [[ "$*" == "--app safeharbor.wsgi:app db upgrade -d migrations" ]]; then
  printf 'upgrade-ran\\n' > "${FAKE_UPGRADE_MARKER}"
  exit 0
fi

if [[ "$*" == "--app safeharbor.wsgi:app safeharbor seed" ]]; then
  exit 0
fi

exit 44
""",
        encoding="utf-8",
    )
    flask_path.chmod(flask_path.stat().st_mode | stat.S_IXUSR)
    return flask_path


def _write_fake_gunicorn(bin_dir: Path) -> Path:
    gunicorn_path = bin_dir / "gunicorn"
    gunicorn_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

printf '%s\\n' "$*" > "${FAKE_GUNICORN_LOG}"
""",
        encoding="utf-8",
    )
    gunicorn_path.chmod(gunicorn_path.stat().st_mode | stat.S_IXUSR)
    return gunicorn_path


def _run_entrypoint(
    tmp_path: Path,
    *,
    current: str,
    heads: str = "headrev",
    backup_fails: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bin_dir = tmp_path / "bin"
    backup_dir = tmp_path / "backups"
    bin_dir.mkdir()
    backup_dir.mkdir()
    _write_fake_flask(bin_dir)
    _write_fake_gunicorn(bin_dir)

    log_path = tmp_path / "flask.log"
    upgrade_marker = tmp_path / "upgrade-ran"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_BACKUP_DIR": str(backup_dir),
        "FAKE_BACKUP_FAIL": "1" if backup_fails else "0",
        "FAKE_DB_CURRENT": current,
        "FAKE_DB_HEADS": heads,
        "FAKE_FLASK_LOG": str(log_path),
        "FAKE_GUNICORN_LOG": str(tmp_path / "gunicorn.log"),
        "FAKE_UPGRADE_MARKER": str(upgrade_marker),
    }

    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "gunicorn", "--check-config"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    return result, backup_dir, upgrade_marker


def _log_lines(tmp_path: Path) -> list[str]:
    return (tmp_path / "flask.log").read_text(encoding="utf-8").splitlines()


def _command_index(log_lines: list[str], command: str) -> int:
    assert command in log_lines
    return log_lines.index(command)


def _backup_command_index(log_lines: list[str]) -> int:
    matches = [
        index
        for index, line in enumerate(log_lines)
        if line.startswith(BACKUP_COMMAND_PREFIX) and line.endswith(".tar.gz")
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_core_flask_commands_ran(log_lines: list[str]) -> None:
    _command_index(log_lines, DB_CURRENT_COMMAND)
    _command_index(log_lines, DB_HEADS_COMMAND)
    _command_index(log_lines, DB_UPGRADE_COMMAND)
    _command_index(log_lines, SEED_COMMAND)


def _assert_backup_before_upgrade(log_lines: list[str]) -> None:
    assert _backup_command_index(log_lines) < _command_index(
        log_lines, DB_UPGRADE_COMMAND
    )


def _assert_no_backup_command(log_lines: list[str]) -> None:
    assert not any(line.startswith(BACKUP_COMMAND_PREFIX) for line in log_lines)


def test_pending_migrations_create_pre_upgrade_backup(tmp_path: Path) -> None:
    result, backup_dir, upgrade_marker = _run_entrypoint(
        tmp_path, current="oldrev", heads="headrev"
    )

    assert result.returncode == 0, result.stderr
    requested_output = (backup_dir / "requested-output.txt").read_text(
        encoding="utf-8"
    )
    assert requested_output.startswith("/backups/pre-upgrade-")
    assert requested_output.endswith(".tar.gz\n")
    assert (backup_dir / Path(requested_output.strip()).name).read_text(
        encoding="utf-8"
    ) == "fake backup\n"
    assert upgrade_marker.read_text(encoding="utf-8") == "upgrade-ran\n"
    log_lines = _log_lines(tmp_path)
    _assert_core_flask_commands_ran(log_lines)
    _assert_backup_before_upgrade(log_lines)


def test_current_revision_at_heads_skips_pre_upgrade_backup(tmp_path: Path) -> None:
    result, backup_dir, upgrade_marker = _run_entrypoint(
        tmp_path, current="headrev", heads="headrev"
    )

    assert result.returncode == 0, result.stderr
    assert (backup_dir / "requested-output.txt").exists() is False
    assert upgrade_marker.read_text(encoding="utf-8") == "upgrade-ran\n"
    log_lines = _log_lines(tmp_path)
    _assert_core_flask_commands_ran(log_lines)
    _assert_no_backup_command(log_lines)


def test_empty_current_revision_skips_pre_upgrade_backup(tmp_path: Path) -> None:
    result, backup_dir, upgrade_marker = _run_entrypoint(tmp_path, current="")

    assert result.returncode == 0, result.stderr
    assert (backup_dir / "requested-output.txt").exists() is False
    assert upgrade_marker.read_text(encoding="utf-8") == "upgrade-ran\n"
    log_lines = _log_lines(tmp_path)
    _assert_core_flask_commands_ran(log_lines)
    _assert_no_backup_command(log_lines)


def test_backup_failure_warns_and_still_runs_upgrade(tmp_path: Path) -> None:
    result, backup_dir, upgrade_marker = _run_entrypoint(
        tmp_path, current="oldrev", heads="headrev", backup_fails=True
    )

    assert result.returncode == 0, result.stderr
    assert "[entrypoint] pre-upgrade backup failed; continuing" in result.stdout
    assert (backup_dir / "requested-output.txt").exists() is False
    assert upgrade_marker.read_text(encoding="utf-8") == "upgrade-ran\n"
    log_lines = _log_lines(tmp_path)
    _assert_core_flask_commands_ran(log_lines)
    _assert_backup_before_upgrade(log_lines)
