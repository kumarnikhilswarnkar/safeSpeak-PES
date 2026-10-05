"""The role → permission matrix matches the approved design."""
import pytest

from app.core.permissions import ROLE_PERMISSIONS, Permission as P, Role, has_permission

COMPLAINANT = {P.SUBMIT_COMPLAINT, P.VIEW_OWN_COMPLAINTS}
HANDLER = {P.VIEW_ASSIGNED_COMPLAINTS, P.REVIEW_COMPLAINTS, P.REROUTE_COMPLAINTS, P.RESOLVE_COMPLAINTS}
MODIFYING = HANDLER - {P.VIEW_ASSIGNED_COMPLAINTS} | {P.SUBMIT_COMPLAINT, P.MANAGE_USERS, P.MANAGE_RULES_AND_SETTINGS}

EXPECTED = {
    Role.STUDENT: COMPLAINANT,
    Role.TEACHING_STAFF: COMPLAINANT,
    Role.NON_TEACHING_STAFF: COMPLAINANT,
    Role.DEPARTMENT_AUTHORITY: COMPLAINANT | HANDLER,
    Role.HIGHER_AUTHORITY: COMPLAINANT | HANDLER,
    Role.VIEWER: {P.VIEW_SCOPED_COMPLAINTS},
    Role.ADMIN: {P.VIEW_SCOPED_COMPLAINTS, P.MANAGE_USERS, P.MANAGE_RULES_AND_SETTINGS},
}


def test_exactly_the_seven_required_roles_exist():
    assert {r.value for r in Role} == {
        "student", "teaching_staff", "non_teaching_staff", "department_authority",
        "higher_authority", "viewer", "admin",
    }


@pytest.mark.parametrize("role", list(Role))
def test_role_permissions_match_design(role):
    assert ROLE_PERMISSIONS[role] == EXPECTED[role]


def test_every_permission_is_granted_to_some_role():
    granted = set().union(*ROLE_PERMISSIONS.values())
    assert granted == set(P)


def test_viewer_has_no_modifying_permission():
    assert not any(has_permission(Role.VIEWER, p) for p in MODIFYING)


@pytest.mark.parametrize("role", [Role.DEPARTMENT_AUTHORITY, Role.HIGHER_AUTHORITY])
def test_authorities_can_also_submit_complaints(role):
    assert has_permission(role, P.SUBMIT_COMPLAINT)


def test_admin_cannot_handle_or_submit_complaints():
    assert not any(has_permission(Role.ADMIN, p) for p in COMPLAINANT | HANDLER)
