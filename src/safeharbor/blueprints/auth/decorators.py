"""View-decorator markers used by the app-level login-required hook."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from flask import abort
from flask_login import current_user

F = TypeVar("F", bound=Callable[..., Any])


def public(view: F) -> F:
    """Mark a view as exempt from login-required-by-default.

    The before_request hook in __init__.py inspects view._is_public to decide
    whether to redirect anonymous requests to /login. Apply this to /login,
    /register/<token>, /password-reset/<token>, and /healthz. /logout is
    intentionally NOT public — it requires an authenticated user."""
    view._is_public = True  # type: ignore[attr-defined]
    return view


def superuser_required(view: F) -> F:
    """Reject any request whose current_user is not is_superuser=True.

    Anonymous requests get 401 from Flask-Login (which our login hook will
    have already redirected anyway). Authenticated-but-not-superuser get 403."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "is_superuser", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
