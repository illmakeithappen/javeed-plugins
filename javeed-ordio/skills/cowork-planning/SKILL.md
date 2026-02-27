---
name: cowork-planning
description: >
  DRAFT v0.1 -- Autonomous weekly shift planning workflow for Cowork agents.
  Covers data sync, plan generation, evaluation, and quality-based iteration.
  Cowork: improve this skill based on what works in practice.
version: 0.1.0
---

# Wochenplanung (Weekly Planning Workflow)

Autonomous workflow for generating and validating a weekly shift plan for one Betrieb. Uses MCP tools only -- no code execution required.

## Workflow

### Step 1: Ensure Fresh Snapshot

Check for existing snapshots first, then sync if needed.

```
list_snapshots(limit=3)
```

If no snapshot covers the target week, or the snapshot is stale (>24h old):

```
sync_snapshot(betrieb="hinweg", start="2026-03-09", end="2026-03-15")
```

### Step 2: Select Constraint Profile

```
list_profiles()
```

Pick the venue-specific profile if available (e.g. `hinweg_march_2026`), otherwise use `default`. Inspect the profile to understand its rules:

```
load_profile(profile_name="hinweg_march_2026")
```

### Step 3: Generate Plan

```
generate_plan(
    range_from="2026-03-09",
    range_to="2026-03-15",
    profile_name="hinweg_march_2026",
    mechanism="algo"
)
```

The response includes assignments, unassigned slots, metrics, and fairness data. The full plan (with evaluation_matrix) is persisted to disk automatically.

### Step 4: Evaluate Plan Quality

```
evaluate_plan(plan_id="plan-...")
```

This returns scoring distribution, fairness, applicant dominance, unassigned analysis, and coverage heatmap.

### Step 5: Decide

Use the decision tree below to determine next steps.

## Decision Tree

| Fill Rate | Gini | Action |
|-----------|------|--------|
| >= 90% | < 0.30 | Plan is healthy. Present to Betriebsleiter. |
| >= 90% | >= 0.30 | Fill rate is fine but hours are unevenly distributed. Check per-employee fairness for outliers. |
| 70-89% | any | Try a different profile or `mechanism="loose"`. Re-evaluate. |
| < 70% | any | Major coverage gaps. Run gap resolution workflow (see `cowork-gap-resolution` skill). |

## Interpreting Key Metrics

- **fill_rate_pct**: % of open slots successfully assigned. Primary quality indicator.
- **gini**: 0 = perfectly equal hours distribution, 1 = one person gets all hours. Target: < 0.30.
- **applicant_driven_pct**: % of assignments where the applicant bonus contributed > 40% of the score. High values (> 60%) are normal when many employees apply.
- **unassigned_analysis.top_blocked_reasons**: Shows which constraints are causing the most blocks. Key for diagnosing low fill rates.
- **scoring_consistency**: Stable components (role, skill) should have near-zero variance. If they vary, something is wrong with the data.

## Iteration Pattern

If the first plan is unsatisfactory:

1. Try `mechanism="loose"` (relaxes some constraints, LLM refines remaining gaps)
2. Try a different profile (e.g. `default` vs venue-specific)
3. Use `compare_plans(plan_id_a, plan_id_b)` to understand what changed
4. If nothing helps, switch to gap resolution workflow

## Output Template

When presenting results, structure the summary as:

```
## Wochenplan {Betrieb} KW{week_number}

**Profil**: {profile_name} | **Mechanismus**: {mechanism}
**Besetzungsquote**: {fill_rate}% ({assigned}/{total} Schichten)
**Fairness (Gini)**: {gini}

### Unbesetzte Schichten
{count} Schichten konnten nicht besetzt werden.
Hauptgründe: {top_blocked_reasons}

### Fairness-Auffälligkeiten
{employees with large delta to target}

### Empfehlung
{next steps or approval recommendation}
```

## Constraints

- **Read-only Ordio boundary**: Never attempt to write back to Ordio. Plans are local artifacts.
- **Deterministic**: The `algo` mechanism always produces the same plan for the same inputs.
- **German domain language**: Use German terms in user-facing output (Betrieb, Schicht, Mitarbeiter, Besetzungsquote).
- **Betriebsleiter review**: Plans must be reviewed by a human before manual entry in Ordio.
