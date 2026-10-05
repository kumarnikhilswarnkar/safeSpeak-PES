"""Shared setup for complaint-workflow tests: sample rules, a small
organisation, and a controllable stand-in for the AI model."""
from dataclasses import dataclass

import pytest

from app.core.permissions import Role
from app.models import Department, DepartmentKind
from app.services.triage_service import TriageResult
from app.services.user_service import create_user
from seed.prototype_rules import seed_prototype_rules
from tests.conftest import TEST_DOMAIN, TEST_PASSWORD, bearer

CONCERNS = "/api/v1/concerns"
DESCRIPTION = "The projector in lab 3 has not worked for two weeks."


class StubTriageModel:
    """Returns whatever prediction the test sets; the real model is tested separately."""

    name = "stub"
    version = "test"
    recommended_threshold = 0.3

    def __init__(self):
        self.set("Infrastructure and facilities", 0.9, "Medium", 0.9)

    def set(self, category, category_confidence, priority, priority_confidence):
        self.result = TriageResult(
            model_name=self.name,
            model_version=self.version,
            category=category,
            category_confidence=category_confidence,
            priority=priority,
            priority_confidence=priority_confidence,
            probabilities={"category": {category: category_confidence}, "priority": {priority: priority_confidence}},
        )

    def predict(self, text):
        return self.result


@dataclass
class World:
    model: StubTriageModel
    users: dict
    tokens: dict

    def h(self, who: str) -> dict:
        return bearer(self.tokens[who])


@pytest.fixture
def world(app, db, settings, client) -> World:
    mca = Department(code="MCA", name="Computer Applications", kind=DepartmentKind.ACADEMIC.value)
    cse = Department(code="CSE", name="Computer Science", kind=DepartmentKind.ACADEMIC.value)
    db.add_all([mca, cse])
    db.flush()
    seed_prototype_rules(db)

    specs = {
        "student": (Role.STUDENT, mca.id, None),
        "student2": (Role.STUDENT, mca.id, None),
        "teaching": (Role.TEACHING_STAFF, mca.id, None),
        "authority": (Role.DEPARTMENT_AUTHORITY, mca.id, 1),
        "authority_cse": (Role.DEPARTMENT_AUTHORITY, cse.id, 1),
        "dean": (Role.HIGHER_AUTHORITY, None, 3),
        "director": (Role.HIGHER_AUTHORITY, None, 4),
        "viewer": (Role.VIEWER, None, None),
        "viewer_cse": (Role.VIEWER, cse.id, None),
        "admin": (Role.ADMIN, None, None),
    }
    users = {}
    for key, (role, dept_id, level) in specs.items():
        users[key] = create_user(
            db, settings,
            name=key.replace("_", " ").title(),
            email=f"{key}@{TEST_DOMAIN}",
            password=TEST_PASSWORD,
            role=role,
            department_id=dept_id,
            authority_level=level,
        )
    db.commit()

    model = StubTriageModel()
    app.state.triage_model = model

    tokens = {}
    for key, user in users.items():
        response = client.post("/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
        tokens[key] = response.json()["access_token"]
    return World(model=model, users=users, tokens=tokens)


def submit(client, world: World, who: str = "student", description: str = DESCRIPTION) -> dict:
    response = client.post(CONCERNS, json={"description": description}, headers=world.h(who))
    assert response.status_code == 201, response.text
    return response.json()


def actions(complaint: dict) -> list[str]:
    return [e["action"] for e in complaint["events"]]
