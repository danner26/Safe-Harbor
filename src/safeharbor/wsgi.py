"""Gunicorn entrypoint.

Usage in Dockerfile / process manager:
    gunicorn safeharbor.wsgi:app
"""

from __future__ import annotations

from safeharbor import create_app

app = create_app()
