"""Mechanism dispatcher for shift allocation.

Routes to the appropriate allocation strategy:
  - algo:  Deterministic greedy scorer with strict constraints
  - loose: Relaxed algorithm + LLM refinement pass
  - llm:   Pure LLM allocation with post-hoc constraint validation
"""

from __future__ import annotations

from typing import Any

MECHANISMS = ("algo", "loose", "llm")


def run_mechanism(
    mechanism: str,
    snapshot: dict[str, Any],
    *,
    range_from: str,
    range_to: str,
    profile_name: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Run the specified allocation mechanism and return a plan dict.

    All mechanisms return plan dicts with identical top-level structure.
    """
    from .allocator import generate_plan
    from .constraints import validate_plan_hard_constraints
    from .llm_allocator import generate_plan_pure_llm, refine_plan_llm

    if mechanism == "algo":
        plan = generate_plan(
            snapshot,
            range_from=range_from,
            range_to=range_to,
            profile_name=profile_name,
            profile=profile,
            constraint_mode="strict",
        )
        plan["mechanism"] = "algo"

    elif mechanism == "loose":
        loose = generate_plan(
            snapshot,
            range_from=range_from,
            range_to=range_to,
            profile_name=profile_name,
            profile=profile,
            constraint_mode="loose",
        )
        plan = refine_plan_llm(loose, snapshot, profile)
        plan["mechanism"] = "loose"

    elif mechanism == "llm":
        plan = generate_plan_pure_llm(
            snapshot,
            profile,
            range_from=range_from,
            range_to=range_to,
            profile_name=profile_name,
        )
        violations = validate_plan_hard_constraints(plan, snapshot, profile)
        plan["hard_violations"] = violations
        plan["mechanism"] = "llm"

    else:
        raise ValueError(f"Unknown mechanism: {mechanism!r}. Choose from {MECHANISMS}")

    return plan
