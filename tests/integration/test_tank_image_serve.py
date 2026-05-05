"""Tank image serving integration tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask
from PIL import Image


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="image-server@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(db_session: Any, **kwargs: Any) -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=kwargs.pop("name", "Reef 90"), water_type=kwargs.pop("water_type", "salt"))
    for key, value in kwargs.items():
        setattr(tank, key, value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _image_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), color=(32, 96, 160))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.get(f"/tanks/{uuid4()}/image", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_serves_private_image(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    tank = _seed_tank(db_session, image_path="tanks/stale-name.jpg")
    image_path = upload_dir / "tanks" / f"{tank.id}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_image_bytes())

    resp = client.get(f"/tanks/{tank.id}/image")

    assert resp.status_code == 200
    assert resp.content_type == "image/jpeg"
    assert "private" in resp.headers["Cache-Control"]


def test_404_when_no_image(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.get(f"/tanks/{tank.id}/image")

    assert resp.status_code == 404


def test_404_when_tank_missing(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get(f"/tanks/{uuid4()}/image")

    assert resp.status_code == 404
