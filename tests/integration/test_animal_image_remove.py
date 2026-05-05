"""Animal image removal integration tests."""

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

    user = User(email="animal-image-remover@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_animal(db_session: Any, **kwargs: Any) -> Any:
    from safeharbor.models.animal import Animal

    animal = Animal(
        species=kwargs.pop("species", "Ocellaris clownfish"),
        acquired_quantity=kwargs.pop("acquired_quantity", 1),
    )
    for key, value in kwargs.items():
        setattr(animal, key, value)
    db_session.add(animal)
    db_session.commit()
    return animal


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _image_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), color=(32, 96, 160))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.post(f"/animals/{uuid4()}/image/remove", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_remove_clears_image_path_and_redirects_to_edit(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    animal = _seed_animal(db_session, image_path=f"animals/{uuid4()}.jpg")

    resp = client.post(f"/animals/{animal.id}/image/remove", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.location == url_for("animals.edit_animal", animal_id=animal.id)
    db_session.refresh(animal)
    assert animal.image_path is None


def test_remove_deletes_file_from_disk(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    animal = _seed_animal(db_session, image_path=f"animals/{uuid4()}.jpg")
    image_path = upload_dir / "animals" / f"{animal.id}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_image_bytes())

    resp = client.post(f"/animals/{animal.id}/image/remove", follow_redirects=False)

    assert resp.status_code == 302
    db_session.refresh(animal)
    assert animal.image_path is None
    assert not image_path.exists()


def test_remove_404_when_animal_missing(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.post(f"/animals/{uuid4()}/image/remove")

    assert resp.status_code == 404


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    animal = _seed_animal(db_session, image_path=f"animals/{uuid4()}.jpg")

    resp = client.post(f"/animals/{animal.id}/image/remove", follow_redirects=False)

    assert resp.status_code == 400


def test_remove_accepts_valid_csrf_token(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    animal = _seed_animal(db_session, image_path=f"animals/{uuid4()}.jpg")
    form_resp = client.get(f"/animals/{animal.id}/edit")

    resp = client.post(
        f"/animals/{animal.id}/image/remove",
        data={"csrf_token": _csrf_token(form_resp.data)},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(animal)
    assert animal.image_path is None
