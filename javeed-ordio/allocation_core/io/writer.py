"""Write enriched metrics.json from generate_plan() output.

All row-level data (assignments, fairness, eval matrix) lives in plan.xlsx
only.  metrics.json contains aggregated KPIs sufficient for report.html and
monatsuebersicht.html to render without any CSV dependencies.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from .schemas import SCORE_COMPONENTS

# ---------------------------------------------------------------------------
# Lightweight helpers
# ---------------------------------------------------------------------------

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _gini(values: list[float]) -> float:
    """Gini coefficient: 0 = perfect equality, 1 = total concentration."""
    if not values or all(v == 0 for v in values):
        return 0.0
    s = sorted(values)
    n = len(s)
    total = sum(s)
    if total == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(s))
    return round((2 * cum) / (n * total) - (n + 1) / n, 4)


def _shift_category(start_str: str) -> str:
    """Categorise a shift as frueh or spaet based on start time."""
    try:
        sh = int(start_str.split(":")[0])
    except (ValueError, IndexError):
        return "spaet"
    return "frueh" if sh < 14 else "spaet"


def _hours(start: str, end: str) -> float:
    """Compute hours between HH:MM time strings (handles overnight)."""
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    mins = eh * 60 + em - sh * 60 - sm
    if mins < 0:
        mins += 24 * 60
    return mins / 60


def _assess(
    fill: dict,
    fairness: dict,
    workforce: dict,
    unassigned: list[dict],
) -> list[dict]:
    """Generate traffic-light assessment bullets."""
    bullets: list[dict] = []
    pct = fill.get("pct", 0)

    # Fill rate
    if pct >= 95:
        bullets.append({"level": "green", "text": "Fill rate excellent"})
    elif pct >= 85:
        bullets.append({"level": "green", "text": "Fill rate good"})
    elif pct >= 70:
        bullets.append({"level": "yellow", "text": "Fill rate moderate -- constraints may be tight"})
    else:
        bullets.append({"level": "red", "text": "Fill rate low -- constraints blocking candidates"})

    # Concentration
    conc = workforce.get("concentration_pct", 0)
    top_name = workforce.get("top_employee", "")
    top_hours = workforce.get("top_hours", 0)
    if conc > 30 and top_name:
        bullets.append({
            "level": "yellow",
            "text": f"Concentration: {top_name} has {top_hours:.0f}h ({conc:.0f}%)",
        })

    # Fairness
    avg_delta = fairness.get("avg_abs_delta", 0)
    if avg_delta > 15:
        bullets.append({"level": "red", "text": f"Fairness poor -- avg {avg_delta:.0f}h off target"})
    elif avg_delta > 5:
        bullets.append({"level": "yellow", "text": f"Fairness moderate -- avg {avg_delta:.0f}h off target"})
    elif fairness.get("per_employee"):
        bullets.append({"level": "green", "text": f"Fairness good -- avg {avg_delta:.0f}h off target"})

    # Sunday gap
    by_wd = fill.get("by_weekday", {})
    sun_open = by_wd.get("Sun", {}).get("open", 0) if isinstance(by_wd.get("Sun"), dict) else 0
    if sun_open >= 3:
        bullets.append({"level": "yellow", "text": f"Sunday gap: {sun_open} unfilled slots"})

    return bullets


# ---------------------------------------------------------------------------
# Build enriched metrics dict
# ---------------------------------------------------------------------------

def _build_enriched_metrics(
    plan: dict,
    golden_comparison: dict | None = None,
) -> dict:
    """Build the comprehensive metrics.json structure from a plan dict.

    Contains all aggregate KPIs needed by report.html and
    monatsuebersicht.html -- no raw row-level data.
    """
    m = plan.get("metrics", {})
    kind_counts = m.get("assignment_kind_counts", {})
    assignments = plan.get("assignments", [])
    unassigned = plan.get("unassigned", [])
    fairness_list = plan.get("fairness", [])

    total_slots = m.get("total_slots", 0)
    assigned_count = m.get("assigned_slots", 0)
    unassigned_count = m.get("unassigned_slots", 0)
    fill_pct = m.get("fill_rate", 0.0)

    # -- Fill rate breakdown --------------------------------------------------
    by_shift_type: dict[str, dict[str, int]] = {}
    by_weekday: dict[str, dict[str, int]] = {}

    for a in assignments:
        cat = _shift_category(a.get("start", ""))
        st = a.get("shift_type", "")
        key = "spaet" if st == "normal" else (st if st in ("frueh", "spaet") else cat)
        by_shift_type.setdefault(key, {"assigned": 0, "open": 0})
        by_shift_type[key]["assigned"] += 1

        try:
            wd = _WEEKDAYS[date.fromisoformat(a["date"]).weekday()]
        except (ValueError, KeyError):
            wd = "?"
        by_weekday.setdefault(wd, {"assigned": 0, "open": 0})
        by_weekday[wd]["assigned"] += 1

    for u in unassigned:
        cat = _shift_category(u.get("start", ""))
        st = u.get("shift_type", "")
        key = "spaet" if st == "normal" else (st if st in ("frueh", "spaet") else cat)
        by_shift_type.setdefault(key, {"assigned": 0, "open": 0})
        by_shift_type[key]["open"] += 1

        try:
            wd = _WEEKDAYS[date.fromisoformat(u["date"]).weekday()]
        except (ValueError, KeyError):
            wd = "?"
        by_weekday.setdefault(wd, {"assigned": 0, "open": 0})
        by_weekday[wd]["open"] += 1

    # Ensure both categories exist
    by_shift_type.setdefault("frueh", {"assigned": 0, "open": 0})
    by_shift_type.setdefault("spaet", {"assigned": 0, "open": 0})

    fill_rate = {
        "total_slots": total_slots,
        "assigned": assigned_count,
        "unassigned": unassigned_count,
        "pct": fill_pct,
        "by_applicant": kind_counts.get("applicant", 0),
        "by_recommendation": (
            kind_counts.get("recommendation_without_applicant", 0)
            + kind_counts.get("recommendation_despite_applicants", 0)
        ),
        "by_shift_type": by_shift_type,
        "by_weekday": by_weekday,
    }

    # -- Fairness -------------------------------------------------------------
    per_employee_fair = []
    all_hours = []
    deltas = []
    for f in fairness_list:
        hours = f.get("assigned_hours", 0)
        target = f.get("target_hours")
        delta = f.get("delta_to_target")
        per_employee_fair.append({
            "name": f["employee_name"],
            "assigned_hours": hours,
            "assigned_slots": f.get("assigned_slots", 0),
            "target_hours": target,
            "delta": delta,
        })
        all_hours.append(hours)
        if delta is not None:
            deltas.append(abs(delta))

    avg_abs_delta = round(sum(deltas) / len(deltas), 1) if deltas else 0
    max_abs_delta = round(max(deltas), 1) if deltas else 0
    std_dev = 0.0
    if all_hours:
        mean_h = sum(all_hours) / len(all_hours)
        std_dev = round((sum((h - mean_h) ** 2 for h in all_hours) / len(all_hours)) ** 0.5, 2)

    fairness = {
        "avg_abs_delta": avg_abs_delta,
        "max_abs_delta": max_abs_delta,
        "gini": _gini(all_hours),
        "std_dev": std_dev,
        "per_employee": per_employee_fair,
    }

    # -- Scoring --------------------------------------------------------------
    scores = [a.get("score", 0) for a in assignments if a.get("score") is not None]
    component_sums: dict[str, list[float]] = {c: [] for c in SCORE_COMPONENTS}
    for a in assignments:
        sd = a.get("score_detail", {})
        for c in SCORE_COMPONENTS:
            val = sd.get(c)
            if val is not None:
                component_sums[c].append(val)

    per_component_avg = {}
    for c, vals in component_sums.items():
        per_component_avg[c] = round(sum(vals) / len(vals), 1) if vals else 0

    scoring = {
        "avg": round(sum(scores) / len(scores), 1) if scores else 0,
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "per_component_avg": per_component_avg,
    }

    # -- Constraints ----------------------------------------------------------
    unassigned_reasons = Counter(u.get("reason", "unknown") for u in unassigned)

    # Block rate + top reasons from eval_matrix if available
    eval_matrix = plan.get("evaluation_matrix", {})
    block_rate = None
    top_block_reasons: list[list] = []
    if eval_matrix:
        total_evals = 0
        blocked_count = 0
        reason_counter: Counter = Counter()
        for evals in eval_matrix.values():
            for ev in evals:
                total_evals += 1
                if ev.get("blocked"):
                    blocked_count += 1
                    for r in ev.get("blocked_reasons", []):
                        reason_counter[r] += 1
        block_rate = round(blocked_count / total_evals * 100, 1) if total_evals else 0
        top_block_reasons = [[r, c] for r, c in reason_counter.most_common(10)]

    constraints = {
        "unassigned_by_reason": dict(unassigned_reasons),
        "block_rate": block_rate,
        "top_block_reasons": top_block_reasons,
    }

    # -- Workforce ------------------------------------------------------------
    emp_hours: dict[str, float] = {}
    for f in fairness_list:
        emp_hours[f["employee_name"]] = f.get("assigned_hours", 0)

    total_hours = sum(emp_hours.values())
    active = sum(1 for h in emp_hours.values() if h > 0)
    idle = len(emp_hours) - active
    top_employee = max(emp_hours, key=emp_hours.get, default="") if emp_hours else ""
    top_hours_val = emp_hours.get(top_employee, 0)
    concentration = round(top_hours_val / total_hours * 100, 1) if total_hours else 0

    workforce = {
        "total_employees": len(emp_hours),
        "active": active,
        "idle": idle,
        "total_hours": round(total_hours, 1),
        "avg_score": scoring["avg"],
        "top_employee": top_employee,
        "top_hours": round(top_hours_val, 1),
        "concentration_pct": concentration,
    }

    # -- Assessment -----------------------------------------------------------
    assessment = _assess(fill_rate, fairness, workforce, unassigned)

    # -- open_by_day (for monatsuebersicht) -----------------------------------
    open_by_day_dict: dict[str, dict] = {}
    for u in unassigned:
        d = u.get("date", "")
        if d not in open_by_day_dict:
            open_by_day_dict[d] = {"date": d, "open": 0, "applicants": 0}
        open_by_day_dict[d]["open"] += 1
    open_by_day = sorted(open_by_day_dict.values(), key=lambda x: x["date"])

    # -- per_employee_schedule (for monatsuebersicht) -------------------------
    schedule: dict[str, dict] = {}
    for a in assignments:
        name = a.get("employee_name", "")
        if name not in schedule:
            schedule[name] = {"name": name, "algo_hours": 0, "algo_slots": 0, "shift_dates": []}
        schedule[name]["algo_hours"] += _hours(a["start"], a["end"])
        schedule[name]["algo_slots"] += 1
        schedule[name]["shift_dates"].append(a["date"])

    per_employee_schedule = []
    for s in schedule.values():
        s["algo_hours"] = round(s["algo_hours"], 1)
        s["shift_dates"] = sorted(set(s["shift_dates"]))
        per_employee_schedule.append(s)
    per_employee_schedule.sort(key=lambda x: -x["algo_hours"])

    # -- slot_assignments (for review view) ------------------------------------
    slot_assignments = []
    for a in assignments:
        slot_assignments.append({
            "slot_id": a.get("slot_id", ""),
            "date": a.get("date", ""),
            "start": a.get("start", ""),
            "end": a.get("end", ""),
            "shift_type": a.get("shift_type", ""),
            "working_area": a.get("working_area", ""),
            "employee_name": a.get("employee_name", ""),
            "employee_id": a.get("ordio_employee_id", ""),
            "score": a.get("score"),
            "is_applicant": a.get("is_applicant", False),
        })
    for u in unassigned:
        slot_assignments.append({
            "slot_id": u.get("slot_id", ""),
            "date": u.get("date", ""),
            "start": u.get("start", ""),
            "end": u.get("end", ""),
            "shift_type": u.get("shift_type", ""),
            "working_area": u.get("working_area", ""),
            "employee_name": None,
            "employee_id": None,
            "reason": u.get("reason", ""),
        })
    slot_assignments.sort(key=lambda x: (x["date"], x["start"]))

    # -- Assemble top-level dict ----------------------------------------------
    result = {
        "plan_id": plan.get("plan_id", ""),
        "generated_at": plan.get("generated_at", ""),
        "snapshot_id": plan.get("snapshot_id", ""),
        "betrieb": plan.get("betrieb", ""),
        "range_from": plan.get("range", {}).get("from", ""),
        "range_to": plan.get("range", {}).get("to", ""),
        "profile": plan.get("profile", ""),
        "mechanism": plan.get("mechanism", "algo"),
        "fill_rate": fill_rate,
        "fairness": fairness,
        "scoring": scoring,
        "constraints": constraints,
        "workforce": workforce,
        "assessment": assessment,
        "open_by_day": open_by_day,
        "shift_types": by_shift_type,
        "per_employee_schedule": per_employee_schedule,
        "slot_assignments": slot_assignments,
    }

    # Mechanism-specific metadata
    mech = plan.get("mechanism", "algo")
    if mech == "loose":
        result["soft_violations_count"] = len(plan.get("soft_violations", []))
    elif mech == "llm":
        result["hard_violations_count"] = len(plan.get("hard_violations", []))

    # -- Golden comparison (optional) -----------------------------------------
    if golden_comparison:
        result["golden"] = {
            k: golden_comparison[k]
            for k in ("total_slots", "exact_match", "different_employee",
                      "algo_only", "golden_only", "both_empty",
                      "match_rate", "coverage_rate")
            if k in golden_comparison
        }

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_output(
    plan: dict,
    directory: Path,
    golden_comparison: dict | None = None,
) -> dict[str, Path]:
    """Write enriched metrics.json from generate_plan() output.

    All row-level data (assignments, fairness, eval matrix) lives in
    plan.xlsx only.  Returns {"metrics.json": Path(...)}.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    metrics = _build_enriched_metrics(plan, golden_comparison)

    metrics_path = directory / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    return {"metrics.json": metrics_path}
