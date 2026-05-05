"""HTMX request helpers."""

from __future__ import annotations

from flask import request


def is_htmx_request() -> bool:
    """Return whether the current request was issued by HTMX."""
    return request.headers.get("Hx-Request") == "true"
