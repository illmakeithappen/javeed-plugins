# Allocation Mechanisms

## Overview

The allocation system supports three mechanisms via `allocation_core.mechanisms.run_mechanism()`. All return plan dicts with the same top-level structure.

## Mechanism 1: algo (Deterministic Greedy)

**How it works:**
1. Sort open slots by priority (applicant slots first, then chronological)
2. For each slot, score every employee against 8 components (max ~209 points)
3. Apply 16 hard constraints -- blocked candidates get score 0
4. Assign the highest-scoring unblocked candidate
5. Update running state (hours, shifts, days) for subsequent decisions

**Constraint mode:** `strict` -- all hard constraints enforced, no relaxation.

**When to use:** Default for production plans. Deterministic, reproducible, fast.

**Code pattern:**
```python
plan = run_mechanism("algo", snapshot, range_from=start, range_to=end,
                     profile_name=name, profile=profile)
```

## Mechanism 2: loose (Relaxed + LLM Refinement)

**How it works:**
1. Run the greedy algorithm with `constraint_mode="loose"` (some constraints relaxed)
2. Pass the result + unassigned slots to an LLM for refinement
3. LLM can reassign slots, suggest swaps, or fill previously unassigned slots
4. Final plan includes both algorithmic and LLM-refined assignments

**When to use:** When the `algo` mechanism leaves too many slots unfilled due to strict constraints. The loose pass fills more slots, then the LLM applies human judgment.

**Code pattern:**
```python
plan = run_mechanism("loose", snapshot, range_from=start, range_to=end,
                     profile_name=name, profile=profile)
```

## Mechanism 3: llm (Pure LLM Allocation)

**How it works:**
1. Send snapshot data, profile, and open slots to an LLM
2. LLM generates the full allocation based on its understanding of the domain
3. Hard constraints are validated post-hoc
4. Plan includes `hard_violations` field listing any constraint breaches

**When to use:** Experimental. When you want to compare human-like judgment against the algorithm. Always validate results against hard constraints.

**Code pattern:**
```python
plan = run_mechanism("llm", snapshot, range_from=start, range_to=end,
                     profile_name=name, profile=profile)
# Check plan["hard_violations"] for constraint breaches
```

## Comparing Mechanisms

Run all three on the same data to compare:

```python
from allocation_core.mechanisms import MECHANISMS, run_mechanism

results = {}
for mech in MECHANISMS:  # ("algo", "loose", "llm")
    results[mech] = run_mechanism(mech, snapshot, range_from=start,
                                  range_to=end, profile_name=name, profile=profile)

# Compare fill rates
for mech, plan in results.items():
    m = plan.get("metrics", {})
    print(f"{mech}: {m.get('assigned_slots', 0)}/{m.get('total_slots', 0)} "
          f"({m.get('fill_rate', 0)}%)")
```
