"""Shared time utilities used by allocation scoring logic."""

from __future__ import annotations


def parse_hhmm_to_minutes(value: str | None) -> int | None:
    """Parse HH:MM into minutes after midnight."""
    if not value or ":" not in str(value):
        return None
    try:
        hh, mm = str(value).split(":", 1)
        h = int(hh)
        m = int(mm)
    except (TypeError, ValueError):
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h * 60 + m


def calc_shift_hours(start: str | None, end: str | None) -> float:
    """Calculate duration for a shift in decimal hours."""
    s = parse_hhmm_to_minutes(start)
    e = parse_hhmm_to_minutes(end)
    if s is None or e is None:
        return 0.0
    diff = e - s
    if diff < 0:
        diff += 24 * 60
    return diff / 60.0


def time_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Return True if two HH:MM time ranges overlap (supports overnight ranges)."""
    a0 = parse_hhmm_to_minutes(start_a)
    a1 = parse_hhmm_to_minutes(end_a)
    b0 = parse_hhmm_to_minutes(start_b)
    b1 = parse_hhmm_to_minutes(end_b)
    if None in (a0, a1, b0, b1):
        return False

    def intervals(start: int, end: int) -> list[tuple[int, int]]:
        if end > start:
            return [(start, end)]
        return [(start, 24 * 60), (0, end)]

    for x0, x1 in intervals(a0, a1):
        for y0, y1 in intervals(b0, b1):
            if max(x0, y0) < min(x1, y1):
                return True
    return False


def shift_labels(shift_type: str | None, start: str | None, end: str | None) -> set[str]:
    """Map shift metadata to coarse labels used for preference matching."""
    labels: set[str] = set()
    typ = str(shift_type or "").lower()
    if "frueh" in typ:
        labels.add("frueh")
    if "spaet" in typ:
        labels.add("spaet")

    start_min = parse_hhmm_to_minutes(start)
    end_min = parse_hhmm_to_minutes(end)
    if start_min is not None:
        if start_min < 11 * 60:
            labels.add("frueh")
        if start_min >= 16 * 60:
            labels.add("spaet")
    if end_min is not None and end_min >= 21 * 60:
        labels.add("spaet")
    return labels
