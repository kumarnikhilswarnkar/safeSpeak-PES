#!/bin/sh
# Wait until the database accepts connections, then run the given command
# (uvicorn for the API, "alembic upgrade head" for the migrate job, or a seed script).
set -eu

python - <<'PY'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
if not url.startswith("postgresql"):
    sys.exit(0)  # SQLite needs no waiting
for attempt in range(60):
    try:
        engine = create_engine(url, hide_parameters=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        sys.exit(0)
    except Exception as exc:  # never print the URL: it contains the password
        print(f"waiting for database ({type(exc).__name__})...", flush=True)
        time.sleep(2)
print("database not reachable after 120 s", file=sys.stderr)
sys.exit(1)
PY

exec "$@"
