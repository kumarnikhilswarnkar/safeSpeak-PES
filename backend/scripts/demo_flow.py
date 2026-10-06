"""Review-II demo: one complete grievance workflow against the RUNNING API.

Everything goes through the real HTTP endpoints with real logins: passwords are
sent only in the JSON body of POST /auth/login, and every other call uses the
JWT returned by the server. Nothing is written to the database directly.

Prerequisites (from the backend folder):
    alembic upgrade head
    python -m seed.demo_users          # demo accounts + sample TAT/escalation rules
    DEMO_MODE=true in backend/.env     # enables the TAT breach simulation endpoint
    uvicorn app.main:app               # the API, on port 8000 by default

Run:
    python scripts/demo_flow.py [--base-url http://127.0.0.1:8000]

Passwords are read from the git-ignored demo_credentials.local.txt and are never printed.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CREDENTIALS_FILE = Path(__file__).resolve().parents[1] / "demo_credentials.local.txt"
IST = ZoneInfo("Asia/Kolkata")

NORMAL_TEXT = "Fee receipt for the second semester has not been issued even after payment two weeks ago."
VAGUE_TEXT = "there is some issue, please check"


class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/") + "/api/v1"

    def call(self, method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")


def step(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def when(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def person(p: dict | None) -> str:
    if not p:
        return "-"
    level = f" L{p['authority_level']}" if p.get("authority_level") else ""
    return f"{p['name']} ({p['role']}{level})"


def load_credentials() -> dict[str, str]:
    if not CREDENTIALS_FILE.exists():
        sys.exit(f"Missing {CREDENTIALS_FILE}. Run `python -m seed.demo_users` first.")
    creds = {}
    for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and "@" in parts[1]:
            creds[parts[1].split("@")[0]] = (parts[1], parts[2])
    return creds


def login(api: Api, creds: dict, who: str) -> str:
    email, password = creds[who]
    status, body = api.call("POST", "/auth/login", body={"email": email, "password": password})
    if status != 200:
        sys.exit(f"Login failed for {email}: {status} {body}")
    _, me = api.call("GET", "/auth/me", token=body["access_token"])
    print(f"Logged in as {email} -> role from server: {me['role']}")
    return body["access_token"]


def expect(status: int, wanted: int, body) -> None:
    if status != wanted:
        sys.exit(f"Unexpected response {status} (expected {wanted}): {body}")


def show_complaint(c: dict) -> None:
    ai = c["ai"]
    print(f"Complaint ID     : {c['complaint_id']}")
    print(f"AI category      : {ai['category']}  (confidence {ai['category_confidence']:.3f})")
    print(f"AI priority      : {ai['priority']}  (confidence {ai['priority_confidence']:.3f})")
    print(f"Overall conf.    : {ai['confidence']:.3f}  vs threshold {ai['threshold']} [{ai['threshold_source']}]")
    print(f"Status           : {c['status']}  (human review: {'REQUIRED ' + str(c['review_reasons']) if c['needs_review'] else 'not required'})")
    print(f"Assigned to      : {person(c['assigned_to'])}, escalation level {c['escalation_level']}")
    print(f"TAT              : {c['tat']['stage']} stage, {c['tat']['hours']} h (TAT rule #{c['tat']['rule_id']})")
    print(f"Deadline         : {when(c['tat']['deadline_at'])}  [{c['tat']['state']}]")


def show_event(e: dict) -> None:
    actor = person(e["actor"]) if e["actor"] else "SYSTEM"
    print(f"  - {when(e['created_at'])} | {e['action']:<22} | by {actor}")
    if e["previous_value"]:
        print(f"      previous: {json.dumps(e['previous_value'], default=str)[:160]}")
    if e["new_value"]:
        print(f"      new     : {json.dumps(e['new_value'], default=str)[:160]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    api = Api(parser.parse_args().base_url)
    creds = load_credentials()

    step("0. Server check")
    status, health = api.call("GET", "/health")
    expect(status, 200, health)
    print(f"Database: {health['database']} | AI model: {health['triage_model']} | demo mode: {health['demo_mode']}")
    if not health["demo_mode"]:
        sys.exit("DEMO_MODE is off on the server; set DEMO_MODE=true in backend/.env to run the breach step.")

    step("1. Login (role comes from the server account) and a rejected non-college login")
    student = login(api, creds, "demo.student")
    status, body = api.call("POST", "/auth/login", body={"email": "someone@gmail.com", "password": "anything-123"})
    print(f"Non-college email -> {status} {body['detail']}")

    step("2-7. Submit a routine complaint: ID, AI category/priority/confidence, TAT, routing")
    status, normal = api.call("POST", "/concerns", student, {"description": NORMAL_TEXT})
    expect(status, 201, normal)
    print(f'Text: "{NORMAL_TEXT}"')
    show_complaint(normal)

    step("8. Submit a vague complaint: low confidence -> human review queue with a review TAT")
    status, vague = api.call("POST", "/concerns", student, {"description": VAGUE_TEXT})
    expect(status, 201, vague)
    print(f'Text: "{VAGUE_TEXT}"')
    show_complaint(vague)

    step("9. Authorization: the student cannot review; the assigned authority can")
    status, body = api.call("POST", f"/concerns/{vague['complaint_id']}/review", student, {"action": "accept"})
    print(f"Student tries to review -> {status} {body['detail']}")
    authority = login(api, creds, "demo.authority")
    status, body = api.call(
        "POST", f"/concerns/{vague['complaint_id']}/review", authority,
        {"action": "accept", "reviewer_id": 999, "role": "admin"},
    )
    print(f"Request with forged reviewer_id/role fields -> {status} (rejected: identity comes only from the token)")
    _, pending = api.call("GET", "/concerns/pending-triage", authority)
    print(f"Authority's human-review queue: {[c['complaint_id'] for c in pending]}")

    step("10. Reviewer actions: accept, override, reroute")
    status, accepted = api.call(
        "POST", f"/concerns/{normal['complaint_id']}/review", authority,
        {"action": "accept", "remarks": "AI recommendation is correct"},
    )
    expect(status, 200, accepted)
    print(f"ACCEPT   {normal['complaint_id']}: decision = {accepted['decision_source']}")

    status, overridden = api.call(
        "POST", f"/concerns/{vague['complaint_id']}/review", authority,
        {"action": "override", "category": "Infrastructure and facilities", "priority": "Medium",
         "remarks": "Clarified with the student: broken classroom fan"},
    )
    expect(status, 200, overridden)
    print(f"OVERRIDE {vague['complaint_id']}: AI said {overridden['ai']['category']}/{overridden['ai']['priority']}"
          f" -> human decided {overridden['category']}/{overridden['priority']} ({overridden['decision_source']})")
    print(f"         status now {overridden['status']}, new deadline {when(overridden['tat']['deadline_at'])}")

    _, targets = api.call("GET", f"/concerns/{vague['complaint_id']}/reroute-targets", authority)
    target = next(t for t in targets if t["role"] == "department_authority")
    status, rerouted = api.call(
        "POST", f"/concerns/{vague['complaint_id']}/review", authority,
        {"action": "reroute", "target_user_id": target["id"], "remarks": "Room belongs to the CSE block"},
    )
    expect(status, 200, rerouted)
    print(f"REROUTE  {vague['complaint_id']}: now assigned to {person(rerouted['assigned_to'])}")

    step("11. Audit events for the reviewer actions")
    for e in rerouted["events"]:
        if e["action"] in ("overridden", "rerouted"):
            show_event(e)

    step("12. Simulate a TAT breach (admin, demo mode only)")
    admin = login(api, creds, "demo.admin")
    status, breached = api.call("POST", f"/concerns/{normal['complaint_id']}/simulate_breach", admin)
    expect(status, 200, breached)
    print(f"{normal['complaint_id']} deadline is now {when(breached['tat']['deadline_at'])} [{breached['tat']['state']}]")

    step("13. Run the escalation check now (the automatic TAT monitor runs the same check in the background)")
    status, run = api.call("POST", "/concerns/escalate-overdue", admin)
    expect(status, 200, run)
    for o in run["outcomes"]:
        print(f"{o['complaint_id']}: {o['result']}, level {o['from_level']} -> {o['to_level']}")
    if run["processed"] == 0:
        print("Nothing to do: the automatic monitor had already escalated it (see the audit trail below).")
    _, again = api.call("POST", "/concerns/escalate-overdue", admin)
    print(f"Running it again processes {again['processed']} complaint(s): no duplicate escalation")

    step("14. New assigned authority, new deadline, and the full audit trail")
    _, final = api.call("GET", f"/concerns/{normal['complaint_id']}", admin)
    show_complaint(final)
    print(f"Escalated: {final['escalated']}")
    print("Audit trail:")
    for e in final["events"]:
        show_event(e)

    step("DONE: login -> submit -> AI triage -> confidence check -> TAT -> routing -> "
         "human review -> audit -> breach -> escalation")


if __name__ == "__main__":
    main()
