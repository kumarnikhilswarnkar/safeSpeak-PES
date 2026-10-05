"""List every complaint stored in the application database (READ-ONLY, for the demo).

Usage, from the backend folder:

    .venv/Scripts/python scripts/list_complaints.py

Opens backend/safespeak_dev.db in SQLite read-only mode and runs SELECT queries
only. Prints the total number of complaints, a count per status, the number of
stored AI predictions and audit events, and one table row per complaint.
From the users table it reads only the assignee's name: no emails, password
hashes, tokens or other credentials are printed. Times are stored in UTC and
shown here in IST.
"""
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).resolve().parents[1] / "safespeak_dev.db"
IST = ZoneInfo("Asia/Kolkata")
TEXT_WIDTH = 42

QUERY = """
SELECT c.complaint_code, c.description, c.category, c.priority, c.status,
       u.name AS assigned_to, c.deadline_at
FROM complaints AS c
LEFT JOIN users AS u ON u.id = c.assigned_user_id
ORDER BY c.id
"""


def to_ist(value: str | None) -> str:
    if not value:
        return "-"
    stored = datetime.fromisoformat(value).replace(tzinfo=UTC)
    return stored.astimezone(IST).strftime("%d %b %Y %H:%M")


def short(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    # mode=ro: SQLite refuses any write through this connection.
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        total = con.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        by_status = con.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status ORDER BY status").fetchall()
        predictions = con.execute("SELECT COUNT(*) FROM ai_predictions").fetchone()[0]
        events = con.execute("SELECT COUNT(*) FROM complaint_events").fetchone()[0]
        rows = con.execute(QUERY).fetchall()
    finally:
        con.close()

    print(f"Database: {DB_PATH}  (opened read-only)")
    print(f"Total complaints: {total}")
    print("By status: " + (", ".join(f"{s} {n}" for s, n in by_status) or "none"))
    print(f"AI predictions stored: {predictions}   Audit events stored: {events}\n")

    headers = ["Complaint ID", "Complaint Text", "Category", "Priority", "Status", "Assigned User", "Deadline (IST)"]
    table = [
        [code, short(text, TEXT_WIDTH), category, priority, status, assigned or "-", to_ist(deadline)]
        for code, text, category, priority, status, assigned, deadline in rows
    ]
    widths = [max(len(h), *(len(r[i]) for r in table)) if table else len(h) for i, h in enumerate(headers)]
    line = "  ".join("-" * w for w in widths)
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print(line)
    for r in table:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))
    if not table:
        print("(no complaints yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
