"""Shared role-to-shift fit scoring helpers."""

from __future__ import annotations

from collections.abc import Mapping, Set


def compute_role_match_score(
    role: str | None,
    shift_type: str | None,
    *,
    affinity_map: Mapping[str, Set[str]],
    exact_score: float,
    affinity_score: float,
    partial_score: float,
) -> float:
    """Compute role/shift fit score with exact, affinity, and fallback levels."""
    role_norm = str(role or "").lower().strip()
    shift_norm = str(shift_type or "").lower().strip()
    if not role_norm or not shift_norm:
        return float(partial_score)

    if role_norm in shift_norm or shift_norm in role_norm:
        return float(exact_score)

    affinity = affinity_map.get(role_norm)
    if affinity and shift_norm in affinity:
        return float(exact_score)

    for key, allowed in affinity_map.items():
        if key in role_norm and shift_norm in allowed:
            return float(affinity_score)

    return float(partial_score)
