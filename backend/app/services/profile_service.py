"""Self-service profile: a signed-in user may change ONLY their display name, phone
number and profile photograph. Email, department, role, authority level and account
status are not editable here (there is no verification flow for them); the API
schema rejects any attempt to send them.

Profile photos:
- accepted only if the bytes really are JPEG, PNG or WebP (magic-number check; the
  client's content type and file name are not trusted) and within the size limit;
- stored on disk under MEDIA_DIR/profile_photos with a server-generated random name
  (no user-controlled path), never in the database;
- returned only to their owner through an authenticated endpoint.
"""
import logging
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings
from app.models import User
from app.services.errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("safespeak.profile")

EDITABLE_FIELDS = ("name", "phone", "photo")
PHOTO_DIR = "profile_photos"
FILENAME_RE = re.compile(r"^\d+-[0-9a-f]{16}\.(jpg|png|webp)$")
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{5,17}[0-9]$")


class PhotoTooLarge(InvalidRequestError):
    status_code = 413


class UnsupportedImage(InvalidRequestError):
    status_code = 415


def sniff_image(data: bytes) -> str | None:
    """File extension for a supported image, decided from its content only."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _photo_dir(settings: Settings) -> Path:
    base = settings.media_dir if settings.media_dir.is_absolute() else BACKEND_DIR / settings.media_dir
    return base / PHOTO_DIR


def update_profile(db: Session, user: User, *, name: str | None = None, phone: str | None = None,
                   clear_phone: bool = False) -> User:
    if name is not None:
        name = " ".join(name.split())
        if not 2 <= len(name) <= 120:
            raise InvalidRequestError("Name must be between 2 and 120 characters")
        user.name = name
    if clear_phone:
        user.phone = None
    elif phone is not None:
        phone = phone.strip()
        if not PHONE_RE.match(phone) or sum(ch.isdigit() for ch in phone) < 7:
            raise InvalidRequestError("Enter a valid phone number (digits, spaces, +, - and brackets)")
        user.phone = phone
    db.commit()
    db.refresh(user)
    return user


def save_photo(db: Session, settings: Settings, user: User, data: bytes) -> User:
    if not data:
        raise InvalidRequestError("The uploaded file is empty")
    if len(data) > settings.profile_photo_max_bytes:
        raise PhotoTooLarge(f"The photo must be at most {settings.profile_photo_max_bytes // (1024 * 1024)} MB")
    ext = sniff_image(data)
    if ext is None:
        raise UnsupportedImage("Upload a JPEG, PNG or WebP image")

    folder = _photo_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{user.id}-{secrets.token_hex(8)}.{ext}"
    tmp = folder / f".{filename}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, folder / filename)  # never a half-written photo

    old = user.photo_filename
    user.photo_filename = filename
    try:
        db.commit()
    except Exception:
        (folder / filename).unlink(missing_ok=True)
        raise
    db.refresh(user)
    if old and FILENAME_RE.match(old):
        (folder / old).unlink(missing_ok=True)
    logger.info("Profile photo updated for user %s", user.id)
    return user


def delete_photo(db: Session, settings: Settings, user: User) -> User:
    old = user.photo_filename
    user.photo_filename = None
    db.commit()
    db.refresh(user)
    if old and FILENAME_RE.match(old):
        (_photo_dir(settings) / old).unlink(missing_ok=True)
    return user


@dataclass(frozen=True)
class Photo:
    path: Path
    media_type: str


def photo_for(settings: Settings, user: User) -> Photo:
    name = user.photo_filename
    if not name or not FILENAME_RE.match(name):
        raise NotFoundError("No profile photo")
    path = _photo_dir(settings) / name
    if not path.is_file():
        raise NotFoundError("No profile photo")
    return Photo(path, MEDIA_TYPES[name.rsplit(".", 1)[1]])
