"""Plan comparison -- side-by-side diff of two allocation plans."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any


def _gini(values: list[float]) -> float:
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumulative = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    return (2 * cumulative) / (n * total) - (n + 1) / n


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """Extract aggregate metrics from a plan dict."""
    assignments = plan.get("assignments", [])
    unassigned = plan.get("unassigned", [])
    metrics = plan.get("metrics", {})
    total = metrics.get("total_slots", len(assignments) + len(unassigned))
    fill_rate = metrics.get(
        "fill_rate",
        round(len(assignments) / max(1, total) * 100, 1),
    )

    scores = [float(a.get("score", 0)) for a in assignments]
    mean_score = round(statistics.mean(scores), 2) if scores else 0.0

    emp_hours: dict[str, float] = defaultdict(float)
    for a in assignments:
        name = a.get("employee_name") or a.get("ordio_employee_id", "")
        emp_hours[name] += float(a.get("hours", 0))
    hours_list = list(emp_hours.values())
    gini = _gini(hours_list)
    kind_counts = Counter(a.get("assignment_kind", "unknown") for a in assignments)

    return {
        "plan_id": plan.get("plan_id"),
        "profile": plan.get("profile"),
        "mechanism": plan.get("mechanism"),
        "total_slots": total,
        "assigned": len(assignments),
        "unassigned": len(unassigned),
        "fill_rate": fill_rate,
        "mean_score": mean_score,
        "gini": round(gini, 4),
        "employees_used": len(emp_hours),
        "assignment_kinds": dict(kind_counts.most_common()),
        "_emp_hours": dict(sorted(emp_hours.items(), key=lambda kv: -kv[1])),
    }


def _slot_divergence(plan_a: dict[str, Any], plan_b: dict[str, Any]) -> dict[str, Any]:
    """Slot-level agreement / divergence between two plans."""
    a_by_slot = {a["slot_id"]: a for a in plan_a.get("assignments", []) if a.get("slot_id")}
    b_by_slot = {a["slot_id"]: a for a in plan_b.get("assignments", []) if a.get("slot_id")}

    a_unassigned = {u["slot_id"] for u in plan_a.get("unassigned", []) if u.get("slot_id")}
    b_unassigned = {u["slot_id"] for u in plan_b.get("unassigned", []) if u.get("slot_id")}

    all_slots = set(a_by_slot) | set(b_by_slot) | a_unassigned | b_unassigned

    same_employee = 0
    different_employee = 0
    a_only = 0
    b_only = 0
    both_unassigned = 0
    divergent: list[dict[str, Any]] = []

    for slot_id in sorted(all_slots):
        a_asgn = a_by_slot.get(slot_id)
        b_asgn = b_by_slot.get(slot_id)

        if a_asgn and b_asgn:
            a_emp = a_asgn.get("ordio_employee_id", "")
            b_emp = b_asgn.get("ordio_employee_id", "")
            if a_emp == b_emp:
                same_employee += 1
            else:
                different_employee += 1
                divergent.append({
                    "slot_id": slot_id,
                    "date": a_asgn.get("date"),
                    "start": a_asgn.get("start"),
                    "end": a_asgn.get("end"),
                    "shift_type": a_asgn.get("shift_type"),
                    "plan_a_employee": a_asgn.get("employee_name"),
                    "plan_a_score": a_asgn.get("score"),
                    "plan_b_employee": b_asgn.get("employee_name"),
                    "plan_b_score": b_asgn.get("score"),
                    "score_delta": round(
                        float(a_asgn.get("score", 0)) - float(b_asgn.get("score", 0)), 2
                    ),
                })
        elif a_asgn and not b_asgn:
            a_only += 1
        elif b_asgn and not a_asgn:
            b_only += 1
        else:
            both_unassigned += 1

    divergent.sort(key=lambda d: abs(d.get("score_delta", 0)), reverse=True)

    total_comparable = same_employee + different_employee
    agreement_rate = round(same_employee / total_comparable * 100, 1) if total_comparable else 0.0

    return {
        "total_slots": len(all_slots),
        "same_employee": same_employee,
        "different_employee": different_employee,
        "a_only_assigned": a_only,
        "b_only_assigned": b_only,
        "both_unassigned": both_unassigned,
        "agreement_rate": agreement_rate,
        "top_divergent_slots": divergent[:10],
    }


def compare_plans_impl(plan_a: dict[str, Any], plan_b: dict[str, Any]) -> dict[str, Any]:
    """Compare two plans: aggregate metrics and slot-level divergence."""
    summary_a = _plan_summary(plan_a)
    summary_b = _plan_summary(plan_b)
    slot_diff = _slot_divergence(plan_a, plan_b)

    # Employee hour comparison
    emp_a = summary_a.pop("_emp_hours", {})
    emp_b = summary_b.pop("_emp_hours", {})
    all_emps = set(emp_a) | set(emp_b)
    emp_comparison = []
    for name in sorted(all_emps):
        a_h = round(emp_a.get(name, 0), 2)
        b_h = round(emp_b.get(name, 0), 2)
        emp_comparison.append({
            "employee": name,
            "plan_a_hours": a_h,
            "plan_b_hours": b_h,
            "delta": round(a_h - b_h, 2),
        })
    emp_comparison.sort(key=lambda e: abs(e["delta"]), reverse=True)

    return {
        "plan_a": summary_a,
        "plan_b": summary_b,
        "deltas": {
            "fill_rate": round(summary_a["fill_rate"] - summary_b["fill_rate"], 1),
            "mean_score": round(summary_a["mean_score"] - summary_b["mean_score"], 2),
            "gini": round(summary_a["gini"] - summary_b["gini"], 4),
            "assigned": summary_a["assigned"] - summary_b["assigned"],
        },
        "slot_divergence": slot_diff,
        "employee_comparison": emp_comparison[:15],
    }
