"""The signed-in user's own profile. Every route acts on the user from the verified
JWT; there is no user ID in any path or body, so no one can read or change another
user's profile. Only name, phone and photo are editable (ProfileUpdate forbids
any other field, e.g. role, email, department or is_active -> 422)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.schemas.user import ProfileOut, UserOut
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    # "" clears the phone number.
    phone: str | None = Field(default=None, max_length=40)


def _out(user) -> ProfileOut:
    return ProfileOut(
        **UserOut.model_validate(user).model_dump(),
        phone=user.phone,
        has_photo=user.has_photo,
        editable_fields=list(profile_service.EDITABLE_FIELDS),
    )


async def photo_body(request: Request, settings: AppSettings) -> bytes:
    """The raw request body (the image bytes), read with a hard size limit."""
    limit = settings.profile_photo_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The photo is too large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The photo is too large")
    return bytes(data)


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser) -> ProfileOut:
    return _out(user)


@router.patch("", response_model=ProfileOut)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> ProfileOut:
    clear_phone = payload.phone is not None and payload.phone.strip() == ""
    user = profile_service.update_profile(
        db, user, name=payload.name, phone=None if clear_phone else payload.phone, clear_phone=clear_phone
    )
    return _out(user)


@router.put("/photo", response_model=ProfileOut)
def upload_photo(
    user: CurrentUser, db: DbSession, settings: AppSettings, data: Annotated[bytes, Depends(photo_body)]
) -> ProfileOut:
    """Body: the image bytes (Content-Type image/jpeg, image/png or image/webp). The
    type is decided from the content, not from the header or a file name."""
    return _out(profile_service.save_photo(db, settings, user, data))


@router.delete("/photo", response_model=ProfileOut)
def remove_photo(user: CurrentUser, db: DbSession, settings: AppSettings) -> ProfileOut:
    return _out(profile_service.delete_photo(db, settings, user))


@router.get("/photo")
def get_photo(user: CurrentUser, settings: AppSettings) -> Response:
    photo = profile_service.photo_for(settings, user)
    return FileResponse(
        photo.path,
        media_type=photo.media_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": "inline"},
    )
