"""Upload service tests."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import NotFound

from safeharbor.services import upload_service

TANK_ID = UUID("018f3f4f-4c8d-7c1a-9b2e-123456789abc")
ANIMAL_ID = UUID("018f3f50-2b7a-71c9-a44d-abcdef123456")


@pytest.fixture
def upload_app(tmp_path: Path) -> Iterator[Flask]:
    app = Flask(__name__)
    app.config["UPLOAD_DIR"] = tmp_path
    with app.app_context():
        yield app


def _file_storage(image_bytes: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=BytesIO(image_bytes), filename=filename)


def _image_bytes(
    *,
    image_format: str = "JPEG",
    size: tuple[int, int] = (64, 48),
    exif: Image.Exif | None = None,
) -> bytes:
    image = Image.new("RGB", size, color=(32, 96, 160))
    output = BytesIO()
    save_kwargs = {"exif": exif} if exif is not None else {}
    image.save(output, format=image_format, **save_kwargs)
    return output.getvalue()


def _saved_image(path: Path) -> tuple[str | None, tuple[int, int]]:
    with Image.open(path) as image:
        return image.format, image.size


def test_save_image_writes_jpg_and_returns_relative_path(upload_app: Flask, tmp_path: Path) -> None:
    relative_path = upload_service.save_image(
        entity_type="tanks",
        entity_id=TANK_ID,
        file_storage=_file_storage(_image_bytes(image_format="PNG"), "source.png"),
    )

    saved_path = tmp_path / "tanks" / f"{TANK_ID}.jpg"
    assert relative_path == f"tanks/{TANK_ID}.jpg"
    assert saved_path.exists()
    assert _saved_image(saved_path)[0] == "JPEG"


def test_save_image_rejects_unknown_entity_type(upload_app: Flask) -> None:
    with pytest.raises(ValueError, match="entity_type"):
        upload_service.save_image(
            entity_type="systems",
            entity_id=TANK_ID,
            file_storage=_file_storage(_image_bytes(), "source.jpg"),
        )


def test_save_image_rejects_non_uuid_entity_id(upload_app: Flask) -> None:
    with pytest.raises(ValueError, match="entity_id"):
        upload_service.save_image(
            entity_type="tanks",
            entity_id=Path("../escape"),  # type: ignore[arg-type]
            file_storage=_file_storage(_image_bytes(), "source.jpg"),
        )


def test_save_image_rejects_corrupt_image(upload_app: Flask) -> None:
    with pytest.raises(ValueError, match="could not be processed"):
        upload_service.save_image(
            entity_type="tanks",
            entity_id=TANK_ID,
            file_storage=_file_storage(b"not an image", "source.jpg"),
        )


def test_decompression_bomb_translates_to_value_error(
    upload_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_decompression_bomb(_stream: BytesIO) -> Image.Image:
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(upload_service.Image, "open", raise_decompression_bomb)

    with pytest.raises(ValueError, match="could not be processed"):
        upload_service.save_image(
            entity_type="tanks",
            entity_id=TANK_ID,
            file_storage=_file_storage(_image_bytes(), "source.jpg"),
        )


def test_decompression_bomb_warning_translates_to_value_error(
    upload_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def warn_decompression_bomb(_stream: BytesIO) -> Image.Image:
        warnings.warn(
            "too many pixels",
            Image.DecompressionBombWarning,
            stacklevel=2,
        )
        return Image.new("RGB", (1, 1))

    monkeypatch.setattr(upload_service.Image, "open", warn_decompression_bomb)

    with pytest.raises(ValueError, match="could not be processed"):
        upload_service.save_image(
            entity_type="tanks",
            entity_id=TANK_ID,
            file_storage=_file_storage(_image_bytes(), "source.jpg"),
        )


def test_unsupported_format_raises(upload_app: Flask, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="could not be processed"):
        upload_service.save_image(
            entity_type="tanks",
            entity_id=TANK_ID,
            file_storage=_file_storage(_image_bytes(image_format="GIF"), "source.gif"),
        )

    assert not (tmp_path / "tanks" / f"{TANK_ID}.jpg").exists()


def test_exif_orientation_is_applied_before_save(upload_app: Flask, tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[274] = 6

    upload_service.save_image(
        entity_type="animals",
        entity_id=ANIMAL_ID,
        file_storage=_file_storage(
            _image_bytes(size=(80, 40), exif=exif),
            "portrait.jpg",
        ),
    )

    assert _saved_image(tmp_path / "animals" / f"{ANIMAL_ID}.jpg")[1] == (40, 80)


def test_resize_clamps_to_2000px_max_edge(upload_app: Flask, tmp_path: Path) -> None:
    upload_service.save_image(
        entity_type="tanks",
        entity_id=TANK_ID,
        file_storage=_file_storage(
            _image_bytes(image_format="PNG", size=(2400, 1200)),
            "wide.png",
        ),
    )

    assert _saved_image(tmp_path / "tanks" / f"{TANK_ID}.jpg")[1] == (2000, 1000)


def test_exif_stripped_after_save(upload_app: Flask, tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[271] = "Safe Harbor Test Camera"

    upload_service.save_image(
        entity_type="animals",
        entity_id=ANIMAL_ID,
        file_storage=_file_storage(_image_bytes(exif=exif), "source.jpg"),
    )

    with Image.open(tmp_path / "animals" / f"{ANIMAL_ID}.jpg") as saved:
        assert dict(saved.getexif()) == {}


def test_heic_input_produces_jpg_output(upload_app: Flask, tmp_path: Path) -> None:
    import pillow_heif

    pillow_heif.register_heif_opener()
    source = BytesIO()
    Image.new("RGB", (32, 32), color=(120, 80, 40)).save(source, format="HEIF")

    relative_path = upload_service.save_image(
        entity_type="tanks",
        entity_id=TANK_ID,
        file_storage=_file_storage(source.getvalue(), "source.heic"),
    )

    saved_path = tmp_path / relative_path
    assert relative_path == f"tanks/{TANK_ID}.jpg"
    assert _saved_image(saved_path)[0] == "JPEG"


def test_remove_image_is_idempotent(upload_app: Flask, tmp_path: Path) -> None:
    image_path = tmp_path / "tanks" / f"{TANK_ID}.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(_image_bytes())

    upload_service.remove_image(entity_type="tanks", entity_id=TANK_ID)
    upload_service.remove_image(entity_type="tanks", entity_id=TANK_ID)

    assert not image_path.exists()


def test_serve_image_response_uses_private_cache(upload_app: Flask, tmp_path: Path) -> None:
    image_path = tmp_path / "animals" / f"{ANIMAL_ID}.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(_image_bytes())

    with upload_app.test_request_context(f"/images/animals/{ANIMAL_ID}"):
        response = upload_service.serve_image_response(
            entity_type="animals",
            entity_id=ANIMAL_ID,
        )

    assert response.status_code == 200
    assert response.cache_control.private
    assert response.cache_control.max_age == 300


def test_serve_image_response_404s_when_missing(upload_app: Flask) -> None:
    with upload_app.test_request_context(f"/images/animals/{ANIMAL_ID}"), pytest.raises(NotFound):
        upload_service.serve_image_response(entity_type="animals", entity_id=ANIMAL_ID)
