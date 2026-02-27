from __future__ import annotations

import copy
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .preferences import (
    evaluate_shift_preferences,
    parse_simple_shift_preferences,
)
from .roles import compute_role_match_score
from .time_utils import (
    calc_shift_hours,
    parse_hhmm_to_minutes,
    time_overlap,
)

UTC = timezone.utc


def canonical_name(value: str) -> str:
    s = unicodedata.normalize("NFKD", (value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def month_key(datum: str) -> str:
    return datum[:7]


def week_key(datum: str) -> str:
    d = date.fromisoformat(datum)
    monday = d.fromordinal(d.toordinal() - d.weekday())
    return monday.isoformat()


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fairness_overview(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per_employee = defaultdict(lambda: {"hours": 0.0, "slots": 0, "target_hours": 0.0})
    for row in assignments:
        name = row.get("employee_name") or row.get("ordio_employee_id")
        item = per_employee[name]
        item["hours"] += float(row.get("hours") or 0)
        item["slots"] += 1
        if row.get("target_hours") is not None:
            item["target_hours"] = float(row.get("target_hours") or 0)

    result = []
    for name, values in per_employee.items():
        target = values["target_hours"]
        delta = values["hours"] - target if target else None
        result.append(
            {
                "employee_name": name,
                "assigned_hours": round(values["hours"], 2),
                "assigned_slots": int(values["slots"]),
                "target_hours": round(target, 2) if target else None,
                "delta_to_target": round(delta, 2) if delta is not None else None,
            }
        )

    result.sort(key=lambda row: row["assigned_hours"], reverse=True)
    return result


SCORING = {
    "applicant_bonus": 80,
    "rest_max": 40,
    "fairness_max": 30,
    "role_exact": 20,
    "role_partial": 10,
    "fixed_bonus": 12,
    "pref_bonus": 15,
    "skill_bonus": 12,
    "salary_warning_penalty": -12,
}

ROLE_AFFINITY: dict[str, set[str]] = {
    "service": {"frueh", "normal", "spaet", "doppel", "service", "theke"},
    "kellner": {"frueh", "normal", "spaet", "service", "theke"},
    "bar": {"spaet", "normal", "bar", "theke"},
    "koch": {"frueh", "normal", "spaet", "kueche"},
    "kueche": {"frueh", "normal", "spaet", "kueche"},
}


@dataclass
class CandidateEvaluation:
    ordio_employee_id: str
    employee_name: str
    score: float
    blocked: bool
    is_applicant: bool
    reasons: list[str]
    blocked_reasons: list[str]
    score_detail: dict[str, float]
    hours_existing_month: float
    hours_run_month: float
    target_hours: float | None
    week_shifts: int
    projected_salary: float | None
    soft_violations: list[str] | None = None


@dataclass
class PlanState:
    assignments: list[dict[str, Any]]
    unassigned: list[dict[str, Any]]
    run_assignments_by_emp: dict[str, list[dict[str, Any]]]
    run_hours_by_emp_month: dict[tuple[str, str], float]
    run_hours_by_emp_week: dict[tuple[str, str], float]
    run_shift_count_by_emp_week: dict[tuple[str, str], int]
    run_days_by_emp: dict[str, set[str]]
    run_total_hours_by_emp: dict[str, float]


def _normalize_rule_lookup(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    rules = profile.get("employee_rules", {}) or {}
    for key, value in rules.items():
        out[canonical_name(key)] = value
    return out


def _employee_rule(emp: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    first = canonical_name(emp.get("first_name", ""))
    full = canonical_name(emp.get("full_name", ""))
    user = canonical_name(emp.get("username", ""))
    for k in (full, first, user):
        if k and k in lookup:
            return lookup[k]
    return {}


def _time_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    return time_overlap(start_a, end_a, start_b, end_b)


def _parse_preferences(note_text: str) -> dict[str, Any]:
    return parse_simple_shift_preferences(note_text)


def _preference_score_and_violations(prefs: dict[str, Any], slot: dict[str, Any]) -> tuple[float, list[str]]:
    return evaluate_shift_preferences(
        prefs,
        shift_type=str(slot.get("shift_type", "")),
        date_iso=str(slot.get("date", "")),
        start=str(slot.get("start", "")),
        end=str(slot.get("end", "")),
        preference_bonus=float(SCORING["pref_bonus"]),
        day_violation_penalty=-35.0,
        time_violation_penalty=-35.0,
        violation_mode="flat",
        flat_violation_penalty=-35.0,
    )


def _hours_in_month(shifts: list[dict[str, Any]], month: str) -> float:
    total = 0.0
    for s in shifts:
        if month_key(s.get("date", "")) == month:
            total += float(s.get("hours") or calc_shift_hours(s.get("start", ""), s.get("end", "")))
    return total


def _hours_in_week(shifts: list[dict[str, Any]], wk: str) -> float:
    total = 0.0
    for s in shifts:
        if week_key(s.get("date", "")) == wk:
            total += float(s.get("hours") or calc_shift_hours(s.get("start", ""), s.get("end", "")))
    return total


def _count_shifts_in_week(shifts: list[dict[str, Any]], wk: str) -> int:
    return sum(1 for s in shifts if week_key(s.get("date", "")) == wk)


def _effective_monthly_cap(emp: dict[str, Any], rule: dict[str, Any]) -> float | None:
    if rule.get("disable_max_hours"):
        return None

    if rule.get("max_monthly_hours") is not None:
        return float(rule["max_monthly_hours"])
    if rule.get("target_weekly_hours") is not None:
        return float(rule["target_weekly_hours"]) * 4.33

    employment = canonical_name(emp.get("employment", ""))
    wage = float(emp.get("hourly_wage") or 0)
    max_salary = float(emp.get("max_salary") or 0)

    if "mini" in employment:
        cap = 43.0
        if wage > 0 and max_salary > 0:
            cap = min(cap, max_salary / wage)
        return cap
    if "werki" in employment or "werk" in employment:
        return 20.0 * 4.33

    if wage > 0 and max_salary > 0:
        return max_salary / wage
    return 160.0


def _effective_weekly_cap(emp: dict[str, Any], rule: dict[str, Any]) -> float:
    if rule.get("max_weekly_hours") is not None:
        return float(rule["max_weekly_hours"])

    employment = canonical_name(emp.get("employment", ""))
    if "werki" in employment or "werk" in employment:
        return 20.0

    return 48.0


def _target_hours_for_scoring(emp: dict[str, Any], rule: dict[str, Any]) -> float | None:
    if rule.get("target_weekly_hours") is not None:
        return float(rule["target_weekly_hours"]) * 4.33
    if rule.get("max_monthly_hours") is not None:
        return float(rule["max_monthly_hours"])
    return _effective_monthly_cap(emp, rule)


def _derive_fixed_patterns(assigned_shifts: list[dict[str, Any]]) -> dict[tuple[str, int, str, str], int]:
    counts: Counter[tuple[str, int, str, str]] = Counter()
    for s in assigned_shifts:
        emp = s.get("ordio_employee_id")
        datum = s.get("date")
        if not emp or not datum:
            continue
        wd = date.fromisoformat(datum).weekday()
        key = (str(emp), wd, s.get("start", ""), s.get("end", ""))
        counts[key] += 1
    return {k: v for k, v in counts.items() if v >= 3}


def _collect_existing_shifts(snapshot: dict[str, Any], emp_id: str) -> list[dict[str, Any]]:
    rows = []
    for s in snapshot.get("assigned_shifts", []):
        if str(s.get("ordio_employee_id")) != emp_id:
            continue
        rows.append(
            {
                "date": s.get("date"),
                "start": s.get("start"),
                "end": s.get("end"),
                "hours": float(s.get("hours") or calc_shift_hours(s.get("start", ""), s.get("end", ""))),
            }
        )
    return rows


def _has_absence(absences: list[dict[str, Any]], slot_date: str) -> bool:
    return any(a.get("start_date", "") <= slot_date <= a.get("end_date", "") for a in absences)


def _arbzg_violations(
    existing: list[dict[str, Any]],
    run: list[dict[str, Any]],
    slot: dict[str, Any],
    weekly_limit: float,
    max_consecutive_days: int,
) -> list[str]:
    violations: list[str] = []

    all_shifts = existing + run
    datum = slot["date"]
    start = slot["start"]
    end = slot["end"]
    hours = float(slot.get("hours") or calc_shift_hours(start, end))

    # Same-day overlap and daily 10h.
    day_hours = hours
    for s in all_shifts:
        if s["date"] != datum:
            continue
        day_hours += float(s["hours"])
        if _time_overlap(start, end, s["start"], s["end"]):
            violations.append("overlap_same_day")
    if day_hours > 10:
        violations.append("daily_hours_gt_10")

    # Weekly cap.
    wk = week_key(datum)
    week_hours = hours + _hours_in_week(all_shifts, wk)
    if week_hours > weekly_limit:
        violations.append("weekly_hours_limit")

    # 11h rest before/after adjacent days.
    prev_day = (date.fromisoformat(datum) - timedelta(days=1)).isoformat()
    next_day = (date.fromisoformat(datum) + timedelta(days=1)).isoformat()
    slot_start = parse_hhmm_to_minutes(start) or 0
    slot_end = parse_hhmm_to_minutes(end) or 0
    for s in all_shifts:
        if s["date"] == prev_day:
            prev_end = parse_hhmm_to_minutes(s["end"]) or 0
            gap = (24 * 60 - prev_end) + slot_start
            if gap < 11 * 60:
                violations.append("rest_lt_11h")
        if s["date"] == next_day:
            next_start = parse_hhmm_to_minutes(s["start"]) or 0
            gap = (24 * 60 - slot_end) + next_start
            if gap < 11 * 60:
                violations.append("rest_lt_11h")

    # Consecutive days.
    working_days = {datum}
    for s in all_shifts:
        if s.get("date"):
            working_days.add(s["date"])

    d = date.fromisoformat(datum)
    streak = 1
    prev = d - timedelta(days=1)
    while prev.isoformat() in working_days:
        streak += 1
        prev -= timedelta(days=1)
    nxt = d + timedelta(days=1)
    while nxt.isoformat() in working_days:
        streak += 1
        nxt += timedelta(days=1)
    if streak > max_consecutive_days:
        violations.append("consecutive_days_limit")

    return sorted(set(violations))


def _role_score(employee: dict[str, Any], slot: dict[str, Any]) -> float:
    role = canonical_name(employee.get("role", ""))
    shift_type = canonical_name(slot.get("shift_type", ""))
    return compute_role_match_score(
        role,
        shift_type,
        affinity_map=ROLE_AFFINITY,
        exact_score=float(SCORING["role_exact"]),
        affinity_score=float(SCORING["role_exact"]),
        partial_score=float(SCORING["role_partial"]),
    )


def _skill_score(employee: dict[str, Any], slot: dict[str, Any], rule: dict[str, Any]) -> float:
    tags = {canonical_name(slot.get("shift_type", "")), canonical_name(slot.get("working_area", ""))}
    skills = {canonical_name(s) for s in employee.get("skills", [])}
    pref_areas = {canonical_name(s) for s in rule.get("preferred_working_areas", [])}

    if tags & skills:
        return float(SCORING["skill_bonus"])
    if tags & pref_areas:
        return float(SCORING["skill_bonus"])
    return 0.0


def _fixed_shift_bonus(
    fixed_patterns: dict[tuple[str, int, str, str], int],
    emp_id: str,
    slot: dict[str, Any],
) -> float:
    wd = date.fromisoformat(slot["date"]).weekday()
    key_exact = (emp_id, wd, slot.get("start", ""), slot.get("end", ""))
    if key_exact in fixed_patterns:
        return float(SCORING["fixed_bonus"])
    return 0.0


def _score_candidate(
    *,
    employee: dict[str, Any],
    slot: dict[str, Any],
    rule: dict[str, Any],
    prefs: dict[str, Any],
    is_applicant: bool,
    existing_shifts: list[dict[str, Any]],
    run_shifts: list[dict[str, Any]],
    absences: list[dict[str, Any]],
    fixed_patterns: dict[tuple[str, int, str, str], int],
    policy: dict[str, Any],
    run_extra_month_hours: float,
    constraint_mode: str = "strict",
) -> CandidateEvaluation:
    emp_id = str(employee.get("ordio_employee_id"))
    emp_name = employee.get("full_name") or emp_id
    slot_hours = float(slot.get("hours") or calc_shift_hours(slot.get("start", ""), slot.get("end", "")))
    slot_month = month_key(slot["date"])
    slot_week = week_key(slot["date"])

    reasons: list[str] = []
    blocked_reasons: list[str] = []

    if rule.get("no_additional_shifts"):
        blocked_reasons.append("no_additional_shifts")

    if _has_absence(absences, slot["date"]):
        blocked_reasons.append("absence")

    # No duplicate day assignment.
    if any(s["date"] == slot["date"] for s in existing_shifts + run_shifts):
        blocked_reasons.append("already_has_shift_same_day")

    # Hard legal / contract checks.
    weekly_cap = _effective_weekly_cap(employee, rule)
    max_consecutive_days = int(policy.get("max_consecutive_days") or 5)
    arbzg = _arbzg_violations(existing_shifts, run_shifts, slot, weekly_cap, max_consecutive_days)
    blocked_reasons.extend(arbzg)

    soft_violations: list[str] = []

    month_cap = _effective_monthly_cap(employee, rule)
    existing_month_hours = _hours_in_month(existing_shifts, slot_month)
    run_month_hours = _hours_in_month(run_shifts, slot_month)
    projected_month_hours = existing_month_hours + run_month_hours + slot_hours
    if month_cap is not None and projected_month_hours > month_cap:
        if constraint_mode == "loose":
            soft_violations.append("monthly_hours_limit")
        else:
            blocked_reasons.append("monthly_hours_limit")

    if rule.get("max_additional_monthly_hours") is not None:
        extra_cap = float(rule["max_additional_monthly_hours"])
        if run_extra_month_hours + slot_hours > extra_cap:
            if constraint_mode == "loose":
                soft_violations.append("max_additional_monthly_hours")
            else:
                blocked_reasons.append("max_additional_monthly_hours")

    if rule.get("max_weekly_hours") is not None:
        extra_week = _hours_in_week(run_shifts, slot_week) + slot_hours
        if extra_week > float(rule["max_weekly_hours"]):
            if constraint_mode == "loose":
                soft_violations.append("max_weekly_hours")
            else:
                blocked_reasons.append("max_weekly_hours")

    # Salary guard.
    wage = float(employee.get("hourly_wage") or 0)
    max_salary = float(employee.get("max_salary") or 0)
    projected_salary = None
    if wage > 0 and max_salary > 0:
        projected_salary = projected_month_hours * wage
        if projected_salary > max_salary:
            blocked_reasons.append("max_salary_limit")

    pref_score, pref_viol = _preference_score_and_violations(prefs, slot)
    if pref_viol:
        if constraint_mode == "loose":
            soft_violations.extend(pref_viol)
        else:
            blocked_reasons.extend(pref_viol)

    blocked = bool(blocked_reasons)

    target_hours = _target_hours_for_scoring(employee, rule)
    remaining_hours = max((target_hours or 0) - (existing_month_hours + run_month_hours), 0) if target_hours else 0
    if target_hours and target_hours > 0:
        rest_score = min((remaining_hours / target_hours) * SCORING["rest_max"], SCORING["rest_max"])
    else:
        rest_score = SCORING["rest_max"] * 0.5

    week_shift_count = _count_shifts_in_week(existing_shifts + run_shifts, slot_week)
    fairness_score = max(SCORING["fairness_max"] - 6 * week_shift_count, 0)
    role_score = _role_score(employee, slot)
    skill_score = _skill_score(employee, slot, rule)
    fixed_bonus = _fixed_shift_bonus(fixed_patterns, emp_id, slot)
    applicant_bonus = SCORING["applicant_bonus"] if is_applicant else 0

    salary_penalty = 0.0
    if projected_salary is not None and max_salary > 0 and projected_salary > 0.9 * max_salary:
        salary_penalty = float(SCORING["salary_warning_penalty"])

    # Shift type preference from profile.
    preferred_types = {canonical_name(v) for v in rule.get("preferred_shift_types", [])}
    if preferred_types and canonical_name(slot.get("shift_type", "")) in preferred_types:
        pref_score += SCORING["pref_bonus"] * 0.5

    score_detail = {
        "rest": round(float(rest_score), 2),
        "fairness": round(float(fairness_score), 2),
        "role": round(float(role_score), 2),
        "skill": round(float(skill_score), 2),
        "fixed": round(float(fixed_bonus), 2),
        "preference": round(float(pref_score), 2),
        "applicant": round(float(applicant_bonus), 2),
        "salary": round(float(salary_penalty), 2),
    }

    score = sum(score_detail.values()) if not blocked else 0.0

    # Build reasoning labels from highest absolute component.
    components = sorted(score_detail.items(), key=lambda kv: abs(kv[1]), reverse=True)
    for key, value in components:
        if value == 0:
            continue
        if key == "applicant" and value > 0:
            reasons.append("applied_for_shift")
        elif key == "rest" and value > 0:
            reasons.append("remaining_target_hours")
        elif key == "fairness" and value > 0:
            reasons.append("fair_distribution")
        elif key == "role" and value > 0:
            reasons.append("role_shift_match")
        elif key == "skill" and value > 0:
            reasons.append("skill_working_area_match")
        elif key == "fixed" and value > 0:
            reasons.append("historical_fixed_pattern")
        elif key == "preference" and value > 0:
            reasons.append("matches_employee_preferences")
        elif key == "salary" and value < 0:
            reasons.append("near_salary_limit")
        if len(reasons) >= 3:
            break

    return CandidateEvaluation(
        ordio_employee_id=emp_id,
        employee_name=emp_name,
        score=round(score, 2),
        blocked=blocked,
        is_applicant=is_applicant,
        reasons=reasons,
        blocked_reasons=sorted(set(blocked_reasons)),
        score_detail=score_detail,
        hours_existing_month=round(existing_month_hours, 2),
        hours_run_month=round(run_month_hours, 2),
        target_hours=round(target_hours, 2) if target_hours is not None else None,
        week_shifts=week_shift_count,
        projected_salary=round(projected_salary, 2) if projected_salary is not None else None,
        soft_violations=soft_violations if soft_violations else None,
    )


def _initial_state() -> PlanState:
    return PlanState(
        assignments=[],
        unassigned=[],
        run_assignments_by_emp=defaultdict(list),
        run_hours_by_emp_month=defaultdict(float),
        run_hours_by_emp_week=defaultdict(float),
        run_shift_count_by_emp_week=defaultdict(int),
        run_days_by_emp=defaultdict(set),
        run_total_hours_by_emp=defaultdict(float),
    )


def _slot_sort_key(slot: dict[str, Any]) -> tuple[Any, ...]:
    has_apps = 1 if (slot.get("applicant_employee_ids") or []) else 0
    return (-has_apps, slot.get("date", ""), slot.get("start", ""), slot.get("slot_id", ""))


def generate_plan(
    snapshot: dict[str, Any],
    *,
    range_from: str,
    range_to: str,
    profile_name: str,
    profile: dict[str, Any],
    constraint_mode: str = "strict",
) -> dict[str, Any]:
    employees = snapshot.get("employees", [])
    employee_by_id = {str(e.get("ordio_employee_id")): e for e in employees if e.get("ordio_employee_id")}

    rules_lookup = _normalize_rule_lookup(profile)
    policy = copy.deepcopy(profile.get("policy", {})) if isinstance(profile.get("policy"), dict) else {}

    open_slots = [
        {
            **slot,
            "hours": float(slot.get("hours") or calc_shift_hours(slot.get("start", ""), slot.get("end", ""))),
        }
        for slot in snapshot.get("open_shifts", [])
        if range_from <= slot.get("date", "") <= range_to
    ]
    open_slots.sort(key=_slot_sort_key)

    assigned_shifts = snapshot.get("assigned_shifts", [])
    fixed_patterns = _derive_fixed_patterns(assigned_shifts)

    abs_by_emp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ab in snapshot.get("absences", []):
        emp = str(ab.get("ordio_employee_id") or "")
        if emp:
            abs_by_emp[emp].append(ab)

    existing_by_emp: dict[str, list[dict[str, Any]]] = {}
    for emp_id in employee_by_id:
        existing_by_emp[emp_id] = _collect_existing_shifts(snapshot, emp_id)

    state = _initial_state()
    evaluation_matrix: dict[str, list[dict[str, Any]]] = {}

    for slot in open_slots:
        applicants = {str(v) for v in (slot.get("applicant_employee_ids") or [])}
        evals: list[CandidateEvaluation] = []

        for emp_id, emp in employee_by_id.items():
            rule = _employee_rule(emp, rules_lookup)
            prefs = _parse_preferences(str(rule.get("notes") or ""))
            run_shifts = state.run_assignments_by_emp.get(emp_id, [])
            eval_row = _score_candidate(
                employee=emp,
                slot=slot,
                rule=rule,
                prefs=prefs,
                is_applicant=emp_id in applicants,
                existing_shifts=existing_by_emp.get(emp_id, []),
                run_shifts=run_shifts,
                absences=abs_by_emp.get(emp_id, []),
                fixed_patterns=fixed_patterns,
                policy=policy,
                run_extra_month_hours=state.run_hours_by_emp_month[(emp_id, month_key(slot["date"]))],
                constraint_mode=constraint_mode,
            )
            evals.append(eval_row)

        # deterministic ordering
        evals.sort(key=lambda x: (0 if not x.blocked else 1, -x.score, canonical_name(x.employee_name), x.ordio_employee_id))

        slot_id = slot.get("slot_id", "")
        evaluation_matrix[slot_id] = [
            {
                "employee_id": e.ordio_employee_id,
                "employee_name": e.employee_name,
                "score": e.score,
                "blocked": e.blocked,
                "is_applicant": e.is_applicant,
                "blocked_reasons": e.blocked_reasons,
                "score_detail": e.score_detail,
                "target_hours": e.target_hours,
                "month_hours_before": e.hours_run_month,
                **({"soft_violations": e.soft_violations} if e.soft_violations else {}),
            }
            for e in evals
        ]

        valid = [e for e in evals if not e.blocked]
        has_applicants = bool(applicants)

        selected_pool = valid
        if has_applicants and policy.get("prefer_applicants", True):
            applicant_pool = [e for e in valid if e.is_applicant]
            if applicant_pool:
                selected_pool = applicant_pool

        if not selected_pool:
            reason = "no_valid_candidate"
            if not evals:
                reason = "no_candidates_available"
            elif all(e.blocked for e in evals):
                reason = "all_candidates_blocked_by_constraints"
            elif has_applicants:
                reason = "all_applicants_blocked"

            state.unassigned.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "ordio_shift_id": slot.get("ordio_shift_id"),
                    "date": slot.get("date"),
                    "start": slot.get("start"),
                    "end": slot.get("end"),
                    "shift_type": slot.get("shift_type"),
                    "working_area": slot.get("working_area"),
                    "reason": reason,
                    "top_candidates": [
                        {
                            "ordio_employee_id": e.ordio_employee_id,
                            "employee_name": e.employee_name,
                            "blocked_reasons": e.blocked_reasons,
                            "score": e.score,
                            "is_applicant": e.is_applicant,
                        }
                        for e in evals[:5]
                    ],
                }
            )
            continue

        best = selected_pool[0]
        emp_id = best.ordio_employee_id
        slot_hours = float(slot.get("hours") or 0)
        m_key = month_key(slot["date"])
        w_key = week_key(slot["date"])

        state.run_assignments_by_emp[emp_id].append(
            {
                "date": slot["date"],
                "start": slot["start"],
                "end": slot["end"],
                "hours": slot_hours,
            }
        )
        state.run_hours_by_emp_month[(emp_id, m_key)] += slot_hours
        state.run_hours_by_emp_week[(emp_id, w_key)] += slot_hours
        state.run_shift_count_by_emp_week[(emp_id, w_key)] += 1
        state.run_days_by_emp[emp_id].add(slot["date"])
        state.run_total_hours_by_emp[emp_id] += slot_hours

        alternatives = []
        for e in evals[:8]:
            if e.ordio_employee_id == best.ordio_employee_id:
                continue
            alternatives.append(
                {
                    "ordio_employee_id": e.ordio_employee_id,
                    "employee_name": e.employee_name,
                    "score": e.score,
                    "blocked": e.blocked,
                    "is_applicant": e.is_applicant,
                    "reasons": e.reasons,
                    "blocked_reasons": e.blocked_reasons,
                    "score_detail": e.score_detail,
                }
            )

        assignment_kind = "applicant"
        if not best.is_applicant:
            assignment_kind = "recommendation_without_applicant" if not has_applicants else "recommendation_despite_applicants"

        state.assignments.append(
            {
                "assignment_id": f"{slot.get('slot_id')}::{emp_id}",
                "slot_id": slot.get("slot_id"),
                "ordio_shift_id": slot.get("ordio_shift_id"),
                "date": slot.get("date"),
                "start": slot.get("start"),
                "end": slot.get("end"),
                "hours": round(slot_hours, 2),
                "shift_type": slot.get("shift_type"),
                "working_area": slot.get("working_area"),
                "note": slot.get("note", ""),
                "ordio_employee_id": emp_id,
                "employee_name": best.employee_name,
                "score": best.score,
                "is_applicant": best.is_applicant,
                "assignment_kind": assignment_kind,
                "reasons": best.reasons,
                "blocked_reasons": best.blocked_reasons,
                "score_detail": best.score_detail,
                "week_shifts": best.week_shifts,
                "existing_month_hours": best.hours_existing_month,
                "run_month_hours_before": best.hours_run_month,
                "target_hours": best.target_hours,
                "projected_salary": best.projected_salary,
                "alternatives": alternatives,
                **({"soft_violations": best.soft_violations} if best.soft_violations else {}),
            }
        )

    total_slots = len(state.assignments) + len(state.unassigned)
    fill_rate = round((len(state.assignments) / total_slots) * 100, 1) if total_slots else 0.0

    fairness = fairness_overview(state.assignments)

    plan = {
        "plan_id": f"plan-{uuid4().hex[:12]}",
        "generated_at": now_utc_iso(),
        "snapshot_id": snapshot.get("snapshot_id"),
        "betrieb": snapshot.get("betrieb"),
        "range": {"from": range_from, "to": range_to},
        "profile": profile_name,
        "profile_description": profile.get("description", ""),
        "assignments": state.assignments,
        "unassigned": state.unassigned,
        "metrics": {
            "assigned_slots": len(state.assignments),
            "unassigned_slots": len(state.unassigned),
            "total_slots": total_slots,
            "fill_rate": fill_rate,
            "assignment_kind_counts": dict(Counter(a["assignment_kind"] for a in state.assignments)),
        },
        "fairness": fairness,
        "explanation": {
            "constraint_policy": policy,
            "notes": [
                "Allocation is deterministic and read-only. No write-back to Ordio is performed.",
                "Candidates blocked by legal/contract/profile constraints are never assigned.",
            ],
        },
        "evaluation_matrix": evaluation_matrix,
    }

    # Collect all soft violations for loose mode
    if constraint_mode == "loose":
        all_soft = []
        for a in state.assignments:
            for sv in a.get("soft_violations", []):
                all_soft.append({
                    "slot_id": a.get("slot_id"),
                    "employee_id": a.get("ordio_employee_id"),
                    "violation": sv,
                })
        plan["soft_violations"] = all_soft

    return plan


def explain_assignment(plan: dict[str, Any], assignment_id: str) -> dict[str, Any]:
    for item in plan.get("assignments", []):
        if item.get("assignment_id") == assignment_id:
            return {
                "assignment_id": assignment_id,
                "employee": item.get("employee_name"),
                "slot": {
                    "date": item.get("date"),
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "shift_type": item.get("shift_type"),
                    "working_area": item.get("working_area"),
                },
                "score": item.get("score"),
                "reasons": item.get("reasons", []),
                "score_detail": item.get("score_detail", {}),
                "alternatives": item.get("alternatives", [])[:5],
            }
    raise KeyError(f"assignment_id not found: {assignment_id}")
