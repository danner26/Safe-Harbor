"""Gunicorn runtime configuration for Safe Harbor."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from gunicorn.glogging import Logger

bind = "0.0.0.0:8000"
workers = 2
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")

_TOKEN_PATH_PATTERNS = (
    re.compile(r"^(/register/)[^/?#]+"),
    re.compile(r"^(/password-reset/)[^/?#]+"),
    re.compile(r"^(/settings/account/email/verify/)[^/?#]+"),
)


def _header(req: Any, name: str, default: str = "-") -> str:
    for header_name, value in req.headers:
        if header_name.lower() == name.lower():
            return str(value)
    return default


def _redact_token_path(path: str) -> str:
    for pattern in _TOKEN_PATH_PATTERNS:
        if pattern.match(path):
            return pattern.sub(r"\1<redacted>", path)
    return path


def _redact_referer(referer: str) -> str:
    if referer == "-":
        return referer
    parts = urlsplit(referer)
    redacted_path = _redact_token_path(parts.path)
    return urlunsplit((parts.scheme, parts.netloc, redacted_path, parts.query, parts.fragment))


class JsonAccessLogger(Logger):
    """Emit gunicorn access logs as one JSON object per request."""

    def access(self, resp: Any, req: Any, environ: dict[str, Any], request_time: Any) -> None:
        referer = _header(req, "Referer")
        record = {
            "time": datetime.now(UTC).isoformat(),
            "level": "INFO",
            "logger": "gunicorn.access",
            "method": req.method,
            "path": _redact_token_path(req.path),
            "status": resp.status,
            "request_id": _header(req, "X-Request-Id"),
            "remote_addr": environ.get("REMOTE_ADDR", "-"),
            "user_agent": _header(req, "User-Agent"),
            "referer": _redact_referer(referer),
            "duration_ms": int(request_time.total_seconds() * 1000),
        }
        self.access_log.info(json.dumps(record, separators=(",", ":")))


logger_class = JsonAccessLogger
