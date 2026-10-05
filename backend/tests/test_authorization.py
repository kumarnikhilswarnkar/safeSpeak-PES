"""Backend authorization: the database role decides, whatever the client sends."""
import pytest

from app.core.permissions import Role
from app.core.security import create_access_token
from tests.conftest import TEST_DOMAIN, TEST_PASSWORD, bearer

ADMIN_USERS = "/api/v1/admin/users"
ME = "/api/v1/auth/me"


def test_admin_can_list_users(client, make_user, login):
    admin = make_user(Role.ADMIN)
    make_user(Role.STUDENT)

    response = client.get(ADMIN_USERS, headers=bearer(login(admin.email)))

    assert response.status_code == 200
    assert {u["role"] for u in response.json()} == {"admin", "student"}


@pytest.mark.parametrize(
    "role",
    [r for r in Role if r is not Role.ADMIN],
)
def test_every_non_admin_role_is_forbidden_from_user_management(client, make_user, login, role):
    user = make_user(role)

    response = client.get(ADMIN_USERS, headers=bearer(login(user.email)))

    assert response.status_code == 403


def test_user_management_requires_authentication(client):
    assert client.get(ADMIN_USERS).status_code == 401


def test_login_rejects_client_supplied_role(client, make_user):
    make_user(Role.STUDENT)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"student@{TEST_DOMAIN}", "password": TEST_PASSWORD, "role": "admin"},
    )

    assert response.status_code == 422


def test_role_in_query_or_headers_is_ignored(client, make_user, login):
    student = make_user(Role.STUDENT)
    token = login(student.email)
    headers = {**bearer(token), "X-Role": "admin", "X-User-Role": "admin"}

    me = client.get(ME, params={"role": "admin"}, headers=headers)
    admin_area = client.get(ADMIN_USERS, params={"role": "admin"}, headers=headers)

    assert me.json()["role"] == "student"
    assert admin_area.status_code == 403


def test_validly_signed_token_claiming_admin_does_not_grant_admin(client, settings, make_user):
    """Even a correctly signed token whose role claim says 'admin' (for example,
    issued before the account's role changed) is overruled by the database."""
    student = make_user(Role.STUDENT)
    token, _ = create_access_token(student.id, "admin", settings)

    assert client.get(ME, headers=bearer(token)).json()["role"] == "student"
    assert client.get(ADMIN_USERS, headers=bearer(token)).status_code == 403


def test_role_change_in_database_takes_effect_on_existing_token(client, db, make_user, login):
    admin = make_user(Role.ADMIN)
    token = login(admin.email)
    assert client.get(ADMIN_USERS, headers=bearer(token)).status_code == 200

    admin.role = Role.VIEWER.value
    db.commit()

    assert client.get(ADMIN_USERS, headers=bearer(token)).status_code == 403


def test_password_hash_never_appears_in_responses(client, make_user, login):
    admin = make_user(Role.ADMIN)
    student = make_user(Role.STUDENT)
    token = login(admin.email)

    responses = [
        client.post("/api/v1/auth/login", json={"email": admin.email, "password": TEST_PASSWORD}),
        client.get(ME, headers=bearer(token)),
        client.get(ADMIN_USERS, headers=bearer(token)),
    ]

    for response in responses:
        text = response.text
        assert "password" not in text.lower()
        assert "$2b$" not in text
        assert student.password_hash not in text
        assert admin.password_hash not in text
