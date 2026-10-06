"""Role x endpoint access matrix, enforced by the backend. Expected codes:
201/200 allowed, 403 role not permitted, 404 complaint outside the caller's
scope (indistinguishable from "does not exist"), 401 not signed in."""
import pytest

from tests.workflow_fixtures import CONCERNS, submit, world  # noqa: F401

ROLES = ("student", "teaching", "authority", "dean", "viewer", "admin", None)


def call(client, world, who, method, path, json=None):
    headers = world.h(who) if who else {}
    return client.request(method, path, json=json, headers=headers).status_code


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        # submit + own complaints: complainant roles and authorities (decision D3), not viewer/admin
        ("POST", CONCERNS, dict(student=201, teaching=201, authority=201, dean=201, viewer=403, admin=403, anon=401)),
        ("GET", f"{CONCERNS}/mine", dict(student=200, teaching=200, authority=200, dean=200, viewer=403, admin=403, anon=401)),
        # handler queues: authorities only
        ("GET", f"{CONCERNS}/queue", dict(student=403, teaching=403, authority=200, dean=200, viewer=403, admin=403, anon=401)),
        ("GET", f"{CONCERNS}/pending-triage", dict(student=403, teaching=403, authority=200, dean=200, viewer=403, admin=403, anon=401)),
        # read-only scoped list: viewer and admin
        ("GET", CONCERNS, dict(student=403, teaching=403, authority=403, dean=403, viewer=200, admin=200, anon=401)),
        # administration
        ("GET", "/api/v1/admin/users", dict(student=403, teaching=403, authority=403, dean=403, viewer=403, admin=200, anon=401)),
        ("POST", f"{CONCERNS}/escalate-overdue", dict(student=403, teaching=403, authority=403, dean=403, viewer=403, admin=200, anon=401)),
        ("POST", "/api/v1/system/automation/run", dict(student=403, teaching=403, authority=403, dean=403, viewer=403, admin=200, anon=401)),
    ],
)
def test_endpoint_matrix(client, world, method, path, expected):
    body = {"description": "The projector in lab 3 has not worked for two weeks."} if method == "POST" and path == CONCERNS else None
    for who in ROLES:
        key = who or "anon"
        assert call(client, world, who, method, path, body) == expected[key], f"{key} {method} {path}"


@pytest.fixture
def assigned(client, world) -> dict:
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world)  # filed by student, assigned to the MCA L1 authority


def test_complaint_level_matrix(client, world, assigned):
    code = assigned["complaint_id"]
    detail = {who or "anon": call(client, world, who, "GET", f"{CONCERNS}/{code}") for who in ROLES}
    assert detail == dict(student=200, teaching=404, authority=200, dean=404, viewer=200, admin=200, anon=401)

    review = {
        who or "anon": call(client, world, who, "POST", f"{CONCERNS}/{code}/review", {"action": "accept"})
        for who in ("student", "teaching", "dean", "viewer", "admin", None)
    }
    # Roles without the permission get 403; an authority it is not assigned to cannot even see it (404).
    assert review == dict(student=403, teaching=403, dean=404, viewer=403, admin=403, anon=401)
    assert call(client, world, "authority", "POST", f"{CONCERNS}/{code}/review", {"action": "accept"}) == 200


def test_teaching_staff_reads_own_complaint_but_not_others(client, world, assigned):
    world.model.set("Academic / Department", 0.9, "Low", 0.9)
    own = submit(client, world, who="teaching")["complaint_id"]
    assert call(client, world, "teaching", "GET", f"{CONCERNS}/{own}") == 200
    assert call(client, world, "teaching", "GET", f"{CONCERNS}/{assigned['complaint_id']}") == 404
    assert call(client, world, "student", "GET", f"{CONCERNS}/{own}") == 404
    mine = client.get(f"{CONCERNS}/mine", headers=world.h("teaching")).json()
    assert [c["complaint_id"] for c in mine] == [own]


def test_client_cannot_modify_complaint_outside_the_workflow(client, world, assigned):
    code = assigned["complaint_id"]
    for method in ("PUT", "PATCH", "DELETE"):
        status = call(client, world, "admin", method, f"{CONCERNS}/{code}", {"status": "RESOLVED"})
        assert status == 405, method
