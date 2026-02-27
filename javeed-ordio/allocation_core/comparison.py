"""Build comparison data from multiple mechanism metrics.

Merges per-mechanism metrics.json dicts into a unified comparison structure
used by the combined report.html and comparison XLSX.
"""

from __future__ import annotations

from typing import Any


def build_comparison(mechanism_metrics: dict[str, dict]) -> dict:
    """Build comparison from {"algo": metrics, "loose": metrics, "llm": metrics}.

    Works with 2 or 3 mechanisms.
    """
    mechanisms = list(mechanism_metrics.keys())

    kpis = {}
    for mech, m in mechanism_metrics.items():
        kpis[mech] = {
            "fill_rate": m.get("fill_rate", {}).get("pct", 0),
            "gini": m.get("fairness", {}).get("gini", 0),
            "avg_score": m.get("scoring", {}).get("avg", 0),
            "unassigned": m.get("fill_rate", {}).get("unassigned", 0),
            "avg_abs_delta": m.get("fairness", {}).get("avg_abs_delta", 0),
            "total_slots": m.get("fill_rate", {}).get("total_slots", 0),
            "assigned": m.get("fill_rate", {}).get("assigned", 0),
        }

    return {
        "mechanisms": mechanisms,
        "kpis": kpis,
        "per_employee": _merge_per_employee(mechanism_metrics),
        "per_slot": _merge_per_slot(mechanism_metrics),
        "all_metrics": mechanism_metrics,
    }


def _merge_per_employee(mechanism_metrics: dict[str, dict]) -> list[dict[str, Any]]:
    """Merge per-employee fairness data across mechanisms."""
    all_employees: dict[str, dict[str, Any]] = {}
    mechanisms = list(mechanism_metrics.keys())

    for mech, m in mechanism_metrics.items():
        for emp in m.get("fairness", {}).get("per_employee", []):
            name = emp.get("name", "")
            if name not in all_employees:
                all_employees[name] = {"name": name}
            all_employees[name][f"{mech}_hours"] = emp.get("assigned_hours", 0)
            all_employees[name][f"{mech}_slots"] = emp.get("assigned_slots", 0)
            all_employees[name][f"{mech}_delta"] = emp.get("delta")
            all_employees[name]["target_hours"] = emp.get("target_hours")

    result = sorted(all_employees.values(), key=lambda x: -max(
        x.get(f"{m}_hours", 0) for m in mechanisms
    ))
    return result


def _merge_per_slot(mechanism_metrics: dict[str, dict]) -> list[dict[str, Any]]:
    """Merge per-slot assignment data across mechanisms.

    Uses slot_assignments (preferred) or per_employee_schedule (fallback) to
    build a slot-level view of who each mechanism assigned.
    Classifies agreement: all_agree, majority, all_differ.
    """
    mechanisms = list(mechanism_metrics.keys())

    # Check if slot_assignments is available (richer data)
    has_slot_assignments = any(
        m.get("slot_assignments") for m in mechanism_metrics.values()
    )

    if has_slot_assignments:
        return _merge_per_slot_rich(mechanism_metrics, mechanisms)

    # Fallback: reconstruct from per_employee_schedule shift_dates
    return _merge_per_slot_dates(mechanism_metrics, mechanisms)


def _merge_per_slot_rich(
    mechanism_metrics: dict[str, dict], mechanisms: list[str],
) -> list[dict[str, Any]]:
    """Merge using slot_assignments for full slot-level detail."""
    # Collect slot metadata from any mechanism
    slot_meta: dict[str, dict[str, Any]] = {}
    mech_slot_map: dict[str, dict[str, str]] = {m: {} for m in mechanisms}

    for mech, m in mechanism_metrics.items():
        for slot in m.get("slot_assignments", []):
            sid = slot.get("slot_id", "")
            if not sid:
                continue
            if sid not in slot_meta:
                slot_meta[sid] = {
                    "slot_id": sid,
                    "date": slot.get("date", ""),
                    "start": slot.get("start", ""),
                    "end": slot.get("end", ""),
                    "shift_type": slot.get("shift_type", ""),
                    "working_area": slot.get("working_area", ""),
                }
            mech_slot_map[mech][sid] = slot.get("employee_name") or ""

    result = []
    for sid, meta in sorted(
        slot_meta.items(), key=lambda x: (x[1]["date"], x[1]["start"]),
    ):
        row: dict[str, Any] = {**meta}
        employees_assigned: list[str] = []
        for mech in mechanisms:
            emp = mech_slot_map[mech].get(sid, "")
            row[f"{mech}_employee"] = emp
            if emp:
                employees_assigned.append(emp)

        row["agreement"] = _classify_agreement(employees_assigned, len(mechanisms))
        result.append(row)

    return result


def _merge_per_slot_dates(
    mechanism_metrics: dict[str, dict], mechanisms: list[str],
) -> list[dict[str, Any]]:
    """Fallback: merge using per_employee_schedule shift_dates (date-level only)."""
    mech_assignments: dict[str, dict[str, str]] = {}
    for mech, m in mechanism_metrics.items():
        date_to_emp: dict[str, str] = {}
        for emp in m.get("per_employee_schedule", []):
            name = emp.get("name", "")
            for d in emp.get("shift_dates", []):
                date_to_emp[d] = name
        mech_assignments[mech] = date_to_emp

    all_dates: set[str] = set()
    for date_map in mech_assignments.values():
        all_dates.update(date_map.keys())

    result = []
    for d in sorted(all_dates):
        row: dict[str, Any] = {"date": d}
        employees_assigned: list[str] = []
        for mech in mechanisms:
            emp = mech_assignments.get(mech, {}).get(d, "")
            row[f"{mech}_employee"] = emp
            if emp:
                employees_assigned.append(emp)

        row["agreement"] = _classify_agreement(employees_assigned, len(mechanisms))
        result.append(row)

    return result


def _classify_agreement(employees_assigned: list[str], num_mechanisms: int) -> str:
    """Classify agreement level among mechanism assignments."""
    unique = set(employees_assigned)
    if len(unique) == 1 and len(employees_assigned) == num_mechanisms:
        return "all_agree"
    if len(unique) <= 2 and len(employees_assigned) >= 2:
        return "majority"
    if len(unique) == 0:
        return "all_unassigned"
    return "all_differ"
