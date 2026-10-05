"""Login, token validation and /auth/me."""
from datetime import timedelta

import jwt
import pytest

from app.core.permissions import Permission, Role
from app.core.security import create_access_token
from app.core.timeutil import utcnow
from tests.conftest import TEST_DOMAIN, TEST_PASSWORD, TEST_SECRET, bearer

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def decode_claims(token: str) -> dict:
    return jwt.decode(token, TEST_SECRET, algorithms=["HS256"], issuer="safespeak-pes")


# --- login -------------------------------------------------------------------

def test_valid_login_returns_bearer_token(client, make_user):
    make_user(Role.STUDENT)

    response = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    assert set(body) == {"access_token", "token_type", "expires_in"}


def test_login_email_is_case_insensitive(client, make_user):
    make_user(Role.STUDENT)

    response = client.post(LOGIN, json={"email": f"  STUDENT@{TEST_DOMAIN.upper()} ", "password": TEST_PASSWORD})

    assert response.status_code == 200


def test_wrong_password_is_rejected(client, make_user):
    make_user(Role.STUDENT)

    response = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": "wrong-password-123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_unknown_account_gets_same_error_as_wrong_password(client, make_user):
    make_user(Role.STUDENT)

    wrong_password = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": "nope-nope-nope"})
    unknown = client.post(LOGIN, json={"email": f"nobody@{TEST_DOMAIN}", "password": "nope-nope-nope"})

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


def test_inactive_account_is_rejected(client, make_user):
    make_user(Role.STUDENT, is_active=False)

    response = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": TEST_PASSWORD})

    assert response.status_code == 403
    assert response.json()["detail"] == "This account is disabled"


def test_inactive_account_wrong_password_does_not_reveal_status(client, make_user):
    make_user(Role.STUDENT, is_active=False)

    response = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": "wrong-password-123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_non_institutional_email_is_rejected(client):
    response = client.post(LOGIN, json={"email": "someone@gmail.com", "password": TEST_PASSWORD})

    assert response.status_code == 401
    assert "institutional" in response.json()["detail"]


def test_sign_in_refused_when_no_domains_configured(settings, make_user):
    from fastapi.testclient import TestClient

    from app.main import create_app

    make_user(Role.STUDENT)
    unconfigured = settings.model_copy(update={"allowed_email_domains": ""})
    with TestClient(create_app(unconfigured)) as client:
        response = client.post(LOGIN, json={"email": f"student@{TEST_DOMAIN}", "password": TEST_PASSWORD})

    assert response.status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": f"student@{TEST_DOMAIN}"},
        {"password": TEST_PASSWORD},
        {"email": "", "password": ""},
        {"email": 123, "password": ["x"]},
    ],
)
def test_malformed_login_body_is_rejected(client, payload):
    assert client.post(LOGIN, json=payload).status_code == 422


def test_credentials_in_query_string_are_not_accepted(client, make_user):
    make_user(Role.STUDENT)

    response = client.post(LOGIN, params={"email": f"student@{TEST_DOMAIN}", "password": TEST_PASSWORD})

    assert response.status_code == 422


# --- token validation ----------------------------------------------------------

def test_missing_authorization_header_is_401(client):
    response = client.get(ME)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-jwt",
        "Bearer eyJhbGciOiJIUzI1NiJ9.e30.invalid-signature",
        "Basic dXNlcjpwYXNz",
        "Bearer",
    ],
)
def test_malformed_token_is_401(client, header):
    assert client.get(ME, headers={"Authorization": header}).status_code == 401


def test_token_signed_with_another_key_is_401(client, make_user):
    user = make_user(Role.STUDENT)
    forged = jwt.encode(
        {"sub": str(user.id), "role": "student", "typ": "access", "iss": "safespeak-pes",
         "iat": utcnow(), "exp": utcnow() + timedelta(minutes=5)},
        "some-other-secret-key-that-is-long-enough!!",
        algorithm="HS256",
    )
    assert client.get(ME, headers=bearer(forged)).status_code == 401


def test_unsigned_alg_none_token_is_401(client, make_user):
    user = make_user(Role.STUDENT)
    unsigned = jwt.encode(
        {"sub": str(user.id), "role": "admin", "typ": "access", "iss": "safespeak-pes",
         "iat": utcnow(), "exp": utcnow() + timedelta(minutes=5)},
        None,
        algorithm="none",
    )
    assert client.get(ME, headers=bearer(unsigned)).status_code == 401


def test_expired_token_is_401(client, settings, make_user):
    user = make_user(Role.STUDENT)
    token, _ = create_access_token(user.id, user.role, settings, now=utcnow() - timedelta(hours=2))

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_token_for_deleted_user_is_401(client, settings, db, make_user):
    user = make_user(Role.STUDENT)
    token, _ = create_access_token(user.id, user.role, settings)
    db.delete(user)
    db.commit()

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_token_stops_working_once_account_is_deactivated(client, db, make_user, login):
    user = make_user(Role.STUDENT)
    token = login(user.email)
    user.is_active = False
    db.commit()

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == 403


# --- /auth/me --------------------------------------------------------------------

def test_me_with_valid_token_returns_safe_profile(client, make_user, login):
    user = make_user(Role.STUDENT)

    response = client.get(ME, headers=bearer(login(user.email)))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id", "name", "email", "role", "department", "authority_level", "is_active", "permissions",
    }
    assert body["email"] == f"student@{TEST_DOMAIN}"
    assert body["department"]["code"] == "MCA"
    assert body["is_active"] is True


def test_me_without_token_is_401(client):
    assert client.get(ME).status_code == 401


@pytest.mark.parametrize("role", [Role.STUDENT, Role.TEACHING_STAFF, Role.ADMIN])
def test_token_and_me_carry_the_account_role(client, make_user, login, role):
    user = make_user(role)
    token = login(user.email)

    assert decode_claims(token)["role"] == role.value
    assert client.get(ME, headers=bearer(token)).json()["role"] == role.value


def test_token_contains_only_minimal_claims(make_user, login):
    user = make_user(Role.STUDENT)

    claims = decode_claims(login(user.email))

    assert set(claims) == {"sub", "role", "typ", "iss", "iat", "exp"}
    assert claims["sub"] == str(user.id)


def test_authority_profile_includes_level(client, make_user, login):
    user = make_user(Role.DEPARTMENT_AUTHORITY)

    body = client.get(ME, headers=bearer(login(user.email))).json()

    assert body["authority_level"] == 1
    assert Permission.SUBMIT_COMPLAINT in body["permissions"]
    assert Permission.REVIEW_COMPLAINTS in body["permissions"]


def test_viewer_receives_no_modification_permissions(client, make_user, login):
    user = make_user(Role.VIEWER)

    permissions = client.get(ME, headers=bearer(login(user.email))).json()["permissions"]

    assert permissions == [Permission.VIEW_SCOPED_COMPLAINTS]
