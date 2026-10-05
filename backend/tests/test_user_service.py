"""Controlled account creation and the database constraints behind it."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.permissions import Role
from app.models import User
from app.services.user_service import UserValidationError, create_user
from tests.conftest import TEST_DOMAIN


def make(db, settings, **overrides):
    values = {
        "name": "Someone",
        "email": f"someone@{TEST_DOMAIN}",
        "password": "a-long-enough-password",
        "role": Role.VIEWER,
    }
    values.update(overrides)
    return create_user(db, settings, **values)


def test_email_is_stored_lowercase(db, settings):
    user = make(db, settings, email=f"Some.One@{TEST_DOMAIN.upper()}")
    assert user.email == f"some.one@{TEST_DOMAIN}"


def test_password_is_stored_only_as_hash(db, settings):
    user = make(db, settings)
    assert "a-long-enough-password" not in user.password_hash
    assert "password" not in repr(user)


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "someone@gmail.com"},
        {"email": "not-an-email"},
        {"password": "short"},
        {"role": "superuser"},
        {"name": "   "},
        {"role": Role.STUDENT},  # no department
        {"role": Role.DEPARTMENT_AUTHORITY, "department_id": None, "authority_level": None},
        {"role": Role.HIGHER_AUTHORITY, "authority_level": 0},
        {"role": Role.VIEWER, "authority_level": 2},
        {"role": Role.ADMIN, "department_id": 999},
    ],
)
def test_invalid_accounts_are_refused(db, settings, department, overrides):
    with pytest.raises(UserValidationError):
        make(db, settings, **overrides)


def test_duplicate_email_is_refused(db, settings):
    make(db, settings)
    with pytest.raises(UserValidationError):
        make(db, settings, email=f"SOMEONE@{TEST_DOMAIN}")


def test_no_accounts_can_be_created_without_configured_domains(db, settings):
    unconfigured = settings.model_copy(update={"allowed_email_domains": ""})
    with pytest.raises(UserValidationError):
        make(db, unconfigured)


@pytest.mark.parametrize(
    "fields",
    [
        {"role": "superuser"},
        {"role": "viewer", "email": f"UPPER@{TEST_DOMAIN}"},
        {"role": "student"},  # department missing
        {"role": "higher_authority"},  # level missing
        {"role": "viewer", "authority_level": 1},
    ],
)
def test_database_constraints_block_invalid_rows_that_bypass_the_service(db, fields):
    values = {"name": "Bypass", "email": f"bypass@{TEST_DOMAIN}", "password_hash": "x"}
    db.add(User(**{**values, **fields}))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
