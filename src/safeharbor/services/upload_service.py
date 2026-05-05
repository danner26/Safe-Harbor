"""Upload service - private image storage helpers."""

from __future__ import annotations

import warnings
from pathlib import Path
from uuid import UUID

import pillow_heif
from flask import Response, abort, current_app, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

pillow_heif.register_heif_opener()

_ALLOWED_ENTITY_TYPES = {"tanks", "animals"}
_ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}
_MAX_EDGE_PX = 2000
_JPEG_QUALITY = 85


def save_image(*, entity_type: str, entity_id: UUID, file_storage: FileStorage) -> str:
    """Save an uploaded image as a private JPG and return its relative path."""
    _validate_entity_type(entity_type)
    relative_path = _relative_path(entity_type=entity_type, entity_id=entity_id)
    destination = _upload_dir() / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file_storage.stream) as source:
                if source.format not in _ALLOWED_IMAGE_FORMATS:
                    raise ValueError("Uploaded image could not be processed.")
                image = ImageOps.exif_transpose(source)
                image.thumbnail((_MAX_EDGE_PX, _MAX_EDGE_PX), Image.Resampling.LANCZOS)
                image = _as_jpeg_image(image)
                image.save(destination, format="JPEG", quality=_JPEG_QUALITY)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Uploaded image could not be processed.") from exc

    return relative_path.as_posix()


def remove_image(*, entity_type: str, entity_id: UUID) -> None:
    """Delete an uploaded image if it exists."""
    _validate_entity_type(entity_type)
    (_upload_dir() / _relative_path(entity_type=entity_type, entity_id=entity_id)).unlink(
        missing_ok=True
    )


def serve_image_response(*, entity_type: str, entity_id: UUID) -> Response:
    """Return a private cached response for a stored image."""
    _validate_entity_type(entity_type)
    upload_dir = _upload_dir()
    filename = f"{_entity_id_path_segment(entity_id)}.jpg"
    image_dir = upload_dir / entity_type
    if not (image_dir / filename).is_file():
        abort(404)

    response = send_from_directory(image_dir, filename, max_age=300)
    response.cache_control.private = True
    response.cache_control.public = False
    response.cache_control.max_age = 300
    return response


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in _ALLOWED_ENTITY_TYPES:
        raise ValueError("entity_type must be one of: animals, tanks.")


def _relative_path(*, entity_type: str, entity_id: UUID) -> Path:
    return Path(entity_type) / f"{_entity_id_path_segment(entity_id)}.jpg"


def _entity_id_path_segment(entity_id: UUID) -> str:
    if not isinstance(entity_id, UUID):
        raise ValueError("entity_id must be a UUID.")
    return str(entity_id)


def _upload_dir() -> Path:
    return Path(current_app.config["UPLOAD_DIR"])


def _as_jpeg_image(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, color=(255, 255, 255))
        alpha_source = image.convert("RGBA")
        background.paste(alpha_source, mask=alpha_source.getchannel("A"))
        return background
    return image.convert("RGB")
