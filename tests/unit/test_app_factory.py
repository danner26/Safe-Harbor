"""App factory startup validation behavior."""

from __future__ import annotations

from pathlib import Path

from flask import Flask

from safeharbor import _validate_upload_dir


def test_validate_upload_dir_allows_non_writable_dir_when_disabled(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    upload_dir.chmod(0o500)

    app = Flask(__name__)
    app.config["UPLOAD_DIR"] = str(upload_dir)
    app.config["UPLOAD_DIR_REQUIRE_WRITABLE"] = False

    try:
        _validate_upload_dir(app)
    finally:
        upload_dir.chmod(0o700)
