"""Password hashing and JWT access tokens."""
from datetime import datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt

from app.core.config import Settings
from app.core.timeutil import utcnow

# bcrypt only uses the first 72 bytes; longer input is refused rather than
# silently truncated.
MAX_PASSWORD_BYTES = 72
TOKEN_ISSUER = "safespeak-pes"
ACCESS_TOKEN_TYPE = "access"


class TokenError(Exception):
    """The token is missing, malformed, expired, or not signed by this server."""


def hash_password(password: str, rounds: int) -> str:
    data = password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    data = password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(data, password_hash.encode("ascii"))
    except ValueError:
        return False


@lru_cache
def _dummy_hash(rounds: int) -> bytes:
    return bcrypt.hashpw(b"safespeak-timing-equaliser", bcrypt.gensalt(rounds=rounds))


def spend_verification_time(password: str, rounds: int) -> None:
    """Do the same bcrypt work as a real check, so a login for an unknown
    account takes as long as one for an existing account."""
    bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], _dummy_hash(rounds))


def create_access_token(
    user_id: int, role: str, settings: Settings, *, now: datetime | None = None
) -> tuple[str, int]:
    """Return (token, lifetime in seconds).

    The role claim is informational for the client only; the backend always
    re-reads the role from the database.
    """
    issued_at = now or utcnow()
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": ACCESS_TOKEN_TYPE,
        "iss": TOKEN_ISSUER,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> int:
    """Validate signature, expiry, issuer and type; return the user id."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=TOKEN_ISSUER,
            options={"require": ["sub", "exp", "iat", "iss", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("Not an access token")
    try:
        return int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise TokenError("Invalid subject") from exc
