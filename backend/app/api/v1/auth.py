from fastapi import APIRouter, HTTPException, status

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.core.permissions import permissions_for
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import CurrentUserOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = "Invalid email or password"


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession, settings: AppSettings) -> TokenResponse:
    """Credentials are accepted only in the JSON body, never in the URL."""
    try:
        user = auth_service.authenticate(db, settings, payload.email, payload.password)
    except auth_service.SignInNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is not configured on this server"
        ) from None
    except auth_service.EmailDomainNotAllowed:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Use your institutional email address to sign in"
        ) from None
    except auth_service.InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_CREDENTIALS) from None
    except auth_service.AccountDisabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled") from None

    token, expires_in = create_access_token(user.id, user.role, settings)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserOut)
def me(user: CurrentUser) -> CurrentUserOut:
    return CurrentUserOut(
        **UserOut.model_validate(user).model_dump(),
        permissions=sorted(permissions_for(user.role)),
    )
