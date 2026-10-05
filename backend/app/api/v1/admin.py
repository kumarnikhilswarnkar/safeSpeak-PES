from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require_permission
from app.core.permissions import Permission
from app.models import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: DbSession,
    _admin: Annotated[User, Depends(require_permission(Permission.MANAGE_USERS))],
) -> list[User]:
    return list(
        db.scalars(select(User).options(selectinload(User.department)).order_by(User.role, User.email))
    )
