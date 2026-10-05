"""Show the database record for one complaint (READ-ONLY, for the demo).

Usage, from the backend folder:

    .venv/Scripts/python scripts/show_complaint.py SSP-2026-000004

Opens the application database (backend/safespeak_dev.db) in SQLite read-only
mode and prints the raw rows stored for that complaint: the `complaints` row,
its `ai_predictions` row and its `complaint_events` (audit trail). It cannot
change or delete anything, and it does not read the users table, so no
passwords or other credentials are printed.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "safespeak_dev.db"

COMPLAINT_COLUMNS = [
    "id", "complaint_code", "complainant_id", "complainant_role", "description",
    "category", "priority", "decision_source", "status", "review_reasons",
    "assigned_user_id", "escalation_level", "escalated", "tat_stage", "tat_rule_id",
    "tat_hours", "deadline_at", "resolved_at", "created_at",
]
PREDICTION_COLUMNS = [
    "id", "complaint_id", "model_name", "model_version", "category", "category_confidence",
    "priority", "priority_confidence", "confidence", "threshold", "threshold_source",
    "flagged_for_review", "flag_reasons", "created_at",
]
EVENT_COLUMNS = ["id", "action", "actor_user_id", "actor_role", "created_at"]


def print_row(title: str, columns: list[str], row: sqlite3.Row) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    width = max(len(c) for c in columns)
    for column in columns:
        print(f"  {column:<{width}}  {row[column]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show one complaint's stored database rows (read-only).")
    parser.add_argument("complaint_code", help="visible complaint ID, e.g. SSP-2026-000004")
    code = parser.parse_args().complaint_code.strip()

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    # mode=ro: SQLite refuses any write through this connection.
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        complaint = con.execute(
            f"SELECT {', '.join(COMPLAINT_COLUMNS)} FROM complaints WHERE complaint_code = ?", (code,)
        ).fetchone()
        if complaint is None:
            print(f"No complaint with ID {code} in {DB_PATH.name}", file=sys.stderr)
            return 1

        print(f"Database: {DB_PATH}  (opened read-only)")
        print_row(f"Table complaints  (complaint_code = {code})", COMPLAINT_COLUMNS, complaint)

        prediction = con.execute(
            f"SELECT {', '.join(PREDICTION_COLUMNS)} FROM ai_predictions WHERE complaint_id = ?",
            (complaint["id"],),
        ).fetchone()
        if prediction is not None:
            print_row(f"Table ai_predictions  (complaint_id = {complaint['id']})", PREDICTION_COLUMNS, prediction)

        events = con.execute(
            f"SELECT {', '.join(EVENT_COLUMNS)} FROM complaint_events WHERE complaint_id = ? ORDER BY id",
            (complaint["id"],),
        ).fetchall()
        title = f"Table complaint_events  (complaint_id = {complaint['id']}, {len(events)} rows)"
        print(f"\n{title}\n{'-' * len(title)}")
        for e in events:
            actor = f"user {e['actor_user_id']} ({e['actor_role']})" if e["actor_user_id"] else "SYSTEM"
            print(f"  #{e['id']:<4} {e['created_at']}  {e['action']:<22} by {actor}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
