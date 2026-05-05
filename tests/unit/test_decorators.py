"""Decorators that gate views: @public marks a view exempt from login-required;
@superuser_required rejects non-superusers."""

from __future__ import annotations

from flask import Flask

from safeharbor.blueprints.auth.decorators import public, superuser_required


def test_public_decorator_marks_view() -> None:
    @public
    def view():
        return "ok"

    assert getattr(view, "_is_public", False) is True


def test_public_decorator_preserves_call_behavior() -> None:
    @public
    def view():
        return "hello"

    assert view() == "hello"


def test_superuser_required_rejects_anonymous(app: Flask, client) -> None:
    @superuser_required
    def view():
        return "ok"

    app.add_url_rule("/__t_su", endpoint="test_t_su", view_func=view)
    resp = client.get("/__t_su")
    # before_request hook isn't yet installed, so superuser_required is
    # the first gate. It must redirect anon → /login.
    assert resp.status_code in (302, 401, 403)


def test_superuser_required_rejects_regular_user(app: Flask, client, db_session) -> None:
    from flask_login import login_user

    from safeharbor.models.account import User

    @superuser_required
    def view():
        return "ok"

    app.add_url_rule("/__t_su2", endpoint="test_t_su2", view_func=view)
    u = User(email="reg@x.com", password_hash="h", is_superuser=False)
    db_session.add(u)
    db_session.commit()

    with client:
        with client.session_transaction():
            pass
        with app.test_request_context():
            login_user(u)
        # Use Flask test client login helper via session manipulation:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(u.id)
            sess["_fresh"] = True
        resp = client.get("/__t_su2")
        assert resp.status_code == 403


def test_superuser_required_allows_superuser(app: Flask, client, db_session) -> None:
    from safeharbor.models.account import User

    @superuser_required
    def view():
        return "ok"

    app.add_url_rule("/__t_su3", endpoint="test_t_su3", view_func=view)
    u = User(email="su@x.com", password_hash="h", is_superuser=True)
    db_session.add(u)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    resp = client.get("/__t_su3")
    assert resp.status_code == 200
    assert resp.data == b"ok"
