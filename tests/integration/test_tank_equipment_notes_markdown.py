"""Tank equipment notes render through the markdown sanitizer."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="equipment-notes@example.test",
        password_hash=hash_password("test-pw-12345"),
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(db_session: Any, *, equipment_notes: str) -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name="Reef 90", water_type="salt", equipment_notes=equipment_notes)
    db_session.add(tank)
    db_session.commit()
    return tank


def _equipment_notes_fragment(body: str) -> str:
    start = body.index("Equipment notes")
    end = body.index("</div>", start)
    return body[start:end]


def test_unauthenticated_redirects_to_login(client: FlaskClient) -> None:
    response = client.get("/tanks/new", follow_redirects=False)

    assert response.status_code == 302
    assert response.location is not None
    assert "/login" in response.location


def test_markdown_headings_render_as_html(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session, equipment_notes="# Lighting\n\n- Kessil")

    response = client.get(f"/tanks/{tank.id}")

    assert response.status_code == 200
    body = response.data.decode()
    assert "<h1>Lighting</h1>" in body
    assert "<li>Kessil</li>" in body
    assert "# Lighting" not in body


def test_markdown_links_get_rel_nofollow_noopener(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(
        db_session,
        equipment_notes="[Pump](https://example.test/pump)",
    )

    response = client.get(f"/tanks/{tank.id}")

    assert response.status_code == 200
    body = response.data.decode()
    assert '<a href="https://example.test/pump" rel="nofollow noopener">Pump</a>' in body


def test_script_tags_stripped(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(
        db_session,
        equipment_notes="<script>alert('xss')</script>Safe note",
    )

    response = client.get(f"/tanks/{tank.id}")

    assert response.status_code == 200
    body = response.data.decode()
    fragment = _equipment_notes_fragment(body)
    assert "<script" not in fragment
    assert "alert" not in fragment
    assert "Safe note" in fragment


def test_image_tags_denied(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(
        db_session,
        equipment_notes="![alt text](https://example.test/pump.jpg)",
    )

    response = client.get(f"/tanks/{tank.id}")

    assert response.status_code == 200
    body = response.data.decode()
    fragment = _equipment_notes_fragment(body)
    assert "<img" not in fragment
    assert "pump.jpg" not in fragment


def test_form_shows_markdown_supported_hint(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session, equipment_notes="Existing note")

    create_response = client.get("/tanks/new")
    edit_response = client.get(f"/tanks/{tank.id}/edit")

    for response in (create_response, edit_response):
        assert response.status_code == 200
        body = response.data.decode()
        assert "Markdown supported" in body
        assert "links, headings, lists, code" in body
        assert 'href="https://commonmark.org/help/"' in body
        assert 'target="_blank"' in body
        assert 'rel="noopener noreferrer"' in body
