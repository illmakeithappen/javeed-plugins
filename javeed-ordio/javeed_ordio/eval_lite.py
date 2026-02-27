"""Lightweight plan evaluation -- self-contained in the plugin.

Computes key quality metrics from a plan dict without depending on
the evals package.  All functions are pure dict-in / dict-out.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gini(values: list[float]) -> float:
    """Gini coefficient for a list of non-negative values."""
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumulative = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    return (2 * cumulative) / (n * total) - (n + 1) / n


def _stats(values: list[float]) -> dict[str, float]:
    """Basic distribution statistics."""
    if not values:
        return {"mean": 0, "median": 0, "std": 0, "min": 0, "max": 0}
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "std": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


# ---------------------------------------------------------------------------
# Metric functions
# ---------------------------------------------------------------------------

_COMP_KEYS = ("rest", "fairness", "role", "skill", "fixed", "preference", "applicant", "salary")


def _scoring_distribution(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Overall and per-component scoring distribution."""
    scores = [float(a.get("score", 0)) for a in assignments]
    overall = _stats(scores)

    per_component: dict[str, dict[str, float]] = {}
    for key in _COMP_KEYS:
        vals = [float(a.get("score_detail", {}).get(key, 0)) for a in assignments]
        if any(v != 0 for v in vals):
            per_component[key] = _stats(vals)

    return {"overall": overall, "per_component": per_component}


def _applicant_dominance(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """How much the applicant bonus drives final scores."""
    total = len(assignments)
    if not total:
        return {"applicant_driven_pct": 0, "avg_applicant_share": 0}

    applicant_driven = 0
    shares: list[float] = []
    for a in assignments:
        detail = a.get("score_detail", {})
        applicant_val = float(detail.get("applicant", 0))
        total_score = float(a.get("score", 0))
        if total_score > 0 and applicant_val > 0:
            share = applicant_val / total_score
            shares.append(share)
            if share > 0.4:
                applicant_driven += 1

    return {
        "applicant_driven_count": applicant_driven,
        "applicant_driven_pct": round(applicant_driven / total * 100, 1),
        "avg_applicant_share": round(statistics.mean(shares), 4) if shares else 0.0,
        "total_with_applicant_bonus": len(shares),
    }


def _scoring_consistency(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Variance of stable vs dynamic score components for multi-slot employees."""
    emp_details: dict[str, list[dict[str, float]]] = defaultdict(list)
    for a in assignments:
        emp = a.get("ordio_employee_id") or a.get("employee_name")
        detail = a.get("score_detail")
        if emp and detail:
            emp_details[emp].append(detail)

    multi = {emp: ds for emp, ds in emp_details.items() if len(ds) >= 2}
    if not multi:
        return {"employees_with_multiple": 0}

    stable = ["role", "skill"]
    dynamic = ["rest", "fairness"]

    stable_var: dict[str, list[float]] = {c: [] for c in stable}
    dynamic_var: dict[str, list[float]] = {c: [] for c in dynamic}

    for details in multi.values():
        for comp in stable:
            vals = [d.get(comp, 0) for d in details]
            if len(vals) > 1:
                stable_var[comp].append(statistics.variance(vals))
        for comp in dynamic:
            vals = [d.get(comp, 0) for d in details]
            if len(vals) > 1:
                dynamic_var[comp].append(statistics.variance(vals))

    return {
        "employees_with_multiple": len(multi),
        "stable_components": {
            c: {"mean_variance": round(statistics.mean(vs), 4) if vs else 0.0}
            for c, vs in stable_var.items()
        },
        "dynamic_components": {
            c: {"mean_variance": round(statistics.mean(vs), 4) if vs else 0.0}
            for c, vs in dynamic_var.items()
        },
    }


def _unassigned_analysis(unassigned: list[dict[str, Any]]) -> dict[str, Any]:
    """Unassigned slots grouped by reason, shift type, date, and blocked reasons."""
    if not unassigned:
        return {"count": 0}

    reason_dist = Counter(u.get("reason", "unknown") for u in unassigned)
    by_type = Counter(u.get("shift_type", "unknown") for u in unassigned)
    by_date = Counter(u.get("date", "unknown") for u in unassigned)

    blocked_reasons: Counter[str] = Counter()
    for u in unassigned:
        for cand in u.get("top_candidates", []):
            for r in cand.get("blocked_reasons", []):
                blocked_reasons[r] += 1

    return {
        "count": len(unassigned),
        "reason_distribution": dict(reason_dist.most_common()),
        "by_shift_type": dict(by_type.most_common()),
        "by_date": dict(by_date.most_common()),
        "top_blocked_reasons": dict(blocked_reasons.most_common(10)),
    }


def _coverage_heatmap(
    assignments: list[dict[str, Any]],
    unassigned: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Date x shift_type coverage grid."""
    grid: dict[tuple[str, str], str] = {}
    for a in assignments:
        key = (a.get("date", ""), a.get("shift_type", ""))
        grid[key] = "filled"
    for u in unassigned:
        key = (u.get("date", ""), u.get("shift_type", ""))
        if key not in grid:
            grid[key] = "unfilled"
    return [
        {"date": dt, "shift_type": st, "status": status}
        for (dt, st), status in sorted(grid.items())
    ]


def _fairness(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Gini, std_dev, per-employee hours vs target."""
    emp_hours: dict[str, float] = defaultdict(float)
    emp_target: dict[str, float | None] = {}
    for a in assignments:
        name = a.get("employee_name") or a.get("ordio_employee_id", "")
        emp_hours[name] += float(a.get("hours", 0))
        if a.get("target_hours") is not None:
            emp_target[name] = float(a["target_hours"])

    hours_list = list(emp_hours.values())
    gini = _gini(hours_list)
    std_dev = round(statistics.stdev(hours_list), 2) if len(hours_list) > 1 else 0.0
    mean_hours = round(statistics.mean(hours_list), 2) if hours_list else 0.0

    per_employee: list[dict[str, Any]] = []
    for name, hours in sorted(emp_hours.items(), key=lambda kv: -kv[1]):
        entry: dict[str, Any] = {
            "employee": name,
            "assigned_hours": round(hours, 2),
        }
        if name in emp_target and emp_target[name] is not None:
            entry["target_hours"] = round(emp_target[name], 2)
            entry["delta"] = round(hours - emp_target[name], 2)
        per_employee.append(entry)

    return {
        "gini": round(gini, 4),
        "std_dev": std_dev,
        "mean_hours": mean_hours,
        "employee_count": len(emp_hours),
        "per_employee": per_employee,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_plan_lite(plan: dict[str, Any]) -> dict[str, Any]:
    """Compute quality metrics for a plan dict.

    Returns a flat result dict suitable for MCP tool output.
    """
    assignments = plan.get("assignments", [])
    unassigned = plan.get("unassigned", [])
    plan_metrics = plan.get("metrics", {})

    total = plan_metrics.get("total_slots", len(assignments) + len(unassigned))
    assigned = plan_metrics.get("assigned_slots", len(assignments))
    fill_rate = plan_metrics.get(
        "fill_rate",
        round(assigned / max(1, total) * 100, 1),
    )

    kind_counts = Counter(a.get("assignment_kind", "unknown") for a in assignments)

    return {
        "meta": {
            "plan_id": plan.get("plan_id"),
            "betrieb": plan.get("betrieb"),
            "range": plan.get("range"),
            "profile": plan.get("profile"),
            "generated_at": plan.get("generated_at"),
            "snapshot_id": plan.get("snapshot_id"),
        },
        "fill_rate": {
            "total_slots": total,
            "assigned": assigned,
            "unassigned": plan_metrics.get("unassigned_slots", len(unassigned)),
            "fill_rate_pct": fill_rate,
        },
        "assignment_kinds": dict(kind_counts.most_common()),
        "scoring_distribution": _scoring_distribution(assignments),
        "applicant_dominance": _applicant_dominance(assignments),
        "scoring_consistency": _scoring_consistency(assignments),
        "unassigned_analysis": _unassigned_analysis(unassigned),
        "coverage_heatmap": _coverage_heatmap(assignments, unassigned),
        "fairness": _fairness(assignments),
    }
