"""Root / route serves the dashboard layout (Phase 1a placeholder)."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any, email: str = "t@x.com") -> None:
    """Seed a user in the DB and inject a valid Flask-Login session."""
    from safeharbor.models.account import User

    u = User(email=email, password_hash="h")
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True


def test_root_returns_200(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert response.status_code == 200


def test_root_renders_safe_harbor_branding(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert b"Safe Harbor" in response.data


def test_root_references_logo(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert b"SafeHarborLogo.svg" in response.data


# ── Dashboard-specific assertions ─────────────────────────────────────────


def test_root_shows_dashboard_kpi_strip(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert b"kpi-card" in response.data
    assert b"Salinity" in response.data
    assert b"&mdash;" in response.data


def test_root_shows_tank_grid_empty_state(client: FlaskClient, db_session: Any) -> None:
    """With no tanks seeded the dashboard shows the empty-state CTA."""
    _login(client, db_session)
    response = client.get("/")
    assert b"Your tanks" in response.data
    assert b"Add your first tank" in response.data
    assert b"Add a tank to start logging readings and trends." in response.data
    assert b"Three tanks logged in the last 24 hours" not in response.data


def test_root_header_ctas_link_real_routes(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert b'href="/tanks/new"' in response.data
    assert b'href="/measurements/quick-add"' in response.data
    assert b'href="#quick-add"' not in response.data


def test_root_shows_tank_grid_with_seeded_tanks(client: FlaskClient, db_session: Any) -> None:
    """With real tanks seeded the dashboard renders them in the grid."""
    from safeharbor.models.tank import Tank

    _login(client, db_session)
    db_session.add(Tank(name="Reef 90", water_type="salt"))
    db_session.add(Tank(name="Planted 40", water_type="fresh"))
    db_session.add(Tank(name="Mangrove tide", water_type="brackish"))
    db_session.commit()
    response = client.get("/")
    assert b"Reef 90" in response.data
    assert b"Planted 40" in response.data
    assert b"Mangrove tide" in response.data
    assert b"chip-salt" in response.data
    assert b"chip-fresh" in response.data
    assert b"chip-brackish" in response.data


def test_root_shows_measurements_table(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    response = client.get("/")
    assert b"Recent measurements" in response.data
    assert b"No readings yet" in response.data
