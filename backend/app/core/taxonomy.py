"""Research labels shared by the dataset, the triage model and the application.
These must stay identical to the labels in ml/data (they are checked when the
model loads)."""

CATEGORIES: tuple[str, ...] = (
    "Hostel",
    "Exam",
    "Academic / Department",
    "Infrastructure and facilities",
    "Safety and welfare",
    "Administrative / Fees",
    "Library / Transport",
    "Other",
)

PRIORITIES: tuple[str, ...] = ("Low", "Medium", "High", "Critical")

HIGH_SEVERITY_PRIORITIES = frozenset({"High", "Critical"})
