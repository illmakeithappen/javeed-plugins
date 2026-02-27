"""Column constants, pipe helpers, and type coercion for CSV I/O."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Input CSV column names
# ---------------------------------------------------------------------------

EMPLOYEES_COLS = [
    "employee_id",
    "name",
    "role",
    "employment",
    "hourly_wage",
    "max_salary",
    "skills",
]

SHIFTS_COLS = [
    "employee_id",
    "date",
    "start",
    "end",
]

OPEN_SLOTS_COLS = [
    "slot_id",
    "date",
    "start",
    "end",
    "shift_type",
    "area",
    "applicants",
]

ABSENCES_COLS = [
    "employee_id",
    "start_date",
    "end_date",
]

GOLDEN_ASSIGNMENTS_COLS = [
    "slot_id",
    "employee_name",
    "employee_id",
]

# ---------------------------------------------------------------------------
# Output CSV column names
# ---------------------------------------------------------------------------

SCORE_COMPONENTS = [
    "rest",
    "fairness",
    "role",
    "skill",
    "fixed",
    "preference",
    "applicant",
    "salary",
]

ASSIGNMENTS_COLS = [
    "slot_id",
    "date",
    "start",
    "end",
    "shift_type",
    "area",
    "employee_id",
    "employee_name",
    "score",
    "is_applicant",
    "kind",
    *[f"score_{c}" for c in SCORE_COMPONENTS],
    "reasons",
    "target_hours",
    "month_hours_before",
]

UNASSIGNED_COLS = [
    "slot_id",
    "date",
    "start",
    "end",
    "shift_type",
    "area",
    "reason",
    "top_blocked",
]

FAIRNESS_COLS = [
    "employee_name",
    "assigned_hours",
    "assigned_slots",
    "target_hours",
    "delta",
]

EVAL_MATRIX_COLS = [
    "slot_id",
    "date",
    "start",
    "end",
    "area",
    "employee_name",
    "blocked",
    "blocked_reasons",
    "score",
    *[f"score_{c}" for c in SCORE_COMPONENTS],
    "is_applicant",
    "selected",
]

DIRECTIVES_COLS = [
    "id",
    "text",
    "employees",
    "source",
]

DIRECTIVE_COMPLIANCE_COLS = [
    "directive_id",
    "text",
    "employees",
    "rule_field",
    "rule_value",
    "honored",
    "evidence",
]

GOLDEN_COMPARISON_COLS = [
    "slot_id",
    "date",
    "start",
    "end",
    "shift_type",
    "area",
    "golden_employee",
    "algo_employee",
    "match",
    "algo_score",
    "golden_in_alternatives",
    "golden_alt_rank",
]

# ---------------------------------------------------------------------------
# Pipe-separated field helpers
# ---------------------------------------------------------------------------

PIPE = "|"


def pipe_join(values: list | None) -> str:
    """Join a list into a pipe-separated string. Empty/None -> empty string."""
    if not values:
        return ""
    return PIPE.join(str(v) for v in values if v is not None and str(v).strip())


def pipe_split(value: str | None) -> list[str]:
    """Split a pipe-separated string into a list. Empty/None -> empty list."""
    if not value or not str(value).strip():
        return []
    return [v.strip() for v in str(value).split(PIPE) if v.strip()]


# ---------------------------------------------------------------------------
# Type coercion helpers for reading CSV values
# ---------------------------------------------------------------------------


def to_float(value: str | None, default: float = 0.0) -> float:
    """Coerce a CSV string to float. Empty/None -> default."""
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def to_float_or_none(value: str | None) -> float | None:
    """Coerce a CSV string to float, returning None for empty values."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def to_int(value: str | None, default: int = 0) -> int:
    """Coerce a CSV string to int. Empty/None -> default."""
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def to_bool(value: str | None) -> bool:
    """Coerce a CSV string to bool. TRUE/true/1/True -> True, else False."""
    if value is None:
        return False
    return str(value).strip().upper() in ("TRUE", "1", "YES")


def fmt_bool(value: bool) -> str:
    """Format a bool for CSV output."""
    return "TRUE" if value else "FALSE"
