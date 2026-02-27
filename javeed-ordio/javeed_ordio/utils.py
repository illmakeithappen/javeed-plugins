from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timezone

UTC = timezone.utc
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

BERLIN_TZ = ZoneInfo("Europe/Berlin")


def to_iso_datetime(d: date, *, end_of_day: bool = False) -> str:
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    dt = datetime.combine(d, t, tzinfo=BERLIN_TZ)
    return dt.isoformat()


def parse_rfc2822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def hhmm_from_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(BERLIN_TZ).strftime("%H:%M")


def date_from_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(BERLIN_TZ).strftime("%Y-%m-%d")


def parse_hhmm_to_minutes(value: str) -> int | None:
    if not value or ":" not in value:
        return None
    try:
        hh, mm = value.split(":", 1)
        return int(hh) * 60 + int(mm)
    except Exception:
        return None


def calc_shift_hours(beginn: str, ende: str) -> float:
    start = parse_hhmm_to_minutes(beginn)
    end = parse_hhmm_to_minutes(ende)
    if start is None or end is None:
        return 0.0
    diff = end - start
    if diff < 0:
        diff += 24 * 60
    return diff / 60.0


def infer_shift_type(beginn: str, ende: str, working_area: str = "", note: str = "") -> str:
    area = (working_area or "").strip().lower()
    msg = f"{area} {(note or '').lower()}"
    if "theke" in msg:
        return "theke"
    if "bar" in msg:
        return "bar"
    if "kueche" in msg or "küche" in msg:
        return "kueche"

    start = parse_hhmm_to_minutes(beginn)
    end = parse_hhmm_to_minutes(ende)
    if start is None or end is None:
        return "normal"

    if start < 11 * 60:
        return "frueh"
    if start >= 16 * 60 or end >= 22 * 60:
        return "spaet"
    if start <= 11 * 60 and end >= 20 * 60:
        return "doppel"
    return "normal"


def month_key(datum: str) -> str:
    return datum[:7]


def week_key(datum: str) -> str:
    d = date.fromisoformat(datum)
    monday = d.fromordinal(d.toordinal() - d.weekday())
    return monday.isoformat()


def canonical_name(value: str) -> str:
    s = unicodedata.normalize("NFKD", (value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def first_name_key(first_name: str, last_name: str) -> str:
    return canonical_name(first_name)


def full_name(first_name: str, last_name: str) -> str:
    return f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_date(value: str) -> str:
    date.fromisoformat(value)
    return value
