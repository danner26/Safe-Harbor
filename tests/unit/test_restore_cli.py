"""Restore CLI command coverage."""

from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner, Result
from flask import Flask

from safeharbor.cli import _validate_tarball_structure, safeharbor_cli


def _write_member(tf: tarfile.TarFile, name: str, data: bytes = b"data") -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def _create_restore_tarball(
    tmp_path: Path,
    *,
    include_db_dump: bool = True,
    include_uploads: bool = True,
) -> Path:
    path = tmp_path / "restore.tar"
    with tarfile.open(path, "w") as tf:
        if include_db_dump:
            _write_member(tf, "db.dump", b"dump")
        if include_uploads:
            _write_member(tf, "uploads/foo.txt", b"upload")
    return path


def _pg_restore_list_result() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pg_restore", "--list"],
        returncode=0,
        stdout=(
            "123; 456 789 TABLE public tanks safeharbor\n"
            "124; 456 790 TABLE public measurements safeharbor\n"
        ),
        stderr="",
    )


@pytest.fixture
def restore_app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    upload_dir = tmp_path / "upload-dir"
    upload_dir.mkdir()
    app.config.update(
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://safeharbor:secret@localhost:5432/safeharbor",
        UPLOAD_DIR=str(upload_dir),
    )
    return app


def _invoke_restore(app: Flask, args: list[str]) -> Result:
    with app.app_context():
        return CliRunner().invoke(safeharbor_cli, args=args)


def test_validate_tarball_structure_passes_on_good_tarball(tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path)

    _validate_tarball_structure(str(path))


def test_validate_tarball_structure_passes_on_empty_uploads_dir(tmp_path: Path) -> None:
    path = tmp_path / "restore-empty-uploads.tar"
    with tarfile.open(path, "w") as tf:
        _write_member(tf, "db.dump", b"dump")
        info = tarfile.TarInfo("uploads")
        info.type = tarfile.DIRTYPE
        tf.addfile(info)

    assert _validate_tarball_structure(str(path)) == 0


def test_validate_tarball_structure_fails_on_missing_db_dump(tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path, include_db_dump=False)

    with pytest.raises(click.ClickException):
        _validate_tarball_structure(str(path))


def test_validate_tarball_structure_fails_on_missing_uploads(tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path, include_uploads=False)

    with pytest.raises(click.ClickException):
        _validate_tarball_structure(str(path))


def test_validate_tarball_structure_fails_on_non_tarball(tmp_path: Path) -> None:
    path = tmp_path / "not-a-tarball.tar"
    path.write_bytes(b"not a tarball")

    with pytest.raises(click.ClickException):
        _validate_tarball_structure(str(path))


def test_dry_run_does_not_call_destructive_pg_restore(restore_app: Flask, tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path)

    with patch("safeharbor.cli.subprocess.run", return_value=_pg_restore_list_result()) as run:
        result = _invoke_restore(restore_app, ["restore", "--from", str(path), "--dry-run"])

    assert result.exit_code == 0
    assert run.call_count == 1
    assert run.call_args_list[0].args[0][0:2] == ["pg_restore", "--list"]
    assert Path(run.call_args_list[0].args[0][2]).name == "db.dump"


def test_yes_flag_skips_prompt(restore_app: Flask, tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path)

    with (
        patch("safeharbor.cli.click.prompt") as prompt,
        patch("safeharbor.cli.subprocess.run", return_value=_pg_restore_list_result()),
    ):
        result = _invoke_restore(restore_app, ["restore", "--from", str(path), "--yes"])

    assert result.exit_code == 0
    prompt.assert_not_called()


def test_prompt_wrong_input_aborts(restore_app: Flask, tmp_path: Path) -> None:
    path = _create_restore_tarball(tmp_path)

    with (
        patch("safeharbor.cli.click.prompt", Mock(return_value="no")),
        patch("safeharbor.cli.subprocess.run", return_value=_pg_restore_list_result()) as run,
    ):
        result = _invoke_restore(restore_app, ["restore", "--from", str(path)])

    assert result.exit_code == 1
    assert all("--clean" not in call.args[0] for call in run.call_args_list)
