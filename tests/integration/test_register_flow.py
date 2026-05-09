"""Registration via admin-issued invite token."""

from __future__ import annotations


def _seed_admin(db_session, *, preferred_units: str | None = None) -> "User":  # noqa
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(
        email="admin@x.com",
        password_hash=hash_password("admin-pw-12345"),
        is_superuser=True,
        preferred_units=preferred_units,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _issue(app, db_session, admin_id, email: str = "newbie@x.com") -> str:
    from safeharbor.models.invite import InviteKind
    from safeharbor.services.auth_service import issue_invite_token

    with app.app_context():
        token, _ = issue_invite_token(email=email, kind=InviteKind.INVITE, issued_by=admin_id)
        db_session.commit()
    return token


def test_register_get_with_valid_token_renders_form(client, app, db_session) -> None:
    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "alice@x.com")

    resp = client.get(f"/register/{token}")
    assert resp.status_code == 200
    assert b"alice@x.com" in resp.data
    assert b'name="password"' in resp.data
    assert b'name="confirm"' in resp.data


def test_register_get_with_bogus_token_shows_error_no_form(client, configured_user) -> None:
    resp = client.get("/register/this-is-not-a-real-token")
    assert resp.status_code == 200
    assert b"invalid or expired" in resp.data.lower()
    assert b'name="password"' not in resp.data


def test_register_post_creates_user_and_logs_in(client, app, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.account import User

    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "bob@x.com")

    resp = client.post(
        f"/register/{token}",
        data={"username": "Bob", "password": "supersecure-pw", "confirm": "supersecure-pw"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.location.endswith("/") or resp.location == "/"

    bob = db_session.scalar(select(User).where(User.email == "bob@x.com"))
    assert bob is not None
    assert bob.username == "Bob"
    assert bob.is_active is True
    assert bob.is_superuser is False
    # Password is hashed, not plaintext
    assert bob.password_hash != "supersecure-pw"
    assert bob.password_hash.startswith("$argon2")


def test_register_post_inherits_install_units_from_inviting_admin(client, app, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.account import User

    admin = _seed_admin(db_session, preferred_units="metric")
    token = _issue(app, db_session, admin.id, "metric-bob@x.com")

    resp = client.post(
        f"/register/{token}",
        data={"username": "Metric Bob", "password": "supersecure-pw", "confirm": "supersecure-pw"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    bob = db_session.scalar(select(User).where(User.email == "metric-bob@x.com"))
    assert bob is not None
    assert bob.preferred_units == "metric"


def test_register_post_marks_invite_consumed(client, app, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.invite import Invite

    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "carol@x.com")

    client.post(
        f"/register/{token}",
        data={"username": "", "password": "supersecure-pw", "confirm": "supersecure-pw"},
    )
    invite = db_session.scalar(select(Invite).where(Invite.email == "carol@x.com"))
    assert invite is not None
    assert invite.consumed_at is not None
    assert invite.consumed_by is not None


def test_register_post_rejects_already_consumed_token(client, app, db_session) -> None:
    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "dave@x.com")

    # First registration succeeds
    client.post(
        f"/register/{token}",
        data={"username": "", "password": "supersecure-pw", "confirm": "supersecure-pw"},
    )
    # Second attempt with same token rejected
    resp = client.post(
        f"/register/{token}",
        data={"username": "", "password": "supersecure-pw", "confirm": "supersecure-pw"},
    )
    assert resp.status_code == 200
    assert b"invalid or expired" in resp.data.lower()


def test_register_post_rejects_when_email_already_user(client, app, db_session) -> None:
    from safeharbor.models.account import User

    admin = _seed_admin(db_session)
    db_session.add(User(email="exists@x.com", password_hash="h"))
    db_session.commit()
    token = _issue(app, db_session, admin.id, "exists@x.com")

    resp = client.post(
        f"/register/{token}",
        data={"username": "", "password": "supersecure-pw", "confirm": "supersecure-pw"},
    )
    # Don't reveal whether the email exists — same generic error
    assert resp.status_code == 200
    assert b"invalid or expired" in resp.data.lower()


def test_register_post_rejects_short_password(client, app, db_session) -> None:
    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "shortpw@x.com")

    resp = client.post(
        f"/register/{token}",
        data={"username": "", "password": "short", "confirm": "short"},
    )
    assert resp.status_code == 200
    # WTForms Length(min=10) message — match loosely
    assert (
        b"at least 10" in resp.data
        or b"10 characters" in resp.data
        or b"too short" in resp.data.lower()
    )


def test_register_post_rejects_mismatched_passwords(client, app, db_session) -> None:
    admin = _seed_admin(db_session)
    token = _issue(app, db_session, admin.id, "mm@x.com")

    resp = client.post(
        f"/register/{token}",
        data={"username": "", "password": "supersecure-pw", "confirm": "different-pw"},
    )
    assert resp.status_code == 200
    assert b"match" in resp.data.lower()
