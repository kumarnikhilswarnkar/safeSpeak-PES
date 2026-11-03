"""SafeSpeak Assistant: deterministic, database-backed answers about complaints.

There is no language model and no external service. A message is matched against fixed
patterns (intents such as status, "why is it unresolved", deadline, authority,
escalation, human review, timeline, classification, resolution, summary, lists and
paging), a complaint ID pattern (SSP-YYYY-NNNNNN), references to the complaint already
being discussed ("it", "its deadline", "that complaint") and positions in the last list
shown ("the second one").

Conversation state is kept by the client and sent back with each message: the complaint
being discussed and the last list shown (kind + position). It is only a hint: the
complaint and every list page are fetched again through the API's own authorization
(complaint_service.get_visible / list_mine / list_queue / list_scoped), so stale or
forged context can never reveal anything. A complaint the user may not open gets the
same reply as one that does not exist. Every value comes from the database; when the
records do not say something (e.g. an authority's internal reasons) the reply says so.
Messages are not stored.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Permission, has_permission
from app.core.timeutil import utcnow
from app.models import OPEN_STATUSES, Complaint, User
from app.schemas.complaint import ComplaintDetailOut, complaint_detail_out, complaint_out
from app.services import complaint_service
from app.services.errors import NotFoundError

CODE_RE = re.compile(r"\bSSP[\s-]?(\d{4})[\s-]?(\d{1,6})\b", re.IGNORECASE)
LIST_PAGE = 8  # items per "page" of a list
LIST_ALL_MAX = 50  # "show all" returns at most this many at once (then "show more" continues)
TIMELINE_LIMIT = 8

# (intent, patterns). A message can match several intents; each is answered.
INTENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("help", (r"\bhelp\b", r"what can you", r"how (do|can) i\b", r"^\s*(hi|hello|hey|namaste)\b")),
    ("list", (r"\bmy (complaints|concerns|cases|tickets)\b", r"\blist\b", r"\ball (my )?complaints\b",
              r"\bshow (me )?(my |all )?complaints\b", r"\bhow many\b")),
    ("queue", (r"\bqueue\b", r"assigned to me", r"\bto review\b", r"\bpending review\b", r"\bmy (tasks|work)\b")),
    ("overdue", (r"\boverdue\b", r"\bbreach", r"\blate\b", r"\bmissed\b")),
    ("deadline", (r"\bdeadline\b", r"\btat\b", r"\bdue\b", r"time left", r"how long", r"\bwhen\b", r"\bturnaround\b")),
    ("authority", (r"\bwho\b", r"\bauthority\b", r"\bhandl", r"\bassigned\b", r"\bofficer\b", r"\breviewer\b")),
    ("escalation", (r"escalat",)),
    ("timeline", (r"\btimeline\b", r"\bhistory\b", r"what happened", r"\bevents?\b", r"\bupdates?\b", r"\bactivity\b")),
    ("classification", (r"\bcategory\b", r"\bpriority\b", r"\bclassif", r"\bai\b", r"\bmodel\b", r"\bconfiden")),
    ("review", (r"human review", r"\breview(ed|ing)?\b(?! queue)", r"\bdecision\b", r"\bdecided\b", r"\boverrid",
                r"\baccepted\b", r"\bapproved\b")),
    ("why", (r"\bwhy\b", r"\bunresolved\b", r"\bnot (yet )?(been )?(resolved|solved|fixed|closed|done|handled)\b",
             r"\bstill (open|pending|not)\b", r"\btaking (so )?long\b", r"\bdelay", r"\bstuck\b",
             r"\bno (action|response|progress)\b")),
    ("summary", (r"tell me (more )?about", r"\bdetails?\b", r"\bsummar", r"\boverview\b", r"\beverything\b",
                 r"\bexplain\b", r"\binfo(rmation)?\b", r"^\s*what about\b")),
    ("resolution", (r"\bresol", r"\bclosed?\b", r"\boutcome\b", r"\bfixed\b", r"\bsolved\b")),
    ("status", (r"\bstatus\b", r"\bprogress\b", r"where is", r"what'?s happening", r"\bupdate on\b", r"\btrack")),
]
# Order in which several questions about one complaint are answered.
COMPLAINT_INTENTS = ("why", "status", "review", "deadline", "authority", "escalation", "timeline",
                     "classification", "resolution", "summary")

MORE_RE = re.compile(r"^\s*(please\s+)?((show|see|load|give|list)\s+(me\s+)?)?(the\s+)?(more|next|rest|remaining)\b"
                     r"|\bnext page\b|\bshow (me )?(the )?(rest|remaining)\b|\bmore (complaints|results|items)\b|\bcontinue\b")
ALL_RE = re.compile(r"\b(show|see|list|give)( me)? (them )?all\b|\ball of them\b|\bfull list\b|\bshow all\b|\bevery (one|complaint)\b")
REFERENCE_RE = re.compile(r"\b(it|its|it's|this|that|same|that one|this one|the complaint|this complaint|that complaint)\b")
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8}
ORDINAL_RE = re.compile(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|last)"
                        r"\s+(one|complaint|item)\b|\b(?:number|no\.?|#)\s*(\d{1,2})\b")
SMALL_TALK_RE = re.compile(r"^\s*(thanks?|thank you|ok(ay)?|cool|great|got it|bye|goodbye)\b[\s!.]*$")

LIST_KINDS = ("mine", "queue", "overdue", "scoped")

STATUS_LABEL = {
    "PENDING_REVIEW": "Awaiting human review",
    "ASSIGNED": "Assigned",
    "IN_PROGRESS": "In progress",
    "RESOLVED": "Resolved",
    "CLOSED": "Closed",
}
DECISION_LABEL = {
    "AI_PENDING_REVIEW": "AI recommendation, waiting for a human reviewer",
    "AI_AUTO": "AI recommendation applied automatically (confident, not High/Critical)",
    "HUMAN_ACCEPTED": "a reviewer accepted the AI recommendation",
    "HUMAN_OVERRIDDEN": "a reviewer changed the AI recommendation",
}
REASON_LABEL = {
    "LOW_CATEGORY_CONFIDENCE": "the AI was not confident enough about the category",
    "LOW_PRIORITY_CONFIDENCE": "the AI was not confident enough about the priority",
    "HIGH_SEVERITY": "High/Critical priority always needs a human",
    "MODEL_UNAVAILABLE": "the AI model was unavailable",
}
EVENT_LABEL = {
    "complaint_created": "Complaint submitted",
    "ai_triaged": "AI analysis completed",
    "sent_to_human_review": "Sent for human review",
    "routing_levels_skipped": "Unavailable levels skipped",
    "assigned": "Assigned",
    "accepted": "Reviewer accepted the AI recommendation",
    "overridden": "Reviewer changed category/priority",
    "rerouted": "Rerouted by reviewer",
    "deadline_recalculated": "Deadline recalculated",
    "resolved": "Resolved",
    "tat_breach_simulated": "TAT breach simulated (demo)",
    "tat_breached": "TAT breached",
    "escalation_triggered": "Escalated",
    "escalation_exhausted": "Escalation chain exhausted",
    "admin_reassigned": "Reassigned by an administrator",
}
ROLE_LABEL = {
    "department_authority": "Department authority",
    "higher_authority": "Higher authority",
}
STAGE_LABEL = {"REVIEW": "review", "RESOLUTION": "resolution"}

NOT_FOUND = ("I couldn't find a complaint with ID {code} that you have access to. "
             "Check the ID (format SSP-YYYY-NNNNNN), or ask “show my complaints”.")


@dataclass
class AssistantReply:
    reply: str
    intent: str
    complaint_id: str | None = None
    cards: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    # The list shown in this reply (kind, offset, limit, total), for "show more" and "the second one".
    list_context: dict[str, Any] | None = None


# --- parsing ---------------------------------------------------------------------------

def normalize_code(year: str, number: str) -> str:
    return f"SSP-{year}-{int(number):06d}"


def find_codes(text: str) -> list[str]:
    seen: list[str] = []
    for m in CODE_RE.finditer(text):
        code = normalize_code(m.group(1), m.group(2))
        if code not in seen:
            seen.append(code)
    return seen


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").replace("‘", "'").split())


def detect_intents(text: str) -> list[str]:
    lowered = _normalize(text)
    found = [name for name, patterns in INTENT_PATTERNS if any(re.search(p, lowered) for p in patterns)]
    if "queue" in found and "authority" in found:
        found.remove("authority")  # "assigned to me" is about the queue, not "who is assigned"
    if "queue" in found and "review" in found:
        found.remove("review")  # "what is pending review / in my queue to review"
    if "why" in found and "resolution" in found:
        found.remove("resolution")  # "why has it not been resolved" is answered by "why"
    if "escalation" in found and "timeline" in found and not re.search(r"\btimeline\b|\bevents?\b|\bactivity\b", lowered):
        found.remove("timeline")  # "what happened during escalation", "escalation history"
    if "escalation" in found and "summary" in found:
        found.remove("summary")  # "explain its escalation history"
    if "summary" in found and len([i for i in found if i in COMPLAINT_INTENTS]) > 1:
        found.remove("summary")  # "explain why ..." -> the specific answer only
    return found


def _ordinal(text: str) -> int | None:
    """1-based position in the last list shown, or -1 for "the last one"."""
    m = ORDINAL_RE.search(_normalize(text))
    if not m:
        return None
    if m.group(3):
        return int(m.group(3))
    word = m.group(1)
    return -1 if word == "last" else ORDINALS[word]


# --- formatting --------------------------------------------------------------------------

def _when(dt: datetime | str | None, settings: Settings) -> str:
    if dt is None:
        return "unknown"
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    local = dt.astimezone(settings.tz)
    return f"{local.day} {local:%b %Y, %H:%M} {local.tzname()}"


def _duration(seconds: int) -> str:
    seconds = abs(int(seconds))
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes = rest // 60
    if days:
        return f"{days} day{'s' if days != 1 else ''} {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def _person(p) -> str:
    """'Name, L2, Department authority, Computer Applications' - level only if the name lacks it."""
    if p is None:
        return "nobody (unassigned)"
    if isinstance(p, dict):  # audit snapshot
        return p.get("name") or "an authority"
    extra = []
    if p.authority_level and f"(L{p.authority_level})" not in p.name:
        extra.append(f"L{p.authority_level}")
    if p.role in ROLE_LABEL:
        extra.append(ROLE_LABEL[p.role])
    if p.department:
        extra.append(p.department.name)
    return p.name + (f", {', '.join(extra)}" if extra else "")


def _tat_phrase(d, s: Settings) -> str:
    stage = STAGE_LABEL.get(d.tat.stage, d.tat.stage.lower())
    if d.tat.state == "STOPPED":
        return f"The clock stopped when it was resolved ({_when(d.resolved_at, s)})."
    deadline = _when(d.tat.deadline_at, s)
    if d.tat.state == "OVERDUE":
        return f"The {stage} deadline was {deadline}; it is overdue by {_duration(d.tat.seconds_remaining or 0)}."
    soon = " (due soon)" if d.tat.state == "DUE_SOON" else ""
    return f"The {stage} deadline is {deadline}: {_duration(d.tat.seconds_remaining or 0)} left{soon}."


def _summary_card(c: Complaint | ComplaintDetailOut, settings: Settings) -> dict[str, Any]:
    d = c if isinstance(c, ComplaintDetailOut) else complaint_out(c, settings)
    return {
        "complaint_id": d.complaint_id,
        "status": d.status,
        "status_label": STATUS_LABEL.get(d.status, d.status),
        "category": d.category,
        "priority": d.priority,
        "assigned_to": d.assigned_to.name if d.assigned_to else None,
        "escalation_level": d.escalation_level,
        "escalated": d.escalated,
        "breached_at_top": d.breached_at_top,
        "deadline_at": d.tat.deadline_at.isoformat(),
        "tat_state": d.tat.state,
        "tat_stage": d.tat.stage,
        "seconds_remaining": d.tat.seconds_remaining,
        "created_at": d.created_at.isoformat(),
    }


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"• {line}" for line in lines)


def _interventions(d: ComplaintDetailOut) -> list:
    return [h for h in d.escalation.history if h.result == "admin_reassigned"]


# --- complaint answers ----------------------------------------------------------------------
# Each answer: (detail, settings, technical) -> text. "technical" = the user may see model
# details (reviewers, read-only authorities, administrators); complainants get plain language.

def _status(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    head = f"{d.complaint_id} is **{STATUS_LABEL.get(d.status, d.status)}**"
    if d.status in ("RESOLVED", "CLOSED"):
        text = f"{head}. It was resolved on {_when(d.resolved_at, s)}."
        if d.resolution_note:
            text += f" Resolution note: “{d.resolution_note}”"
        return text
    lines = [f"{head} — {d.category}, {d.priority} priority."]
    if d.status == "PENDING_REVIEW":
        reasons = ", ".join(REASON_LABEL.get(r, r) for r in d.review_reasons) or "flagged by the system"
        lines.append(f"It is waiting for a human reviewer, {_person(d.assigned_to)}, because: {reasons}.")
    else:
        lines.append(f"It is with {_person(d.assigned_to)} (escalation step {d.escalation_level}).")
    if d.breached_at_top:
        lines.append("Its deadline passed at the top of the escalation chain, so it needs administrator attention.")
    lines.append(_tat_phrase(d, s))
    return " ".join(lines)


def _why(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    if d.status in ("RESOLVED", "CLOSED"):
        note = f" Resolution note: “{d.resolution_note}”" if d.resolution_note else ""
        return f"{d.complaint_id} is not open any more: it was resolved on {_when(d.resolved_at, s)}.{note}"
    lines = []
    if d.status == "PENDING_REVIEW":
        reasons = ", ".join(REASON_LABEL.get(r, r) for r in d.review_reasons) or "it was flagged for review"
        lines.append(f"It is waiting for a human review decision by {_person(d.assigned_to)}. "
                     f"Human review was required because {reasons}.")
    elif d.status == "IN_PROGRESS":
        lines.append(f"{_person(d.assigned_to)} is working on it and has not marked it resolved yet.")
    else:
        lines.append(f"It is assigned to {_person(d.assigned_to)}, who has not marked it resolved yet.")
    lines.append(_tat_phrase(d, s))
    escalations = [h for h in d.escalation.history if h.result == "escalated"]
    if escalations:
        lines.append(f"It was escalated {len(escalations)} time(s) because earlier deadlines passed without a "
                     f"resolution (now at step {d.escalation_level} of its chain).")
    for h in _interventions(d):
        lines.append(f"On {_when(h.at, s)} an administrator reassigned it to {_person(h.to_assignee)}: "
                     f"“{h.reason}”.")
    if d.breached_at_top:
        lines.append("The last authority in its escalation chain also missed the deadline and there is no higher "
                     "level, so it now needs administrator intervention.")
    last = d.events[-1] if d.events else None
    if last:
        lines.append(f"Last recorded activity: {EVENT_LABEL.get(last.action, last.action)} on {_when(last.created_at, s)}.")
    return (f"Why {d.complaint_id} is still open, according to SafeSpeak's records:\n" + _bullets(lines)
            + "\nThe records show the workflow state; they do not contain an authority's internal reasons for a delay.")


def _deadline(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    stage = STAGE_LABEL.get(d.tat.stage, d.tat.stage.lower())
    hours = f"{d.tat.hours:g}"
    text = (f"{d.complaint_id} is in the {stage} stage, which allows {hours} h under TAT rule #{d.tat.rule_id} "
            f"(started {_when(d.tat.started_at, s)}). {_tat_phrase(d, s)}")
    original = d.escalation.original_deadline_at
    if original and d.tat.state != "STOPPED" and original[:16] != d.tat.deadline_at.isoformat()[:16]:
        text += f" Its original deadline was {_when(original, s)}."
    if d.breached_at_top:
        text += " It is overdue at the last step of its escalation chain and needs administrator attention."
    elif d.tat.state == "OVERDUE":
        text += " Overdue complaints are escalated automatically to the next authority level."
    return text


def _authority(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    if d.status in ("RESOLVED", "CLOSED"):
        return f"{d.complaint_id} is resolved; it was last handled by {_person(d.assigned_to)}."
    role = "reviewing" if d.status == "PENDING_REVIEW" else "handling"
    text = f"{_person(d.assigned_to)} is {role} {d.complaint_id} (escalation step {d.escalation_level})."
    if d.handling_department:
        text += f" Handling department: {d.handling_department.name}."
    routing = d.routing or {}
    chain = routing.get("chain") or []
    if chain:
        steps = " → ".join(f"{step['level']}. {step['label']}" for step in chain)
        text += f" Escalation chain for {d.category}: {steps}."
    if _interventions(d):
        text += " An administrator chose the current authority (see the escalation history)."
    elif routing.get("manually_rerouted"):
        text += " A reviewer rerouted it manually."
    if d.breached_at_top:
        text += " It is overdue at the last step of the chain, so it needs administrator attention."
    return text


def _escalation(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    history = d.escalation.history
    if not history:
        base = f"{d.complaint_id} has not been escalated; it is at step {d.escalation_level} of its escalation chain."
        if d.status in OPEN_STATUSES:
            base += " If the deadline passes, the system escalates it automatically to the next level."
        return base
    steps = []
    for h in history:
        when = _when(h.at, s)
        if h.result == "exhausted":
            steps.append(f"{when}: the deadline passed again and no higher level was available (chain exhausted)")
        elif h.result == "admin_reassigned":
            by = (h.by or {}).get("name", "an administrator")
            steps.append(f"{when}: {by} (administrator) reassigned it from {_person(h.from_assignee)} to "
                         f"{_person(h.to_assignee)} — reason: “{h.reason}”")
        else:
            how = "automatically" if h.automatic else "manually"
            steps.append(f"{when}: the deadline was missed, so it was escalated {how} from step {h.from_level} to "
                         f"step {h.to_level} ({_person(h.to_assignee)})")
    text = f"Escalation history of {d.complaint_id} ({len(history)} event(s)):\n" + _bullets(steps)
    if d.breached_at_top:
        text += "\nIt now needs administrator attention."
    return text


def _timeline_card(d: ComplaintDetailOut) -> dict[str, Any]:
    return {
        "type": "timeline",
        "complaint_id": d.complaint_id,
        "items": [
            {
                "action": e.action,
                "label": EVENT_LABEL.get(e.action, e.action.replace("_", " ").capitalize()),
                "at": e.created_at.isoformat(),
                "actor": e.actor.name if e.actor else "System",
                "remarks": e.remarks,
            }
            for e in d.events
        ],
    }


def _timeline(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    recent = d.events[-TIMELINE_LIMIT:]
    lines = [f"{EVENT_LABEL.get(e.action, e.action)} — {_when(e.created_at, s)}"
             f" ({e.actor.name if e.actor else 'System'})" for e in recent]
    more = f" (latest {len(recent)} of {len(d.events)})" if len(d.events) > len(recent) else ""
    return f"Timeline of {d.complaint_id}{more}:\n" + _bullets(lines)


def _classification(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    ai = d.ai
    text = (f"{d.complaint_id} is classified as **{d.category}**, **{d.priority}** priority "
            f"({DECISION_LABEL.get(d.decision_source, d.decision_source)}).")
    if (ai.explanation or {}).get("fallback"):
        return text + (" The AI model was unavailable when it was submitted, so a human reviewer decides the "
                       "category and priority.")
    if technical:
        text += (f" The AI model ({ai.model}) suggested {ai.category} ({ai.category_confidence:.0%} confidence) and "
                 f"{ai.priority} ({ai.priority_confidence:.0%}).")
    else:
        text += (f" The AI suggested {ai.category} and {ai.priority} priority. This is only a recommendation; "
                 "the values above are what the workflow uses.")
    if ai.flag_reasons:
        text += " It was sent to a human because: " + ", ".join(REASON_LABEL.get(r, r) for r in ai.flag_reasons) + "."
    return text


def _review(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    ai, hd = d.ai, d.human_decision
    lines = []
    if ai.flagged_for_review:
        reasons = ", ".join(REASON_LABEL.get(r, r) for r in ai.flag_reasons) or "it was flagged"
        lines.append(f"Human review was required because {reasons}.")
    else:
        lines.append("Human review was not required: the AI was confident and the priority is not High/Critical. "
                     "An authority can still change the recommendation.")
    if hd:
        verb = "accepted the AI recommendation" if hd.action == "accepted" else "changed the AI recommendation"
        reviewer = hd.reviewer.name if hd.reviewer else "A reviewer"
        line = f"{reviewer} {verb} on {_when(hd.at, s)}"
        prev, new = hd.previous or {}, hd.new or {}
        changes = [f"{k} {prev.get(k)} → {new.get(k)}" for k in ("category", "priority") if prev.get(k) != new.get(k)]
        if changes:
            line += " (" + "; ".join(changes) + ")"
        if hd.remarks:
            line += f", with the note “{hd.remarks}”"
        lines.append(line + ".")
    elif d.status == "PENDING_REVIEW":
        lines.append(f"No decision yet: it is waiting for {_person(d.assigned_to)}. {_tat_phrase(d, s)}")
    elif ai.flagged_for_review:
        lines.append("No human decision is recorded yet.")
    lines.append(f"Final values used by the workflow: {d.category}, {d.priority} priority.")
    return f"Human review of {d.complaint_id}:\n" + _bullets(lines)


def _resolution(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    if d.status in ("RESOLVED", "CLOSED"):
        note = f" Resolution note: “{d.resolution_note}”" if d.resolution_note else ""
        return f"{d.complaint_id} was resolved on {_when(d.resolved_at, s)}.{note}"
    return (f"{d.complaint_id} is not resolved yet (status: {STATUS_LABEL.get(d.status, d.status)}). "
            + _tat_phrase(d, s))


def _summary(d: ComplaintDetailOut, s: Settings, technical: bool) -> str:
    lines = [_status(d, s, technical)]
    if d.status in OPEN_STATUSES:
        escalations = [h for h in d.escalation.history if h.result == "escalated"]
        if escalations:
            lines.append(f"It has been escalated {len(escalations)} time(s).")
    hd = d.human_decision
    if hd:
        lines.append(f"Human decision: {'accepted' if hd.action == 'accepted' else 'changed'} by "
                     f"{hd.reviewer.name if hd.reviewer else 'a reviewer'} on {_when(hd.at, s)}.")
    return "\n\n".join(lines)


ANSWERS = {
    "why": _why,
    "status": _status,
    "review": _review,
    "deadline": _deadline,
    "authority": _authority,
    "escalation": _escalation,
    "timeline": _timeline,
    "classification": _classification,
    "resolution": _resolution,
    "summary": _summary,
}
SUGGEST = (("Why is it unresolved?", "why"), ("Who is handling it?", "authority"), ("What is its deadline?", "deadline"),
           ("Explain its escalation history", "escalation"), ("Has a human reviewed it?", "review"),
           ("Show the timeline", "timeline"))


def _technical(user: User) -> bool:
    return has_permission(user.role, Permission.REVIEW_COMPLAINTS) or has_permission(user.role, Permission.VIEW_SCOPED_COMPLAINTS)


def _complaint_reply(db: Session, settings: Settings, user: User, code: str, intents: list[str],
                     note: str = "") -> AssistantReply:
    try:
        c = complaint_service.get_visible(db, user, code)
    except NotFoundError:
        return AssistantReply(NOT_FOUND.format(code=code), "not_found", None,
                              suggestions=["Show my complaints", "Help"])
    d = complaint_detail_out(c, settings, complaint_service.routing_context(db, c))
    asked = [i for i in COMPLAINT_INTENTS if i in intents] or ["status"]
    technical = _technical(user)
    parts = [ANSWERS[i](d, settings, technical) for i in asked]
    cards: list[dict[str, Any]] = [{"type": "complaint", **_summary_card(d, settings)}]
    if "timeline" in asked:
        cards.append(_timeline_card(d))
    suggestions = [label for label, intent in SUGGEST
                   if intent not in asked and not (intent == "why" and d.status not in OPEN_STATUSES)][:3]
    return AssistantReply((note + "\n\n" if note else "") + "\n\n".join(parts), asked[0], d.complaint_id, cards, suggestions)


# --- lists ---------------------------------------------------------------------------------
# Every page is re-queried with the user's own permissions; ordering is deterministic
# (newest first, or earliest deadline first for queues/overdue), so pages never overlap.

def _collection(db: Session, user: User, kind: str) -> tuple[str, str, list[Complaint], str] | None:
    now = utcnow()
    if kind == "mine" and has_permission(user.role, Permission.VIEW_OWN_COMPLAINTS):
        items = sorted(complaint_service.list_mine(db, user), key=lambda c: -c.id)
        open_count = sum(c.status in OPEN_STATUSES for c in items)
        return ("Your complaints", f"You have {len(items)} complaint(s), {open_count} open.", items,
                "You have not submitted any complaints yet.")
    if kind == "scoped" and has_permission(user.role, Permission.VIEW_SCOPED_COMPLAINTS):
        items = sorted(complaint_service.list_scoped(db, user), key=lambda c: -c.id)
        return ("Complaints in your scope", f"There are {len(items)} complaint(s) in your scope.", items,
                "There are no complaints in your scope.")
    if kind == "queue" and has_permission(user.role, Permission.VIEW_ASSIGNED_COMPLAINTS):
        items = sorted(complaint_service.list_queue(db, user), key=lambda c: (c.deadline_at, c.id))
        pending = sum(c.status == "PENDING_REVIEW" for c in items)
        return ("Your queue (earliest deadline first)",
                f"{len(items)} open complaint(s) are assigned to you; {pending} wait for your review.", items,
                "No open complaints are assigned to you.")
    if kind == "overdue":
        seen, items = set(), []
        for k in ("mine", "queue", "scoped"):
            col = _collection(db, user, k)
            for c in col[2] if col else []:
                if c.id not in seen and c.status in OPEN_STATUSES and c.deadline_at < now:
                    seen.add(c.id)
                    items.append(c)
        items.sort(key=lambda c: (c.deadline_at, c.id))
        return ("Overdue complaints", f"{len(items)} complaint(s) you can view are past their deadline.", items,
                "None of the complaints you can view is overdue.")
    return None


def _default_list_kind(user: User) -> str:
    return "mine" if has_permission(user.role, Permission.VIEW_OWN_COMPLAINTS) else "scoped"


def _list_reply(db: Session, settings: Settings, user: User, kind: str, offset: int = 0, limit: int = LIST_PAGE,
                intent: str = "list") -> AssistantReply:
    col = _collection(db, user, kind)
    if col is None:
        return AssistantReply("Your account does not have that list. You can ask about complaints you can view.",
                              intent, suggestions=["Show my complaints"])
    title, intro, items, empty = col
    total = len(items)
    if total == 0:
        return AssistantReply(empty, intent, suggestions=["Help"])
    offset = max(0, min(offset, total - 1))
    page = items[offset: offset + limit]
    end = offset + len(page)
    has_more = end < total
    reply = intro + (f" Showing {offset + 1}–{end} of {total}." if total > len(page) else "")
    suggestions = (["Show more", "Show all"] if has_more else []) + [f"Status of {c.complaint_code}" for c in page[:2]]
    return AssistantReply(
        reply, intent, None,
        cards=[{"type": "list", "title": title, "items": [_summary_card(c, settings) for c in page],
                "pagination": {"kind": kind, "offset": offset, "shown": len(page), "total": total, "has_more": has_more}}],
        suggestions=suggestions[:4],
        list_context={"kind": kind, "offset": offset, "limit": len(page), "total": total},
    )


def _queue_reply(db: Session, settings: Settings, user: User) -> AssistantReply:
    if not has_permission(user.role, Permission.VIEW_ASSIGNED_COMPLAINTS):
        return AssistantReply("Your account does not have a review queue. You can ask about complaints you can view.",
                              "queue", suggestions=["Show my complaints"])
    return _list_reply(db, settings, user, "queue", intent="queue")


def _from_list(db: Session, user: User, list_context: dict | None, position: int) -> str | None:
    """Complaint ID at a 1-based position of the page last shown (-1 = its last item)."""
    if not list_context or list_context.get("kind") not in LIST_KINDS:
        return None
    col = _collection(db, user, list_context["kind"])
    if col is None:
        return None
    offset = int(list_context.get("offset") or 0)
    page = col[2][offset: offset + int(list_context.get("limit") or LIST_PAGE)]
    if not page:
        return None
    index = len(page) - 1 if position == -1 else position - 1
    return page[index].complaint_code if 0 <= index < len(page) else None


def _help(user: User) -> AssistantReply:
    lines = [
        "I'm the SafeSpeak Assistant. I answer from SafeSpeak's own records, only about complaints you are allowed "
        "to see. I can tell you:",
        "• the status of a complaint — e.g. “status of SSP-2026-000123”",
        "• why it is still open, its deadline (TAT), who is handling it and its escalation history",
        "• whether a human reviewed it and what was decided, its timeline, category/priority and resolution",
        "• a list of your complaints (say “show more” for the next page)"
        + (" or your review queue" if has_permission(user.role, Permission.VIEW_ASSIGNED_COMPLAINTS) else ""),
        "After you ask about a complaint you can just say “who is handling it?” or “why is it unresolved?”. "
        "To file a new complaint, use “New complaint”. I cannot change complaints.",
    ]
    suggestions = ["Show my complaints"]
    if has_permission(user.role, Permission.VIEW_ASSIGNED_COMPLAINTS):
        suggestions.append("What is in my queue?")
    suggestions.append("Any overdue complaints?")
    return AssistantReply("\n".join(lines), "help", suggestions=suggestions)


# --- entry point -----------------------------------------------------------------------------

def respond(db: Session, settings: Settings, user: User, message: str, context_complaint_id: str | None = None,
            list_context: dict | None = None) -> AssistantReply:
    text = _normalize(message)
    codes = find_codes(message)
    intents = detect_intents(message)
    complaint_intents = [i for i in intents if i in COMPLAINT_INTENTS]
    context = (find_codes(context_complaint_id or "") or [None])[0]
    refers = bool(REFERENCE_RE.search(text))
    position = _ordinal(message)

    # 1. Explicit complaint IDs always win.
    if codes:
        note = (f"You mentioned {len(codes)} IDs; here is {codes[0]}. Ask about the others one at a time."
                if len(codes) > 1 else "")
        return _complaint_reply(db, settings, user, codes[0], intents, note)

    # 2. Paging through the last list ("show more", "next", "show all").
    show_all = bool(ALL_RE.search(text))
    if (MORE_RE.search(text) or show_all) and not complaint_intents:
        kind = (list_context or {}).get("kind")
        if kind in LIST_KINDS:
            if show_all:
                return _list_reply(db, settings, user, kind, 0, LIST_ALL_MAX)
            offset = int(list_context.get("offset") or 0) + int(list_context.get("limit") or LIST_PAGE)
            if offset >= int(list_context.get("total") or 0):
                reply = _list_reply(db, settings, user, kind, 0)
                reply.reply = "That was the end of the list. Here it is again from the start. " + reply.reply
                return reply
            return _list_reply(db, settings, user, kind, offset)
        if "list" in intents or show_all:
            return _list_reply(db, settings, user, _default_list_kind(user), 0, LIST_ALL_MAX if show_all else LIST_PAGE)
        return AssistantReply("There is no list to continue yet. Ask “show my complaints” first.", "more",
                              suggestions=["Show my complaints"])

    # 3. A position in the last list shown ("the second one", "number 3").
    if position is not None:
        code = _from_list(db, user, list_context, position)
        if code:
            return _complaint_reply(db, settings, user, code, intents)
        if not context:
            return AssistantReply("I don't have a list to pick from. Ask “show my complaints” first, or give the "
                                  "complaint ID.", "clarify", suggestions=["Show my complaints"])

    # 4. Lists and queues.
    if "queue" in intents:
        return _queue_reply(db, settings, user)
    if "overdue" in intents and not complaint_intents and not (refers and context):
        return _list_reply(db, settings, user, "overdue", intent="overdue")
    if "list" in intents and not complaint_intents:
        return _list_reply(db, settings, user, _default_list_kind(user))

    # 5. Questions about one complaint: the one being discussed, or the user's only open one.
    if "overdue" in intents and refers and context:
        intents = [*intents, "deadline"]  # "is it overdue?" -> that complaint's deadline
        complaint_intents = ["deadline", *complaint_intents]
    if not complaint_intents and context and refers and not SMALL_TALK_RE.search(text):
        complaint_intents = intents = ["summary"]  # "and that one?", "what about it?"
    if complaint_intents:
        if context:  # re-checked against the user's scope on every message
            return _complaint_reply(db, settings, user, context, intents)
        own_open = []
        if has_permission(user.role, Permission.VIEW_OWN_COMPLAINTS):
            own_open = [c for c in complaint_service.list_mine(db, user) if c.status in OPEN_STATUSES]
        if len(own_open) == 1:
            return _complaint_reply(db, settings, user, own_open[0].complaint_code, intents,
                                    f"You have one open complaint, {own_open[0].complaint_code}:")
        reply = _list_reply(db, settings, user, _default_list_kind(user))
        reply.reply = "Which complaint do you mean? Include its ID (SSP-YYYY-NNNNNN) or pick one below. " + reply.reply
        reply.intent = "clarify"
        return reply

    if SMALL_TALK_RE.search(text):
        return AssistantReply("You're welcome. Ask me about any of your complaints whenever you need.", "small_talk",
                              suggestions=["Show my complaints"])
    if "help" in intents:
        return _help(user)
    fallback = _help(user)
    fallback.reply = "Sorry, I didn't understand that. " + fallback.reply
    fallback.intent = "unknown"
    if context:
        fallback.suggestions = [f"Status of {context}", "Why is it unresolved?", "Who is handling it?"]
    return fallback
