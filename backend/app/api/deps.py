"""Reusable request dependencies: settings, current user, and authorization."""
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Permission, Role, has_permission
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models import User

# auto_error=False so a missing header produces our own 401 (not a 403).
_bearer = HTTPBearer(auto_error=False, description="JWT access token from POST /api/v1/auth/login")

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Authenticate the request. The role used for every decision is the one
    stored on the database account, never a value supplied by the client."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", _UNAUTHENTICATED_HEADERS)
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except TokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", _UNAUTHENTICATED_HEADERS
        ) from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", _UNAUTHENTICATED_HEADERS)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    return user


require_authenticated_user = get_current_user
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*permissions: Permission) -> Callable[..., User]:
    """Dependency factory: the current user's role must grant every listed permission."""

    def dependency(user: CurrentUser) -> User:
        if not all(has_permission(user.role, p) for p in permissions):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return user

    return dependency


def require_role(*roles: Role) -> Callable[..., User]:
    """Dependency factory: the current user's role must be one of the listed roles.
    Prefer require_permission; use this only where a rule is truly role-specific."""

    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return user

    return dependency
