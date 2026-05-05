"""base.html renders and references HTMX."""

from __future__ import annotations

from flask import render_template
from flask_login import login_user


def test_base_template_renders_for_anonymous_user(app) -> None:
    # The no-op user_loader workaround is registered in the app factory;
    # see src/safeharbor/__init__.py and its TODO(phase-1).
    with app.app_context(), app.test_request_context():
        html = render_template("base.html")
        assert "<!doctype html>" in html.lower()
        assert "viewport" in html
        assert "vendor/htmx/htmx.min.js" in html
        assert '<nav class="dnav"' in html  # Phase 1a Task 7: desktop navbar
        assert '<nav class="mtabs"' not in html
        assert "<footer" in html  # Phase 1a Task 7: footer
        assert "css/app.css" in html  # Phase 1a Task 7: compiled CSS link


def test_base_template_renders_auth_chrome_for_authenticated_user(app, db_session) -> None:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="template-render@example.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()

    with app.app_context(), app.test_request_context():
        login_user(user)
        html = render_template("base.html")
        assert '<nav class="dnav"' in html  # Phase 1a Task 7: desktop navbar
        assert '<nav class="mtabs"' in html  # Phase 1a Task 7: mobile bottom tab bar
