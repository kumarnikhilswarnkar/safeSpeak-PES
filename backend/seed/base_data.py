"""Seed the base data every deployment needs: departments/offices, TAT rules
and escalation chains. Creates NO user accounts (see seed.demo_users for
development/demo accounts). Idempotent: existing rows are left unchanged.

These are SAMPLE values for the prototype (labelled "sample"), not the real
PES hierarchy; an institution replaces them with its own rows.

Usage, after `alembic upgrade head`:
    python -m seed.base_data
"""
import sys

from sqlalchemy import inspect, select

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models import Department
from seed.demo_users import SAMPLE_DEPARTMENTS
from seed.prototype_rules import seed_demo_routing, seed_prototype_rules


def main() -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    if not inspect(engine).has_table("departments"):
        print("Database tables are missing. Run `alembic upgrade head` first.", file=sys.stderr)
        return 1
    with create_session_factory(engine)() as db:
        departments, added_departments = {}, 0
        for code, name, kind in SAMPLE_DEPARTMENTS:
            dept = db.scalar(select(Department).where(Department.code == code))
            if dept is None:
                dept = Department(code=code, name=name, kind=kind.value)
                db.add(dept)
                db.flush()
                added_departments += 1
            departments[code] = dept
        tat_added, chain_added = seed_prototype_rules(db)
        chain_added += seed_demo_routing(db, departments)
        db.commit()
    engine.dispose()
    print(
        f"Base data: {added_departments} department(s), {tat_added} TAT rule(s), "
        f"{chain_added} escalation rule(s) added (existing rows unchanged)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
