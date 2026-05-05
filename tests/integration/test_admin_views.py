"""Superuser-only admin views — invites + users management."""

from __future__ import annotations

import re


def _login_admin(client, db_session, email: str = "admin@x.com", preferred_units=None):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    admin = User(
        email=email,
        password_hash=hash_password("admin-pw-12345"),
        is_superuser=True,
        preferred_units=preferred_units,
    )
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True
    return admin


def _login_regular(client, db_session, email: str = "reg@x.com"):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email=email, password_hash=hash_password("regular-pw-12345"), is_superuser=False)
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def test_admin_invites_requires_login(client) -> None:
    resp = client.get("/admin/invites", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_admin_invites_rejects_non_superuser(client, db_session) -> None:
    _login_regular(client, db_session)
    resp = client.get("/admin/invites")
    assert resp.status_code == 403


def test_admin_invites_list_renders(client, db_session) -> None:
    _login_admin(client, db_session)
    resp = client.get("/admin/invites")
    assert resp.status_code == 200
    assert b"Invites" in resp.data or b"invite" in resp.data.lower()


def test_admin_issue_invite_creates_row_and_redirects_to_detail(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.invite import Invite

    _login_admin(client, db_session)
    resp = client.post(
        "/admin/invites",
        data={"email": "newcomer@x.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/invites/" in resp.location

    inv = db_session.scalar(select(Invite).where(Invite.email == "newcomer@x.com"))
    assert inv is not None
    assert inv.kind == "invite"
    assert inv.consumed_at is None


def test_admin_issued_invite_redeems_with_install_units(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.account import User

    _login_admin(client, db_session, preferred_units="metric")
    resp = client.post(
        "/admin/invites",
        data={"email": "metric-newcomer@x.com"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    match = re.search(rb"/register/([^\"<]+)", resp.data)
    assert match is not None

    register_resp = client.post(
        f"/register/{match.group(1).decode()}",
        data={"username": "", "password": "supersecure-pw", "confirm": "supersecure-pw"},
        follow_redirects=False,
    )
    assert register_resp.status_code == 302

    user = db_session.scalar(select(User).where(User.email == "metric-newcomer@x.com"))
    assert user is not None
    assert user.preferred_units == "metric"


def test_admin_invite_detail_shows_token_at_creation_only(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.invite import Invite

    _login_admin(client, db_session)
    # Issue and follow redirect — first visit to detail shows the token via flask.session
    resp = client.post("/admin/invites", data={"email": "show-once@x.com"}, follow_redirects=True)
    inv = db_session.scalar(select(Invite).where(Invite.email == "show-once@x.com"))
    assert resp.status_code == 200
    # The raw token (signed payload) is shown in the page once
    assert b"/register/" in resp.data
    # On a subsequent direct GET, the raw token is no longer shown
    resp2 = client.get(f"/admin/invites/{inv.id}")
    assert resp2.status_code == 200
    assert b"/register/" not in resp2.data
    assert b"show-once@x.com" in resp2.data


def test_admin_revoke_invite_marks_consumed(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.invite import Invite

    _login_admin(client, db_session)
    client.post("/admin/invites", data={"email": "rev@x.com"})
    inv = db_session.scalar(select(Invite).where(Invite.email == "rev@x.com"))
    resp = client.post(f"/admin/invites/{inv.id}/revoke", follow_redirects=False)
    assert resp.status_code == 302

    db_session.refresh(inv)
    assert inv.consumed_at is not None
    assert inv.consumed_by is None  # revoked, not redeemed


# ---------- /admin/users ----------


def test_admin_users_list_renders(client, db_session) -> None:
    _login_admin(client, db_session, email="alpha@x.com")
    # Add a couple users to render
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    db_session.add(User(email="bob@x.com", password_hash=hash_password("xx-bob-1234567")))
    db_session.add(User(email="carol@x.com", password_hash=hash_password("xx-car-1234567")))
    db_session.commit()

    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert b"alpha@x.com" in resp.data
    assert b"bob@x.com" in resp.data
    assert b"carol@x.com" in resp.data


def test_admin_user_detail_renders(client, db_session) -> None:
    _login_admin(client, db_session)
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    bob = User(email="bobd@x.com", password_hash=hash_password("xx-bob-1234567"))
    db_session.add(bob)
    db_session.commit()

    resp = client.get(f"/admin/users/{bob.id}")
    assert resp.status_code == 200
    assert b"bobd@x.com" in resp.data


def test_admin_user_reset_password_issues_link(client, db_session) -> None:
    from sqlalchemy import select

    from safeharbor.models.invite import Invite

    _login_admin(client, db_session)
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    bob = User(email="bobr@x.com", password_hash=hash_password("xx-bob-1234567"))
    db_session.add(bob)
    db_session.commit()

    resp = client.post(f"/admin/users/{bob.id}/reset-password", follow_redirects=True)
    assert resp.status_code == 200
    # Token shown once on the redirect target
    assert b"/password-reset/" in resp.data

    inv = db_session.scalar(
        select(Invite).where(Invite.email == "bobr@x.com", Invite.kind == "password_reset")
    )
    assert inv is not None
    assert inv.consumed_at is None


def test_admin_user_deactivate_and_reactivate(client, db_session) -> None:
    _login_admin(client, db_session)
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    bob = User(email="bobx@x.com", password_hash=hash_password("xx-bob-1234567"))
    db_session.add(bob)
    db_session.commit()

    client.post(f"/admin/users/{bob.id}/deactivate")
    db_session.refresh(bob)
    assert bob.is_active is False

    client.post(f"/admin/users/{bob.id}/reactivate")
    db_session.refresh(bob)
    assert bob.is_active is True


def test_admin_user_promote_and_demote(client, db_session) -> None:
    # Create two superusers so demote of one is allowed
    _login_admin(client, db_session, email="a1@x.com")
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    admin2 = User(email="a2@x.com", password_hash=hash_password("xx-1234567890"), is_superuser=True)
    user1 = User(email="u1@x.com", password_hash=hash_password("xx-1234567890"))
    db_session.add_all([admin2, user1])
    db_session.commit()

    client.post(f"/admin/users/{user1.id}/promote")
    db_session.refresh(user1)
    assert user1.is_superuser is True

    client.post(f"/admin/users/{user1.id}/demote")
    db_session.refresh(user1)
    assert user1.is_superuser is False


def test_admin_demote_last_superuser_refused(client, db_session) -> None:
    admin = _login_admin(client, db_session)  # only superuser

    client.post(f"/admin/users/{admin.id}/demote", follow_redirects=False)
    db_session.refresh(admin)
    assert admin.is_superuser is True  # not demoted
