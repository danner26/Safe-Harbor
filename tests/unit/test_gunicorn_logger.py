"""Gunicorn access-log helper tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_gconf_path = Path(__file__).resolve().parents[2] / "docker" / "gunicorn.conf.py"
_spec = importlib.util.spec_from_file_location("gconf", _gconf_path)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
assert isinstance(_module, ModuleType)
_spec.loader.exec_module(_module)

_redact_token_path = _module._redact_token_path
_redact_referer = _module._redact_referer


def test_redacts_register_token_path() -> None:
    assert _redact_token_path("/register/secret-token") == "/register/<redacted>"


def test_redacts_password_reset_token_path() -> None:
    assert _redact_token_path("/password-reset/secret-token") == "/password-reset/<redacted>"


def test_redacts_email_verify_token_path() -> None:
    path = "/settings/account/email/verify/secret-token"

    assert _redact_token_path(path) == "/settings/account/email/verify/<redacted>"


def test_leaves_normal_path_unchanged() -> None:
    assert _redact_token_path("/tanks/") == "/tanks/"


def test_redacts_token_path_in_referer() -> None:
    referer = "https://safeharbor.example/register/secret-token?next=/tanks/#section"

    assert (
        _redact_referer(referer)
        == "https://safeharbor.example/register/<redacted>?next=/tanks/#section"
    )
