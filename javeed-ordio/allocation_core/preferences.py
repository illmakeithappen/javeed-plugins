"""Shared preference parsing and scoring helpers."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from .time_utils import parse_hhmm_to_minutes, shift_labels


def _norm_text(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", str(text or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower()
    raw = raw.replace("ß", "ss")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def parse_simple_shift_preferences(note_text: str | None) -> dict[str, Any]:
    """Parse compact natural-language note hints into preference flags.

    This parser is intentionally conservative and focused on explicit signals.
    """
    if not note_text:
        return {}

    text = _norm_text(note_text)
    prefs: dict[str, Any] = {}

    if "kein wochenende" in text or "nicht wochenende" in text:
        prefs["no_weekend"] = True
    if "nur wochenende" in text:
        prefs["only_weekend"] = True

    if "lieber fruh" in text or "bevorzugt fruh" in text:
        prefs["prefer"] = "frueh"
    if "lieber spat" in text or "bevorzugt spat" in text:
        prefs["prefer"] = "spaet"

    max_shifts = re.search(r"max\s+(\d+)\s+schicht", text)
    if max_shifts:
        prefs["max_shifts_week"] = int(max_shifts.group(1))

    earliest = re.search(r"ab\s+(\d{1,2})\s*uhr", text)
    if earliest:
        prefs["earliest"] = int(earliest.group(1)) * 60

    latest = re.search(r"bis\s+(\d{1,2})\s*uhr", text)
    if latest:
        prefs["latest"] = int(latest.group(1)) * 60

    return prefs


def _is_preference_scope_active(scope: str | None, *, is_weekend: bool) -> bool:
    if not scope or scope == "always":
        return True
    if scope == "weekend":
        return is_weekend
    return False


def _resolve_preference_targets(prefs: dict[str, Any], *, is_weekend: bool) -> set[str]:
    targets: set[str] = set()

    prefer = prefs.get("prefer")
    if isinstance(prefer, str) and prefer in {"frueh", "spaet"}:
        targets.add(prefer)

    for key in ("frueh", "spaet"):
        scope = prefs.get(key)
        if isinstance(scope, str) and _is_preference_scope_active(scope, is_weekend=is_weekend):
            targets.add(key)

    return targets


def evaluate_shift_preferences(
    prefs: dict[str, Any],
    *,
    shift_type: str,
    date_iso: str,
    start: str,
    end: str,
    preference_bonus: float,
    day_violation_penalty: float,
    time_violation_penalty: float,
    violation_mode: str = "sum",
    flat_violation_penalty: float | None = None,
) -> tuple[float, list[str]]:
    """Evaluate preference adherence for a slot.

    Returns `(score_delta, violation_codes)`.
    - If no violation is present, score is either `preference_bonus` or `0`.
    - If violation(s) exist, score is negative (sum/flat mode).
    """
    if not prefs:
        return 0.0, []

    d = date.fromisoformat(date_iso)
    weekday = d.weekday()
    is_weekend = weekday >= 5

    start_min = parse_hhmm_to_minutes(start)
    end_min = parse_hhmm_to_minutes(end)

    day_violations = 0
    time_violations = 0
    violations: list[str] = []

    allowed_days = prefs.get("allowed_days")
    if isinstance(allowed_days, (set, list, tuple)) and weekday not in allowed_days:
        day_violations += 1
        violations.append("allowed_days")

    blocked_days = prefs.get("blocked_days")
    if isinstance(blocked_days, (set, list, tuple)) and weekday in blocked_days:
        day_violations += 1
        violations.append("blocked_days")

    if prefs.get("no_weekend") and is_weekend:
        day_violations += 1
        violations.append("no_weekend")
    if prefs.get("only_weekend") and not is_weekend:
        day_violations += 1
        violations.append("only_weekend")

    if "earliest" in prefs and start_min is not None and start_min < int(prefs["earliest"]):
        scope = str(prefs.get("earliest_scope", "always"))
        if _is_preference_scope_active(scope, is_weekend=is_weekend):
            time_violations += 1
            violations.append("starts_too_early")

    if "latest" in prefs and end_min is not None and end_min > int(prefs["latest"]):
        scope = str(prefs.get("latest_scope", "always"))
        if _is_preference_scope_active(scope, is_weekend=is_weekend):
            time_violations += 1
            violations.append("ends_too_late")

    if violations:
        if violation_mode == "flat":
            penalty = flat_violation_penalty
            if penalty is None:
                penalty = day_violation_penalty
            return float(penalty), violations

        penalty = (day_violations * day_violation_penalty) + (time_violations * time_violation_penalty)
        return float(penalty), violations

    labels = shift_labels(shift_type, start, end)
    targets = _resolve_preference_targets(prefs, is_weekend=is_weekend)
    if labels & targets:
        return float(preference_bonus), []
    return 0.0, []
