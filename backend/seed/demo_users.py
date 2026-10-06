"""Create SAMPLE departments, DEMO accounts for every role, and the SAMPLE
TAT/escalation rules (development only).

Usage, from the backend folder, after `alembic upgrade head`:

    python -m seed.demo_users                    # create anything missing
    python -m seed.demo_users --reset-passwords  # also issue new passwords for existing demo users

Passwords are random unless DEMO_PASSWORD is set in the environment. They are
written only to the git-ignored file backend/demo_credentials.local.txt; the
database stores bcrypt hashes. Departments and accounts here are illustrative
sample data, not the real institutional structure.
"""
import argparse
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, select

from app.core.config import BACKEND_DIR, get_settings
from app.core.permissions import Role
from app.core.security import hash_password
from app.db.session import create_db_engine, create_session_factory
from app.models import Department, DepartmentKind, User
from app.services.user_service import create_user
from seed.prototype_rules import seed_demo_routing, seed_prototype_rules

# Git-ignored local file; containers point DEMO_CREDENTIALS_FILE at a path inside the container.
CREDENTIALS_FILE = Path(os.environ.get("DEMO_CREDENTIALS_FILE") or BACKEND_DIR / "demo_credentials.local.txt")

SAMPLE_DEPARTMENTS = [
    ("MCA", "Department of Computer Applications (sample)", DepartmentKind.ACADEMIC),
    ("CSE", "Department of Computer Science (sample)", DepartmentKind.ACADEMIC),
    ("FACILITIES", "Facilities Office (sample)", DepartmentKind.OFFICE),
]


@dataclass(frozen=True)
class DemoUser:
    local_part: str
    name: str
    role: Role
    department_code: str | None = None
    authority_level: int | None = None
    is_active: bool = True


DEMO_USERS = [
    DemoUser("demo.student", "Demo Student", Role.STUDENT, "MCA"),
    DemoUser("demo.teaching", "Demo Teaching Staff", Role.TEACHING_STAFF, "MCA"),
    DemoUser("demo.nonteaching", "Demo Non-Teaching Staff", Role.NON_TEACHING_STAFF, "FACILITIES"),
    DemoUser("demo.authority", "Demo Department Authority (L1)", Role.DEPARTMENT_AUTHORITY, "MCA", 1),
    # A second L1 authority in another department: a valid reroute target in the demo.
    DemoUser("demo.authority.cse", "Demo CSE Department Authority (L1)", Role.DEPARTMENT_AUTHORITY, "CSE", 1),
    # Facilities Office authority: receives Infrastructure complaints (sample office chain).
    DemoUser("demo.facilities", "Demo Facilities Office Authority (L1)", Role.DEPARTMENT_AUTHORITY, "FACILITIES", 1),
    DemoUser("demo.higher", "Demo Higher Authority (L3)", Role.HIGHER_AUTHORITY, None, 3),
    DemoUser("demo.director", "Demo Director (L4)", Role.HIGHER_AUTHORITY, None, 4),
    DemoUser("demo.viewer", "Demo Viewer", Role.VIEWER),
    DemoUser("demo.admin", "Demo Admin", Role.ADMIN),
    # Lets the demo show that a deactivated account is refused.
    DemoUser("demo.inactive", "Demo Inactive Student", Role.STUDENT, "MCA", is_active=False),
]


def _password() -> str:
    return os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)


def seed(reset_passwords: bool) -> int:
    settings = get_settings()
    if settings.is_production:
        print("Refusing to create demo accounts in production.", file=sys.stderr)
        return 1
    if not settings.email_domains:
        print("Set ALLOWED_EMAIL_DOMAINS in backend/.env before seeding demo accounts.", file=sys.stderr)
        return 1
    domain = settings.email_domains[0]

    engine = create_db_engine(settings.database_url)
    if not inspect(engine).has_table("users"):
        print("Database tables are missing. Run `alembic upgrade head` first.", file=sys.stderr)
        return 1

    issued: list[tuple[DemoUser, str, str]] = []
    with create_session_factory(engine)() as db:
        departments = {}
        for code, name, kind in SAMPLE_DEPARTMENTS:
            dept = db.scalar(select(Department).where(Department.code == code))
            if dept is None:
                dept = Department(code=code, name=name, kind=kind.value)
                db.add(dept)
                db.flush()
            departments[code] = dept

        for demo in DEMO_USERS:
            email = f"{demo.local_part}@{domain}"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                password = _password()
                create_user(
                    db,
                    settings,
                    name=demo.name,
                    email=email,
                    password=password,
                    role=demo.role,
                    department_id=departments[demo.department_code].id if demo.department_code else None,
                    authority_level=demo.authority_level,
                    is_active=demo.is_active,
                )
                issued.append((demo, email, password))
            elif reset_passwords:
                password = _password()
                user.password_hash = hash_password(password, settings.bcrypt_rounds)
                issued.append((demo, email, password))

        tat_added, chain_added = seed_prototype_rules(db)
        chain_added += seed_demo_routing(db, departments)
        db.commit()
    engine.dispose()

    if tat_added or chain_added:
        print(f"Added {tat_added} sample TAT rule(s) and {chain_added} sample escalation rule(s).")
    if not issued:
        print("Demo accounts already exist; nothing changed. Use --reset-passwords to issue new passwords.")
        return 0

    _write_credentials(issued)
    print(f"Created or updated {len(issued)} demo account(s).")
    print(f"Credentials written to {CREDENTIALS_FILE} (git-ignored; do not share or commit).")
    return 0


def _read_credentials() -> dict[str, str]:
    """Existing email -> line entries, so a partial run does not lose earlier passwords."""
    entries = {}
    if CREDENTIALS_FILE.exists():
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and "@" in parts[1]:
                entries[parts[1]] = line
    return entries


def _write_credentials(issued: list[tuple[DemoUser, str, str]]) -> None:
    entries = _read_credentials()
    for demo, email, password in issued:
        status = "active" if demo.is_active else "INACTIVE (login should be refused)"
        entries[email] = f"{demo.role.value:<22} {email:<40} {password}   [{status}]"
    lines = [
        "SafeSpeak PES demo credentials (LOCAL DEVELOPMENT ONLY; git-ignored, never commit)",
        "",
        *(entries[email] for email in sorted(entries)),
    ]
    Path(CREDENTIALS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset-passwords", action="store_true", help="issue new passwords for existing demo users")
    return seed(parser.parse_args().reset_passwords)


if __name__ == "__main__":
    raise SystemExit(main())
