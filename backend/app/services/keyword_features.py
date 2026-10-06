"""Hand-written keyword lexicon for SafeSpeak categories and priorities.

Used in two ways:
1. The keyword/rule BASELINE that the ML model is compared against
   (ml/train_triage.py): count lexicon hits per class, highest count wins.
2. As extra features (KeywordCounts) for the hybrid model, so the classifier can
   learn how much to trust each keyword list.

The lists were written from the category definitions in the annotation
guidelines, before evaluation, and are frozen: they must not be tuned on the
test split. Terms are matched as word prefixes, so "harass" matches
"harassed" and "harassment".
"""
import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Hostel": [
        "hostel", "mess", "warden", "room", "roommate", "dorm", "bed", "laundry", "canteen food",
        "dinner", "lunch", "breakfast", "food", "curfew", "hostel fee", "geyser", "hot water",
    ],
    "Exam": [
        "exam", "examination", "hall ticket", "admit card", "marks", "grade", "result", "revaluation",
        "re-evaluation", "invigilator", "question paper", "answer sheet", "isa", "esa", "backlog",
        "supplementary", "seating", "timetable clash", "moderation",
    ],
    "Academic / Department": [
        "lecture", "class", "faculty", "professor", "teacher", "syllabus", "course", "assignment",
        "attendance", "lab session", "project guide", "mentor", "department", "elective", "credits",
        "internship", "curriculum", "hod",
    ],
    "Infrastructure and facilities": [
        "projector", "wifi", "wi-fi", "internet", "network", "fan", "light", "ac ", "air conditioner",
        "washroom", "toilet", "water cooler", "drinking water", "lift", "elevator", "leak", "power",
        "electricity", "chair", "bench", "classroom", "building", "maintenance", "repair", "broken",
        "plumbing", "parking",
    ],
    "Safety and welfare": [
        "harass", "ragging", "bully", "threat", "abuse", "assault", "stalk", "unsafe", "safety",
        "security", "fight", "violence", "molest", "inappropriate", "touch", "mental health",
        "depress", "suicid", "anxiety", "counsel", "injur", "fire", "emergency", "discriminat",
    ],
    "Administrative / Fees": [
        "fee", "fees", "payment", "refund", "receipt", "scholarship", "certificate", "bonafide",
        "transcript", "id card", "admission", "office", "document", "fine", "challan", "invoice",
        "admin office", "registration",
    ],
    "Library / Transport": [
        "library", "book", "librarian", "reading room", "journal", "bus", "transport", "driver",
        "route", "shuttle", "pickup", "drop", "commute", "bus pass", "vehicle",
    ],
    "Other": [
        "suggestion", "feedback", "general", "event", "club", "fest", "sports", "gym", "placement",
        "cafeteria", "noise",
    ],
}

PRIORITY_KEYWORDS: dict[str, list[str]] = {
    "Critical": [
        "harass", "assault", "molest", "suicid", "self harm", "kill", "threat", "violence", "fire",
        "injur", "bleed", "unconscious", "emergency", "electric shock", "short circuit", "gas leak",
        "collapse", "ragging", "stalk", "unsafe",
    ],
    "High": [
        "urgent", "immediately", "asap", "tomorrow", "deadline", "not working for", "weeks", "since last",
        "again and again", "repeated", "still not", "no response", "cannot attend", "missed", "lost",
        "fail", "sick", "ill", "health",
    ],
    "Low": [
        "suggestion", "minor", "small", "not a big deal", "whenever possible", "would be nice", "request",
        "kindly consider", "if possible", "slight", "a bit", "sometimes",
    ],
}
# A text with no priority keyword gets this label.
DEFAULT_PRIORITY = "Medium"
# A text with no category keyword gets this label.
DEFAULT_CATEGORY = "Other"


def _compile(terms: list[str]) -> list[re.Pattern]:
    return [re.compile(r"(?<![a-z])" + re.escape(t.strip())) for t in terms]


_CATEGORY_PATTERNS = {label: _compile(terms) for label, terms in CATEGORY_KEYWORDS.items()}
_PRIORITY_PATTERNS = {label: _compile(terms) for label, terms in PRIORITY_KEYWORDS.items()}


def _hits(text: str, patterns: dict[str, list[re.Pattern]]) -> dict[str, int]:
    lowered = text.lower()
    return {label: sum(1 for p in pats if p.search(lowered)) for label, pats in patterns.items()}


def category_hits(text: str) -> dict[str, int]:
    return _hits(text, _CATEGORY_PATTERNS)


def priority_hits(text: str) -> dict[str, int]:
    return _hits(text, _PRIORITY_PATTERNS)


def keyword_category(text: str) -> str:
    """Baseline rule: most keyword hits wins; ties go to the earlier category in
    CATEGORY_KEYWORDS order; no hit at all → DEFAULT_CATEGORY."""
    hits = category_hits(text)
    best = max(hits.values())
    if best == 0:
        return DEFAULT_CATEGORY
    return next(label for label, n in hits.items() if n == best)


def keyword_priority(text: str) -> str:
    """Baseline rule: the most severe priority with any keyword hit; none → DEFAULT_PRIORITY."""
    hits = priority_hits(text)
    for label in ("Critical", "High", "Low"):
        if hits[label]:
            return label
    return DEFAULT_PRIORITY


class KeywordCounts(BaseEstimator, TransformerMixin):
    """Lexicon hit counts as numeric features (one column per label), for the
    hybrid model. task = "category" or "priority"."""

    def __init__(self, task: str = "category"):
        self.task = task

    def fit(self, X, y=None):
        return self

    def _patterns(self):
        return _CATEGORY_PATTERNS if self.task == "category" else _PRIORITY_PATTERNS

    def get_feature_names_out(self, input_features=None):
        return np.array([f"kw:{label}" for label in self._patterns()], dtype=object)

    def transform(self, X):
        patterns = self._patterns()
        return np.array([[float(n) for n in _hits(text, patterns).values()] for text in X])
