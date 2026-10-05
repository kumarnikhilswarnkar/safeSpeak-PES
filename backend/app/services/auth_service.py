"""Login: verify credentials against the database account."""
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import spend_verification_time, verify_password
from app.models import User
from app.services.user_service import get_user_by_email, is_allowed_email_domain


class AuthError(Exception):
    """Base class for login failures. Messages are safe to show to the user."""


class SignInNotConfigured(AuthError):
    """No institutional email domains are configured, so nobody may sign in."""


class EmailDomainNotAllowed(AuthError):
    """The address is not an institutional one. (The domain rule is public, so
    saying so reveals nothing about which accounts exist.)"""


class InvalidCredentials(AuthError):
    """Unknown account or wrong password. Deliberately indistinguishable."""


class AccountDisabled(AuthError):
    """Correct credentials, but the account is deactivated."""


def authenticate(db: Session, settings: Settings, email: str, password: str) -> User:
    if not settings.email_domains:
        raise SignInNotConfigured()
    if not is_allowed_email_domain(email, settings):
        raise EmailDomainNotAllowed()

    user = get_user_by_email(db, email)
    if user is None:
        spend_verification_time(password, settings.bcrypt_rounds)
        raise InvalidCredentials()
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials()
    # Checked only after the password, so it is never revealed to someone who
    # does not already know the credentials.
    if not user.is_active:
        raise AccountDisabled()
    return user
