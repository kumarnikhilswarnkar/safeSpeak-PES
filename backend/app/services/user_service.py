"""User accounts: email rules and controlled account creation.

There is no public sign-up. Accounts are created by the seed script now and by
the admin user-management screens later, both through create_user().
"""
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import AUTHORITY_ROLES, DEPARTMENT_REQUIRED_ROLES, Role
from app.core.security import MAX_PASSWORD_BYTES, hash_password
from app.models import Department, User

MIN_PASSWORD_LENGTH = 10


class UserValidationError(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_domain(email: str) -> str:
    return email.rpartition("@")[2]


def is_allowed_email_domain(email: str, settings: Settings) -> bool:
    """Exact domain match against ALLOWED_EMAIL_DOMAINS; subdomains are not implied.
    With no domains configured, nothing is allowed."""
    return email_domain(normalize_email(email)) in settings.email_domains


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(
    db: Session,
    settings: Settings,
    *,
    name: str,
    email: str,
    password: str,
    role: Role | str,
    department_id: int | None = None,
    authority_level: int | None = None,
    is_active: bool = True,
) -> User:
    """Validate and add a new account to the session (the caller commits)."""
    try:
        role = Role(role)
    except ValueError as exc:
        raise UserValidationError(f"Unknown role: {role}") from exc

    name = name.strip()
    if not name:
        raise UserValidationError("Name is required")

    try:
        # Reserved test domains (e.g. *.test) are allowed outside production for demo accounts.
        email = validate_email(
            normalize_email(email),
            check_deliverability=False,
            test_environment=not settings.is_production,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise UserValidationError(f"Invalid email address: {exc}") from exc
    if not settings.email_domains:
        raise UserValidationError("No institutional email domains are configured (ALLOWED_EMAIL_DOMAINS)")
    if not is_allowed_email_domain(email, settings):
        raise UserValidationError("Email must use an allowed institutional domain")
    if get_user_by_email(db, email) is not None:
        raise UserValidationError("An account with this email already exists")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise UserValidationError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")

    if role in AUTHORITY_ROLES:
        if authority_level is None or authority_level < 1:
            raise UserValidationError("Authority roles require an authority level of 1 or higher")
    elif authority_level is not None:
        raise UserValidationError("Only authority roles can have an authority level")

    if role in DEPARTMENT_REQUIRED_ROLES and department_id is None:
        raise UserValidationError(f"Role {role} requires a department")
    if department_id is not None and db.get(Department, department_id) is None:
        raise UserValidationError("Department does not exist")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password, settings.bcrypt_rounds),
        role=role.value,
        department_id=department_id,
        authority_level=authority_level,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user
