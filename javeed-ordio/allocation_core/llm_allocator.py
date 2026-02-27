"""LLM-based shift allocation: refinement and pure generation.

Provides two modes:
  1. refine_plan_llm()        — Take a loose algorithmic plan and optimise it via LLM
  2. generate_plan_pure_llm() — Generate an entire plan from raw input data via LLM

Both return the standard plan dict structure so downstream code (writer, xlsx)
works unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import date
from typing import Any
from uuid import uuid4

from .allocator import (
    _collect_existing_shifts,
    _employee_rule,
    _normalize_rule_lookup,
    _score_candidate,
    _derive_fixed_patterns,
    _parse_preferences,
    calc_shift_hours,
    canonical_name,
    fairness_overview,
    month_key,
    now_utc_iso,
    week_key,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anthropic client helpers (same pattern as directives.py)
# ---------------------------------------------------------------------------

def _get_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key, timeout=120.0)


def _get_model() -> str:
    return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def _call_llm(prompt: str, *, max_tokens: int = 8192) -> str:
    """Call the Anthropic API with 3-attempt retry on 429/529."""
    import anthropic

    client = _get_client()
    model = _get_model()

    for attempt in range(3):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text if message.content else ""
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 529) and attempt < 2:
                wait = 2 ** (attempt + 1)
                logger.warning("API %s, retrying in %ds ...", exc.status_code, wait)
                time.sleep(wait)
            else:
                raise
    return ""


def _extract_json(text: str) -> Any:
    """Extract first JSON object or array from LLM response text."""
    # Try code block first
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    # Fallback: find first { ... }
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return json.loads(text[start : i + 1])
    raise ValueError("No JSON object found in LLM response")


# ---------------------------------------------------------------------------
# Loose refinement (Phase 2)
# ---------------------------------------------------------------------------

def refine_plan_llm(
    loose_plan: dict[str, Any],
    snapshot: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Take a loose algorithmic plan and refine it via LLM.

    The LLM sees the current assignments, unassigned slots, employee profiles,
    soft constraint violations, and vorgaben. It can reassign, swap, or fill
    gaps while respecting hard constraints.

    Returns a new plan dict. Falls back to the loose plan unchanged if LLM fails.
    """
    try:
        assignments = loose_plan.get("assignments", [])
        unassigned = loose_plan.get("unassigned", [])
        employees = snapshot.get("employees", [])
        soft_violations = loose_plan.get("soft_violations", [])

        # Build compact representations
        assigned_summary = []
        for a in assignments:
            assigned_summary.append({
                "slot_id": a["slot_id"],
                "date": a["date"],
                "start": a["start"],
                "end": a["end"],
                "shift_type": a.get("shift_type", ""),
                "employee_id": a["ordio_employee_id"],
                "employee_name": a["employee_name"],
                "score": a["score"],
            })

        unassigned_summary = []
        for u in unassigned:
            unassigned_summary.append({
                "slot_id": u["slot_id"],
                "date": u["date"],
                "start": u["start"],
                "end": u["end"],
                "shift_type": u.get("shift_type", ""),
                "reason": u.get("reason", ""),
            })

        employee_summary = []
        rules_lookup = _normalize_rule_lookup(profile)
        for emp in employees:
            rule = _employee_rule(emp, rules_lookup)
            employee_summary.append({
                "employee_id": str(emp.get("ordio_employee_id")),
                "name": emp.get("full_name", ""),
                "role": emp.get("role", ""),
                "employment": emp.get("employment", ""),
                "target_weekly_hours": rule.get("target_weekly_hours"),
                "max_monthly_hours": rule.get("max_monthly_hours"),
                "no_additional_shifts": rule.get("no_additional_shifts", False),
                "notes": rule.get("notes", ""),
            })

        prompt = f"""Du bist ein Schichtplanungs-Optimierer. Du bekommst einen algorithmisch
erstellten Entwurf eines Schichtplans. Deine Aufgabe: Optimiere den Plan.

AKTUELLE ZUWEISUNGEN:
{json.dumps(assigned_summary, ensure_ascii=False, indent=1)}

NICHT BESETZTE SCHICHTEN:
{json.dumps(unassigned_summary, ensure_ascii=False, indent=1)}

MITARBEITER-PROFILE:
{json.dumps(employee_summary, ensure_ascii=False, indent=1)}

WEICHE CONSTRAINT-VERLETZUNGEN IM AKTUELLEN PLAN:
{json.dumps(soft_violations, ensure_ascii=False, indent=1)}

REGELN:
1. NIEMALS harte Constraints verletzen: Ueberlappung, >10h/Tag, >48h/Woche, <11h Ruhezeit, >5 Tage am Stueck, Abwesenheit, Gehaltslimit
2. Versuche unbesetzte Schichten zu fuellen
3. Verbessere die Fairness (gleichmaessige Stundenverteilung)
4. Respektiere weiche Praeferenzen wenn moeglich
5. Behalte gut passende Zuweisungen bei

Antworte NUR mit einem JSON-Objekt:
{{"assignments": [{{"slot_id": "...", "employee_id": "..."}}]}}

Das Array muss ALLE Slots enthalten die besetzt werden sollen (auch unveraenderte).
Slots die nicht im Array sind gelten als unbesetzt."""

        raw = _call_llm(prompt, max_tokens=8192)
        result = _extract_json(raw)

        raw_assignments = result.get("assignments", [])
        if not raw_assignments:
            logger.warning("LLM refinement returned empty assignments, keeping loose plan")
            return loose_plan

        plan = _build_plan_from_llm_assignments(
            raw_assignments, snapshot, profile, loose_plan,
        )
        plan["mechanism"] = "loose"
        plan["soft_violations"] = soft_violations
        return plan

    except Exception:
        logger.exception("LLM refinement failed, returning loose plan unchanged")
        loose_plan["mechanism"] = "loose"
        return loose_plan


# ---------------------------------------------------------------------------
# Pure LLM allocation
# ---------------------------------------------------------------------------

def generate_plan_pure_llm(
    snapshot: dict[str, Any],
    profile: dict[str, Any],
    *,
    range_from: str,
    range_to: str,
    profile_name: str,
) -> dict[str, Any]:
    """Generate a complete shift plan using only the LLM.

    No algorithmic pre-assignment. The LLM sees raw input data and creates
    all assignments from scratch.
    """
    employees = snapshot.get("employees", [])
    open_slots = [
        s for s in snapshot.get("open_shifts", [])
        if range_from <= s.get("date", "") <= range_to
    ]
    assigned_shifts = snapshot.get("assigned_shifts", [])
    absences = snapshot.get("absences", [])

    rules_lookup = _normalize_rule_lookup(profile)

    employee_data = []
    for emp in employees:
        rule = _employee_rule(emp, rules_lookup)
        employee_data.append({
            "id": str(emp.get("ordio_employee_id")),
            "name": emp.get("full_name", ""),
            "role": emp.get("role", ""),
            "employment": emp.get("employment", ""),
            "hourly_wage": emp.get("hourly_wage"),
            "max_salary": emp.get("max_salary"),
            "skills": emp.get("skills", []),
            "target_weekly_hours": rule.get("target_weekly_hours"),
            "max_monthly_hours": rule.get("max_monthly_hours"),
            "max_weekly_hours": rule.get("max_weekly_hours"),
            "no_additional_shifts": rule.get("no_additional_shifts", False),
            "preferred_shift_types": rule.get("preferred_shift_types", []),
            "preferred_working_areas": rule.get("preferred_working_areas", []),
            "notes": rule.get("notes", ""),
        })

    slot_data = []
    for s in open_slots:
        slot_data.append({
            "slot_id": s.get("slot_id"),
            "date": s.get("date"),
            "start": s.get("start"),
            "end": s.get("end"),
            "shift_type": s.get("shift_type", ""),
            "working_area": s.get("working_area", ""),
            "applicants": [str(a) for a in (s.get("applicant_employee_ids") or [])],
        })

    existing_summary = []
    for s in assigned_shifts:
        existing_summary.append({
            "employee_id": str(s.get("ordio_employee_id")),
            "date": s.get("date"),
            "start": s.get("start"),
            "end": s.get("end"),
        })

    absence_summary = []
    for a in absences:
        absence_summary.append({
            "employee_id": str(a.get("ordio_employee_id")),
            "start_date": a.get("start_date"),
            "end_date": a.get("end_date"),
        })

    # Chunk by week if >50 slots
    if len(slot_data) > 50:
        all_assignments = _chunked_llm_allocation(
            slot_data, employee_data, existing_summary, absence_summary,
        )
    else:
        all_assignments = _single_llm_allocation(
            slot_data, employee_data, existing_summary, absence_summary,
        )

    # Build a stub loose_plan for _build_plan_from_llm_assignments
    stub_plan = {
        "plan_id": f"plan-{uuid4().hex[:12]}",
        "generated_at": now_utc_iso(),
        "snapshot_id": snapshot.get("snapshot_id"),
        "betrieb": snapshot.get("betrieb"),
        "range": {"from": range_from, "to": range_to},
        "profile": profile_name,
        "profile_description": profile.get("description", ""),
    }

    plan = _build_plan_from_llm_assignments(
        all_assignments, snapshot, profile, stub_plan,
    )
    plan["mechanism"] = "llm"
    return plan


def _single_llm_allocation(
    slots: list[dict],
    employees: list[dict],
    existing: list[dict],
    absences: list[dict],
) -> list[dict]:
    prompt = f"""Du bist ein Schichtplanungs-System. Erstelle einen vollstaendigen
Schichtplan aus den folgenden Rohdaten.

OFFENE SCHICHTEN:
{json.dumps(slots, ensure_ascii=False, indent=1)}

MITARBEITER:
{json.dumps(employees, ensure_ascii=False, indent=1)}

BESTEHENDE SCHICHTEN (bereits zugewiesen, nicht aendern):
{json.dumps(existing, ensure_ascii=False, indent=1)}

ABWESENHEITEN:
{json.dumps(absences, ensure_ascii=False, indent=1)}

HARTE CONSTRAINTS (MUESSEN eingehalten werden):
- Keine Ueberlappung am selben Tag
- Max 10h pro Tag
- Max 48h pro Woche (ArbZG)
- Min 11h Ruhezeit zwischen Schichten
- Max 5 aufeinanderfolgende Arbeitstage
- Keine Zuweisung bei Abwesenheit
- Gehaltslimit nicht ueberschreiten (hourly_wage * Monatsstunden <= max_salary)
- no_additional_shifts=true → nicht zuweisen

WEICHE CONSTRAINTS (wenn moeglich einhalten):
- Monatliche Stundenlimits
- Woechentliche Stundenlimits aus Profil
- Mitarbeiter-Praeferenzen (Schichttypen, Bereiche, Zeiten)

OPTIMIERUNGSZIELE:
1. Moeglichst alle Schichten besetzen
2. Fairness: Stunden gleichmaessig verteilen (nah am Target)
3. Bewerber bevorzugen (applicants)
4. Rollen/Skills matchen

Antworte NUR mit einem JSON-Objekt:
{{"assignments": [{{"slot_id": "...", "employee_id": "..."}}]}}"""

    raw = _call_llm(prompt, max_tokens=16384)
    result = _extract_json(raw)
    return result.get("assignments", [])


def _chunked_llm_allocation(
    slots: list[dict],
    employees: list[dict],
    existing: list[dict],
    absences: list[dict],
) -> list[dict]:
    """Split slots by week and allocate each chunk separately."""
    by_week: dict[str, list[dict]] = defaultdict(list)
    for s in slots:
        wk = week_key(s.get("date", ""))
        by_week[wk].append(s)

    all_assignments: list[dict] = []
    for wk in sorted(by_week.keys()):
        week_slots = by_week[wk]
        try:
            chunk = _single_llm_allocation(week_slots, employees, existing, absences)
            all_assignments.extend(chunk)
            # Add this week's assignments to "existing" for context in next week
            for a in chunk:
                slot = next((s for s in week_slots if s["slot_id"] == a.get("slot_id")), None)
                if slot:
                    existing.append({
                        "employee_id": a["employee_id"],
                        "date": slot["date"],
                        "start": slot["start"],
                        "end": slot["end"],
                    })
        except Exception:
            logger.exception("LLM chunk allocation failed for week %s", wk)

    return all_assignments


# ---------------------------------------------------------------------------
# Shared: convert LLM output to full plan dict
# ---------------------------------------------------------------------------

def _build_plan_from_llm_assignments(
    raw_assignments: list[dict[str, str]],
    snapshot: dict[str, Any],
    profile: dict[str, Any],
    base_plan: dict[str, Any],
) -> dict[str, Any]:
    """Convert [{slot_id, employee_id}] into a full plan dict.

    Recomputes scores via _score_candidate() for consistent scoring data.
    Builds fairness, evaluation_matrix, metrics.
    """
    employees = snapshot.get("employees", [])
    employee_by_id = {
        str(e.get("ordio_employee_id")): e
        for e in employees if e.get("ordio_employee_id")
    }
    rules_lookup = _normalize_rule_lookup(profile)
    policy = profile.get("policy", {}) or {}

    range_from = base_plan.get("range", {}).get("from", "")
    range_to = base_plan.get("range", {}).get("to", "")

    open_slots = [
        {
            **slot,
            "hours": float(slot.get("hours") or calc_shift_hours(
                slot.get("start", ""), slot.get("end", ""))),
        }
        for slot in snapshot.get("open_shifts", [])
        if range_from <= slot.get("date", "") <= range_to
    ]
    slot_by_id = {s.get("slot_id", ""): s for s in open_slots}

    assigned_shifts = snapshot.get("assigned_shifts", [])
    fixed_patterns = _derive_fixed_patterns(assigned_shifts)

    abs_by_emp: dict[str, list[dict[str, Any]]] = {}
    for ab in snapshot.get("absences", []):
        emp = str(ab.get("ordio_employee_id") or "")
        if emp:
            abs_by_emp.setdefault(emp, []).append(ab)

    existing_by_emp: dict[str, list[dict[str, Any]]] = {}
    for emp_id in employee_by_id:
        existing_by_emp[emp_id] = _collect_existing_shifts(snapshot, emp_id)

    # Build assignments from LLM output
    assigned_slot_ids = set()
    run_by_emp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    run_hours_by_emp_month: dict[tuple[str, str], float] = defaultdict(float)
    assignments: list[dict[str, Any]] = []

    for raw in raw_assignments:
        slot_id = raw.get("slot_id", "")
        emp_id = str(raw.get("employee_id", ""))
        slot = slot_by_id.get(slot_id)
        emp = employee_by_id.get(emp_id)

        if not slot or not emp:
            logger.debug("Skipping invalid LLM assignment: slot=%s emp=%s", slot_id, emp_id)
            continue
        if slot_id in assigned_slot_ids:
            logger.debug("Skipping duplicate LLM assignment for slot %s", slot_id)
            continue

        assigned_slot_ids.add(slot_id)
        slot_hours = float(slot.get("hours", 0))
        emp_name = emp.get("full_name") or emp_id

        rule = _employee_rule(emp, rules_lookup)
        prefs = _parse_preferences(str(rule.get("notes") or ""))
        applicants = {str(v) for v in (slot.get("applicant_employee_ids") or [])}

        # Score this assignment for consistent data
        eval_row = _score_candidate(
            employee=emp,
            slot=slot,
            rule=rule,
            prefs=prefs,
            is_applicant=emp_id in applicants,
            existing_shifts=existing_by_emp.get(emp_id, []),
            run_shifts=run_by_emp.get(emp_id, []),
            absences=abs_by_emp.get(emp_id, []),
            fixed_patterns=fixed_patterns,
            policy=policy,
            run_extra_month_hours=run_hours_by_emp_month[(emp_id, month_key(slot["date"]))],
        )

        has_applicants = bool(applicants)
        assignment_kind = "applicant"
        if not eval_row.is_applicant:
            assignment_kind = (
                "recommendation_without_applicant"
                if not has_applicants
                else "recommendation_despite_applicants"
            )

        assignments.append({
            "assignment_id": f"{slot_id}::{emp_id}",
            "slot_id": slot_id,
            "ordio_shift_id": slot.get("ordio_shift_id"),
            "date": slot.get("date"),
            "start": slot.get("start"),
            "end": slot.get("end"),
            "hours": round(slot_hours, 2),
            "shift_type": slot.get("shift_type"),
            "working_area": slot.get("working_area"),
            "note": slot.get("note", ""),
            "ordio_employee_id": emp_id,
            "employee_name": emp_name,
            "score": eval_row.score,
            "is_applicant": eval_row.is_applicant,
            "assignment_kind": assignment_kind,
            "reasons": eval_row.reasons,
            "blocked_reasons": eval_row.blocked_reasons,
            "score_detail": eval_row.score_detail,
            "week_shifts": eval_row.week_shifts,
            "existing_month_hours": eval_row.hours_existing_month,
            "run_month_hours_before": eval_row.hours_run_month,
            "target_hours": eval_row.target_hours,
            "projected_salary": eval_row.projected_salary,
            "alternatives": [],
        })

        # Track run state
        run_by_emp[emp_id].append({
            "date": slot["date"],
            "start": slot["start"],
            "end": slot["end"],
            "hours": slot_hours,
        })
        run_hours_by_emp_month[(emp_id, month_key(slot["date"]))] += slot_hours

    # Build unassigned list
    unassigned = []
    for slot in open_slots:
        sid = slot.get("slot_id", "")
        if sid not in assigned_slot_ids:
            unassigned.append({
                "slot_id": sid,
                "ordio_shift_id": slot.get("ordio_shift_id"),
                "date": slot.get("date"),
                "start": slot.get("start"),
                "end": slot.get("end"),
                "shift_type": slot.get("shift_type"),
                "working_area": slot.get("working_area"),
                "reason": "not_assigned_by_llm",
                "top_candidates": [],
            })

    total_slots = len(assignments) + len(unassigned)
    fill_rate = round((len(assignments) / total_slots) * 100, 1) if total_slots else 0.0
    fairness = fairness_overview(assignments)

    plan = {
        "plan_id": base_plan.get("plan_id", f"plan-{uuid4().hex[:12]}"),
        "generated_at": base_plan.get("generated_at", now_utc_iso()),
        "snapshot_id": base_plan.get("snapshot_id", snapshot.get("snapshot_id")),
        "betrieb": base_plan.get("betrieb", snapshot.get("betrieb")),
        "range": base_plan.get("range", {"from": range_from, "to": range_to}),
        "profile": base_plan.get("profile", ""),
        "profile_description": base_plan.get("profile_description", ""),
        "assignments": assignments,
        "unassigned": unassigned,
        "metrics": {
            "assigned_slots": len(assignments),
            "unassigned_slots": len(unassigned),
            "total_slots": total_slots,
            "fill_rate": fill_rate,
            "assignment_kind_counts": dict(Counter(
                a["assignment_kind"] for a in assignments
            )),
        },
        "fairness": fairness,
        "explanation": {
            "constraint_policy": policy,
            "notes": ["Plan generated/refined by LLM. Scores recomputed for consistency."],
        },
        "evaluation_matrix": {},
    }
    return plan
