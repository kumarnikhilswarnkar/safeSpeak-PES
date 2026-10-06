"""End-to-end smoke test against a running SafeSpeak stack (Docker, Codespaces, CI).

    python scripts/smoke_test.py http://localhost:8080
    python scripts/smoke_test.py http://127.0.0.1:8000 --no-proxy     # backend only

Reads DEMO_PASSWORD (and ALLOWED_EMAIL_DOMAINS) from the environment; never
prints passwords or tokens. Requires the seeded demo accounts. Exit code 0 only
if every check passes.

Checks: proxy and backend health, database and model loaded, login, complaint
submission, AI category/priority/confidence, stored audit events, human-review
decision for a vague complaint, admin read access, TAT monitor running, and
(when DEMO_MODE is on) automatic escalation after a simulated TAT breach.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

NORMAL = "The projector in classroom 052 has not been working for two weeks."
VAGUE = "There is some issue, please check."
CATEGORIES = {
    "Hostel", "Exam", "Academic / Department", "Infrastructure and facilities",
    "Safety and welfare", "Administrative / Fees", "Library / Transport", "Other",
}
PRIORITIES = {"Low", "Medium", "High", "Critical"}

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}", flush=True)
    if not ok:
        failures.append(label)
    return ok


def request(base: str, method: str, path: str, token: str | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw and raw[:1] in b"[{" else raw.decode())
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, raw.decode(errors="replace")


def login(base: str, email: str, password: str) -> str | None:
    status, body = request(base, "POST", "/api/v1/auth/login", body={"email": email, "password": password})
    return body.get("access_token") if status == 200 and isinstance(body, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--no-proxy", action="store_true", help="target the backend directly (skip /healthz)")
    parser.add_argument("--escalation-wait", type=int, default=int(os.environ.get("SMOKE_ESCALATION_WAIT", "90")))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    password = os.environ.get("DEMO_PASSWORD")
    domain = (os.environ.get("ALLOWED_EMAIL_DOMAINS") or "safespeak.test").split(",")[0].strip()
    if not password:
        print("DEMO_PASSWORD is not set (see .env).", file=sys.stderr)
        return 2

    if not args.no_proxy:
        status, _ = request(base, "GET", "/healthz")
        check(status == 200, "reverse proxy /healthz", str(status))
    status, health = request(base, "GET", "/api/v1/health")
    check(status == 200 and health.get("database") == "ok", "backend health: database ok", f"{status}")
    model = health.get("triage_model") if isinstance(health, dict) else None
    check(bool(model) and model != "unavailable", "backend health: ML model loaded in backend container", str(model))

    student = login(base, f"demo.student@{domain}", password)
    if not check(student is not None, "student login (JWT issued)"):
        return 1

    status, created = request(base, "POST", "/api/v1/concerns", student, {"description": NORMAL})
    if not check(status == 201, "complaint submitted", f"{status} {created.get('complaint_id') if isinstance(created, dict) else ''}"):
        return 1
    code, ai = created["complaint_id"], created["ai"]
    check(ai["category"] in CATEGORIES and ai["priority"] in PRIORITIES, "AI category/priority predicted",
          f"{ai['category']} / {ai['priority']} by {ai['model']}")
    check(0 < ai["category_confidence"] <= 1 and 0 < ai["priority_confidence"] <= 1, "AI confidences in (0, 1]",
          f"category {ai['category_confidence']:.2f}, priority {ai['priority_confidence']:.2f}, threshold {ai['threshold']}")
    print(f"       decision: {'human review' if ai['flagged_for_review'] else 'automatic'}; status {created['status']}")

    status, detail = request(base, "GET", f"/api/v1/concerns/{code}", student)
    actions = [e["action"] for e in detail.get("events", [])] if status == 200 else []
    check({"complaint_created", "ai_triaged", "assigned"} <= set(actions), "audit events stored", ", ".join(actions))

    status, vague = request(base, "POST", "/api/v1/concerns", student, {"description": VAGUE})
    if check(status == 201, "second (vague) complaint submitted"):
        flagged = vague["ai"]["flagged_for_review"]
        print(f"       vague complaint {vague['complaint_id']}: confidence {vague['ai']['confidence']:.2f} "
              f"-> {'human review' if flagged else 'automatic'} ({vague['status']})")

    admin = login(base, f"demo.admin@{domain}", password)
    if not check(admin is not None, "admin login"):
        return 1
    status, overview = request(base, "GET", "/api/v1/analytics/overview", admin)
    check(status == 200 and overview["totals"]["total"] >= 2, "admin overview reads stored complaints",
          f"total {overview['totals']['total'] if status == 200 else '?'}")
    status, automation = request(base, "GET", "/api/v1/system/automation", admin)
    check(status == 200 and automation.get("running") is True, "automatic TAT monitor running",
          f"every {automation.get('interval_seconds')} s" if status == 200 else str(status))

    status, _ = request(base, "POST", f"/api/v1/concerns/{code}/simulate_breach", admin)
    if status == 404:
        print("       DEMO_MODE is off: TAT breach simulation skipped (escalation is covered by backend tests).")
    elif check(status == 200, "TAT breach simulated (demo mode)"):
        deadline = time.time() + args.escalation_wait
        escalated = None
        while time.time() < deadline:
            status, detail = request(base, "GET", f"/api/v1/concerns/{code}", admin)
            history = detail.get("escalation", {}).get("history", []) if status == 200 else []
            if history:
                escalated = history[0]
                break
            time.sleep(3)
        check(escalated is not None and escalated["automatic"], "automatic escalation by the TAT monitor (no manual trigger)",
              f"L{escalated['from_level']} -> L{escalated['to_level']}" if escalated else f"none within {args.escalation_wait} s")

    print(f"\n{'SMOKE TEST PASSED' if not failures else 'SMOKE TEST FAILED: ' + '; '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
