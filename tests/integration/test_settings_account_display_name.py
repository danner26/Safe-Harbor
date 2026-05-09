"""Account settings display-name form."""

from __future__ import annotations

from safeharbor.models import User
from safeharbor.services.auth_service import hash_password


def _login(client, db_session) -> User:
    user = User(
        email="display@example.com", username="Old Name", password_hash=hash_password("pw-12345")
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client, configured_user) -> None:
    resp = client.post(
        "/settings/account/display-name",
        data={"username": "New Name"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_username_persists_after_submit(client, db_session) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/display-name",
        data={"username": "New Name"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(user)
    assert user.username == "New Name"
