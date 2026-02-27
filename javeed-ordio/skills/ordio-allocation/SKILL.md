---
name: ordio-allocation
description: >
  Use when the user asks about shift allocation, Schichtplanung, scoring,
  constraint profiles, why someone was assigned, ArbZG rules, Minijob limits,
  Werkstudent hours, fairness, plan generation, mechanisms (algo, loose, llm),
  or needs to run the allocator against snapshot data.
version: 1.0.0
---

# Ordio Allocation

This skill covers the shift allocation engine: scoring formula, hard constraints, three allocation mechanisms, and how to run them via `allocation_core`.

## Three Allocation Mechanisms

The allocation system supports three mechanisms, each with different trade-offs:

| Mechanism | How it works | When to use |
|-----------|-------------|-------------|
| **algo** | Deterministic greedy scorer with strict constraints | Default. Reproducible, fast, predictable. |
| **loose** | Relaxed algorithm + LLM refinement pass | When strict constraints leave too many slots unfilled. |
| **llm** | Pure LLM allocation with post-hoc constraint validation | Experimental. When human-like judgment is needed. |

### Running Allocation via Code Execution

All mechanisms are run through `allocation_core.mechanisms.run_mechanism()`:

```python
from allocation_core.mechanisms import run_mechanism

# Load snapshot and profile via MCP tools first, then:
plan = run_mechanism(
    "algo",          # or "loose" or "llm"
    snapshot,        # dict from load_snapshot MCP tool
    range_from="2026-03-03",
    range_to="2026-03-09",
    profile_name="hinweg_march_2026",
    profile=profile,  # dict from load_profile MCP tool
)

# Save result via MCP tool
import json
save_plan(json.dumps(plan))
```

For the **algo** mechanism, `constraint_mode="strict"` is used (default).
For the **loose** mechanism, the allocator runs with `constraint_mode="loose"`, then an LLM refines unassigned slots.
For the **llm** mechanism, the LLM generates the full plan, then hard constraints are validated post-hoc.

## Scoring Overview

Each unblocked candidate receives a composite score (max ~209 points):

| Component | Key | Max | What it rewards |
|-----------|-----|-----|-----------------|
| Applicant bonus | `applicant` | 80 | Employee applied for this shift |
| Rest / target hours | `rest` | 40 | Below monthly target |
| Fairness | `fairness` | 30 | Few shifts this week |
| Role fit | `role` | 20 | Role matches shift type |
| Preference match | `preference` | 15 | Preferred shift type |
| Skill / area match | `skill` | 12 | Skills match work area |
| Fixed pattern | `fixed` | 12 | Historical schedule match |
| Salary warning | `salary` | -12 | Penalty near salary cap |

## Hard Constraints (16 Blockers)

Key categories:
- **Profile blocks**: `no_additional_shifts` flag
- **Absence**: slot date in absence period
- **Same-day**: already has a shift that day
- **ArbZG (labor law)**: time overlap, daily >10h, weekly cap, <11h rest, consecutive days >5
- **Contract limits**: monthly hours, additional monthly hours, weekly hours, salary
- **Preferences**: no weekend, only weekend, starts too early, ends too late

For full details: `references/constraints.md`

## Plan Output Structure

```json
{
  "plan_id": "plan-abc123",
  "betrieb": "hinweg",
  "range": {"from": "2026-03-03", "to": "2026-03-09"},
  "profile": "hinweg_march_2026",
  "mechanism": "algo",
  "assignments": [{
    "slot_id": "...",
    "ordio_employee_id": "...",
    "employee_name": "...",
    "date": "2026-03-03",
    "start": "10:00", "end": "16:00",
    "shift_type": "frueh",
    "score": 144.35,
    "score_detail": {"applicant": 80, "rest": 24, "fairness": 18, ...},
    "assignment_kind": "applicant",
    "hours": 6.0,
    "alternatives": [...]
  }],
  "unassigned": [{
    "slot_id": "...",
    "date": "...",
    "reason": "all_candidates_blocked_by_constraints",
    "top_candidates": [...]
  }],
  "metrics": {"total_slots": 8, "assigned_slots": 7, "fill_rate": 87.5},
  "fairness": [{"employee": "...", "assigned_hours": 12, "target_hours": 34.6, ...}]
}
```

## Reference Documents

- `references/algorithm.md` -- Full scoring formula, processing pipeline, role affinity, fairness mechanisms
- `references/constraints.md` -- All 16 hard constraints, monthly/weekly cap decision trees, preference parsing
- `references/mechanisms.md` -- Mechanism details, when to use each, code patterns
- `references/review-sheet.md` -- Wochenplan-Freigabe UI spec (German reasoning templates)
