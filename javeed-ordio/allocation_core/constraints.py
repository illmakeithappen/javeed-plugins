"""Constraint classification and post-hoc validation for shift plans.

Classifies block reasons into obligatory (hard law/contract) vs. soft
(preferences, advisory limits) so the loose allocator can relax soft
constraints while keeping hard guarantees.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .allocator import (
    _arbzg_violations,
    _collect_existing_shifts,
    _effective_monthly_cap,
    _effective_weekly_cap,
    _employee_rule,
    _has_absence,
    _normalize_rule_lookup,
    calc_shift_hours,
    canonical_name,
    month_key,
    week_key,
)

# ---- Constraint categories -------------------------------------------------

OBLIGATORY_BLOCK_REASONS = frozenset({
    "overlap_same_day",
    "daily_hours_gt_10",
    "weekly_hours_limit",
    "rest_lt_11h",
    "consecutive_days_limit",
    "absence",
    "already_has_shift_same_day",
    "no_additional_shifts",
    "max_salary_limit",
})

SOFT_BLOCK_REASONS = frozenset({
    "monthly_hours_limit",
    "max_additional_monthly_hours",
    "max_weekly_hours",
    "no_weekend",
    "only_weekend",
    "starts_too_early",
    "ends_too_late",
    "allowed_days",
    "blocked_days",
})


def is_obligatory(reason: str) -> bool:
    return reason in OBLIGATORY_BLOCK_REASONS


def is_soft(reason: str) -> bool:
    return reason in SOFT_BLOCK_REASONS


# ---- Post-hoc validation ---------------------------------------------------

def validate_plan_hard_constraints(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate a plan dict against obligatory hard constraints.

    Returns a list of violation dicts, one per violated constraint:
        {slot_id, employee_id, employee_name, violation, detail}

    Used to audit LLM-generated plans after the fact.
    """
    violations: list[dict[str, Any]] = []
    employees = snapshot.get("employees", [])
    employee_by_id = {
        str(e.get("ordio_employee_id")): e
        for e in employees if e.get("ordio_employee_id")
    }
    rules_lookup = _normalize_rule_lookup(profile)
    policy = profile.get("policy", {}) or {}

    abs_by_emp: dict[str, list[dict[str, Any]]] = {}
    for ab in snapshot.get("absences", []):
        emp = str(ab.get("ordio_employee_id") or "")
        if emp:
            abs_by_emp.setdefault(emp, []).append(ab)

    existing_by_emp: dict[str, list[dict[str, Any]]] = {}
    for emp_id in employee_by_id:
        existing_by_emp[emp_id] = _collect_existing_shifts(snapshot, emp_id)

    # Build run-time shifts per employee from plan assignments
    run_by_emp: dict[str, list[dict[str, Any]]] = {}
    for a in plan.get("assignments", []):
        emp_id = str(a.get("ordio_employee_id", ""))
        run_by_emp.setdefault(emp_id, []).append({
            "date": a.get("date"),
            "start": a.get("start"),
            "end": a.get("end"),
            "hours": float(a.get("hours") or calc_shift_hours(
                a.get("start", ""), a.get("end", ""))),
        })

    for a in plan.get("assignments", []):
        slot_id = a.get("slot_id", "")
        emp_id = str(a.get("ordio_employee_id", ""))
        emp_name = a.get("employee_name", emp_id)
        emp = employee_by_id.get(emp_id)

        if not emp:
            violations.append({
                "slot_id": slot_id,
                "employee_id": emp_id,
                "employee_name": emp_name,
                "violation": "unknown_employee",
                "detail": f"Employee {emp_id} not found in snapshot",
            })
            continue

        slot_date = a.get("date", "")
        slot_start = a.get("start", "")
        slot_end = a.get("end", "")
        slot_hours = float(a.get("hours") or calc_shift_hours(slot_start, slot_end))

        rule = _employee_rule(emp, rules_lookup)

        # no_additional_shifts
        if rule.get("no_additional_shifts"):
            violations.append({
                "slot_id": slot_id,
                "employee_id": emp_id,
                "employee_name": emp_name,
                "violation": "no_additional_shifts",
                "detail": "Employee flagged as no_additional_shifts",
            })

        # Absence
        absences = abs_by_emp.get(emp_id, [])
        if _has_absence(absences, slot_date):
            violations.append({
                "slot_id": slot_id,
                "employee_id": emp_id,
                "employee_name": emp_name,
                "violation": "absence",
                "detail": f"Employee absent on {slot_date}",
            })

        # ArbZG: use all OTHER run shifts for this employee (excluding this one)
        other_run = [
            s for s in run_by_emp.get(emp_id, [])
            if not (s["date"] == slot_date and s["start"] == slot_start and s["end"] == slot_end)
        ]
        existing = existing_by_emp.get(emp_id, [])
        weekly_cap = _effective_weekly_cap(emp, rule)
        max_consecutive = int(policy.get("max_consecutive_days") or 5)

        slot_dict = {"date": slot_date, "start": slot_start, "end": slot_end, "hours": slot_hours}
        arbzg = _arbzg_violations(existing, other_run, slot_dict, weekly_cap, max_consecutive)
        for v in arbzg:
            violations.append({
                "slot_id": slot_id,
                "employee_id": emp_id,
                "employee_name": emp_name,
                "violation": v,
                "detail": f"ArbZG violation: {v}",
            })

        # Salary limit
        wage = float(emp.get("hourly_wage") or 0)
        max_salary = float(emp.get("max_salary") or 0)
        if wage > 0 and max_salary > 0:
            from .allocator import _hours_in_month
            existing_month_hours = _hours_in_month(existing, month_key(slot_date))
            run_month_hours = _hours_in_month(other_run, month_key(slot_date))
            projected = (existing_month_hours + run_month_hours + slot_hours) * wage
            if projected > max_salary:
                violations.append({
                    "slot_id": slot_id,
                    "employee_id": emp_id,
                    "employee_name": emp_name,
                    "violation": "max_salary_limit",
                    "detail": f"Projected salary {projected:.2f} > max {max_salary:.2f}",
                })

    return violations
