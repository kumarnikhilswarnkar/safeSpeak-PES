"""Roles and the permissions each role grants.

This table is the only place role capabilities are defined. The backend checks
it on every protected request; the frontend receives a copy through /auth/me
purely to decide what to display.

Permissions describe *what kind* of action a role may take. Whether a specific
complaint is in the user's scope (own, assigned, department, escalated to them)
is checked separately by the services that own that data.
"""
from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    TEACHING_STAFF = "teaching_staff"
    NON_TEACHING_STAFF = "non_teaching_staff"
    DEPARTMENT_AUTHORITY = "department_authority"
    HIGHER_AUTHORITY = "higher_authority"
    VIEWER = "viewer"
    ADMIN = "admin"


class Permission(StrEnum):
    SUBMIT_COMPLAINT = "submit_complaint"
    VIEW_OWN_COMPLAINTS = "view_own_complaints"
    VIEW_ASSIGNED_COMPLAINTS = "view_assigned_complaints"
    REVIEW_COMPLAINTS = "review_complaints"
    REROUTE_COMPLAINTS = "reroute_complaints"
    RESOLVE_COMPLAINTS = "resolve_complaints"
    VIEW_SCOPED_COMPLAINTS = "view_scoped_complaints"  # read-only
    MANAGE_USERS = "manage_users"
    MANAGE_RULES_AND_SETTINGS = "manage_rules_and_settings"


# Authority roles hold an authority level (L1, L2, ...) in the configured hierarchy.
AUTHORITY_ROLES = frozenset({Role.DEPARTMENT_AUTHORITY, Role.HIGHER_AUTHORITY})

# Roles that must belong to a department (academic department or office).
DEPARTMENT_REQUIRED_ROLES = frozenset(
    {Role.STUDENT, Role.TEACHING_STAFF, Role.NON_TEACHING_STAFF, Role.DEPARTMENT_AUTHORITY}
)

_COMPLAINANT = frozenset({Permission.SUBMIT_COMPLAINT, Permission.VIEW_OWN_COMPLAINTS})
_HANDLER = frozenset(
    {
        Permission.VIEW_ASSIGNED_COMPLAINTS,
        Permission.REVIEW_COMPLAINTS,
        Permission.REROUTE_COMPLAINTS,
        Permission.RESOLVE_COMPLAINTS,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.STUDENT: _COMPLAINANT,
    Role.TEACHING_STAFF: _COMPLAINANT,
    Role.NON_TEACHING_STAFF: _COMPLAINANT,
    # Authorities can also file their own complaints (decision D3).
    Role.DEPARTMENT_AUTHORITY: _COMPLAINANT | _HANDLER,
    Role.HIGHER_AUTHORITY: _COMPLAINANT | _HANDLER,
    Role.VIEWER: frozenset({Permission.VIEW_SCOPED_COMPLAINTS}),
    Role.ADMIN: frozenset(
        {
            Permission.VIEW_SCOPED_COMPLAINTS,
            Permission.MANAGE_USERS,
            Permission.MANAGE_RULES_AND_SETTINGS,
        }
    ),
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[Role(role)]


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in permissions_for(role)
