"""Create .env for the Docker Compose stack from .env.example, filling every
empty secret with a fresh random value. Secrets are written only to .env
(git-ignored) and never printed.

    python scripts/generate_env.py              # refuses to overwrite an existing .env
    python scripts/generate_env.py --if-missing # no-op if .env exists (Codespaces/CI)
    python scripts/generate_env.py --set KEY=VALUE ...   # override non-secret values
"""
import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = {
    "POSTGRES_SUPERUSER_PASSWORD": 24,
    "OWNER_DB_PASSWORD": 24,
    "APP_DB_PASSWORD": 24,
    "JWT_SECRET_KEY": 48,
    "DEMO_PASSWORD": 12,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-missing", action="store_true")
    parser.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    parser.add_argument("--output", default=str(ROOT / ".env"))
    args = parser.parse_args()

    target = Path(args.output)
    if target.exists():
        if args.if_missing:
            print(f"{target.name} already exists; left unchanged.")
            return 0
        print(f"{target} already exists; delete it first to regenerate.", file=sys.stderr)
        return 1

    overrides = dict(item.split("=", 1) for item in args.set)
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            key = key.strip()
            if key in overrides:
                value = overrides.pop(key)
            elif key in SECRET_KEYS and not value:
                # URL-safe characters only: the passwords are embedded in database URLs.
                value = secrets.token_urlsafe(SECRET_KEYS[key])
            line = f"{key}={value}"
        lines.append(line)
    for key, value in overrides.items():
        lines.append(f"{key}={value}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target} with new random secrets (not shown). Demo password: see DEMO_PASSWORD in that file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
