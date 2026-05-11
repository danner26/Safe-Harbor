"""Tank image upload integration tests."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, url_for
from PIL import Image


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="image-uploader@x.com", password_hash=hash_password("test-pw-12345"))
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


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _image_bytes(*, color: tuple[int, int, int] = (32, 96, 160)) -> bytes:
    image = Image.new("RGB", (40, 30), color=color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _upload_data(filename: str = "reef.png", **kwargs: Any) -> dict[str, Any]:
    payload = {"image": (BytesIO(_image_bytes(**kwargs)), filename)}
    return payload


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.post(f"/tanks/{uuid4()}/image", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_edit_form_renders_image_controls(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session, image_path="tanks/reef.jpg")

    resp = client.get(f"/tanks/{tank.id}/edit")

    assert resp.status_code == 200
    assert b'enctype="multipart/form-data"' in resp.data
    assert bytes(f'action="/tanks/{tank.id}/image"', "utf-8") in resp.data
    assert bytes(f'action="/tanks/{tank.id}/image/remove"', "utf-8") in resp.data
    assert bytes(f'src="/tanks/{tank.id}/image"', "utf-8") in resp.data
    assert b'name="csrf_token"' in resp.data


def test_upload_sets_image_path_and_redirects_to_edit(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data=_upload_data(),
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == url_for("tanks.edit", tank_id=tank.id)
    db_session.refresh(tank)
    assert tank.image_path == f"tanks/{tank.id}.jpg"
    assert (upload_dir / "tanks" / f"{tank.id}.jpg").is_file()


def test_rejects_disallowed_extension(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data={"image": (BytesIO(b"not an image"), "notes.txt")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(tank)
    assert tank.image_path is None
    assert not (upload_dir / "tanks" / f"{tank.id}.jpg").exists()


def test_corrupt_file_flashes_and_redirects(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data={"image": (BytesIO(b"not an image"), "reef.jpg")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == url_for("tanks.edit", tank_id=tank.id)
    db_session.refresh(tank)
    assert tank.image_path is None


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data=_upload_data(),
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_upload_accepts_valid_csrf_token(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    form_resp = client.get(f"/tanks/{tank.id}/edit")

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data={"csrf_token": _csrf_token(form_resp.data), **_upload_data()},
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(tank)
    assert tank.image_path == f"tanks/{tank.id}.jpg"


def test_413_when_over_max_content_length(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["MAX_CONTENT_LENGTH"] = 64
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/tanks/{tank.id}/image",
        data=_upload_data(),
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert resp.status_code == 413


def test_replace_overwrites_at_same_path(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    tank = _seed_tank(db_session)

    first = client.post(
        f"/tanks/{tank.id}/image",
        data=_upload_data(color=(255, 0, 0)),
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    saved_path = upload_dir / "tanks" / f"{tank.id}.jpg"
    first_bytes = saved_path.read_bytes()

    second = client.post(
        f"/tanks/{tank.id}/image",
        data=_upload_data(color=(0, 255, 0)),
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.status_code == 302
    db_session.refresh(tank)
    assert tank.image_path == f"tanks/{tank.id}.jpg"
    assert saved_path.read_bytes() != first_bytes
