# Evaluation Metrics Reference

All metrics are computed by `evals.shared.metrics`. This document describes the formulas and dataclasses.

## Fill Rate Metrics

**Dataclass:** `FillRateMetrics`

| Field | Type | Description |
|-------|------|-------------|
| `total_slots` | int | Total open slots (assigned + unassigned) |
| `assigned` | int | Number of assigned slots |
| `unassigned` | int | Number of unassigned slots |
| `fill_rate` | float | `assigned / total_slots * 100` (percentage) |
| `by_applicant` | int | Assignments where employee applied |
| `by_recommendation` | int | Assignments without applicant match |
| `by_date` | dict | Per-date breakdown: `{date: {assigned: N, unassigned: N}}` |
| `by_shift_type` | dict | Per-type breakdown: `{type: {assigned: N, unassigned: N}}` |

**Formula:**
```
fill_rate = (assigned / total_slots) * 100
```

## Fairness Metrics

**Dataclass:** `FairnessMetrics`

| Field | Type | Description |
|-------|------|-------------|
| `gini` | float | Gini coefficient of hours distribution (0 = equal, 1 = unequal) |
| `std_dev` | float | Standard deviation of assigned hours |
| `mean_hours` | float | Mean assigned hours across employees |
| `per_employee` | list | Per-employee: `{employee, assigned_hours, target_hours, delta}` |

**Gini Coefficient Formula:**
```
Given sorted values v_1 <= v_2 <= ... <= v_n:
gini = (2 * sum((i+1) * v_i)) / (n * sum(v_i)) - (n+1) / n
```

Interpretation:
- 0.0 = perfectly equal distribution
- 0.15 = good fairness
- 0.30 = acceptable
- > 0.30 = uneven, investigate target hours

## Scoring Distribution

**Dataclass:** `ScoringDistribution`

| Field | Type | Description |
|-------|------|-------------|
| `mean` | float | Average total score |
| `median` | float | Median total score |
| `std` | float | Score standard deviation |
| `min` / `max` | float | Score range |
| `q25` / `q75` | float | Quartile boundaries |
| `histogram` | list | `[{range_start, range_end, count}]` with 10 equal-width bins |
| `per_component` | dict | Per-component stats: `{component: {mean, median, std, ...}}` |

**Components analyzed:** `rest`, `fairness`, `role`, `skill`, `fixed`, `preference`, `applicant`, `salary`

## Constraint Satisfaction

**Dataclass:** `ConstraintSatisfaction`

| Field | Type | Description |
|-------|------|-------------|
| `total_candidates` | int | Total candidate evaluations |
| `blocked` | int | Number blocked by hard constraints |
| `block_rate` | float | `blocked / total_candidates * 100` |
| `reason_distribution` | dict | `{reason_key: count}` sorted by frequency |

## Plugin-Specific Analyses

These are computed by `evals.pipeline_plugin.eval_plugin`:

### Unassigned Analysis

| Field | Description |
|-------|-------------|
| `count` | Number of unassigned slots |
| `reason_distribution` | `{reason: count}` (e.g., all_candidates_blocked) |
| `by_shift_type` | Unassigned slots by type |
| `by_date` | Unassigned slots by date |
| `top_blocked_candidate_reasons` | Top 10 reasons candidates were blocked |

### Applicant Dominance

| Field | Description |
|-------|-------------|
| `applicant_driven_count` | Assignments where applicant bonus > 40% of total score |
| `applicant_driven_pct` | Percentage of all assignments |
| `avg_applicant_share` | Mean ratio of applicant bonus to total score |
| `total_with_applicant_bonus` | Assignments that had any applicant bonus |

### Scoring Consistency

Measures whether stable score components (role, skill) remain constant across an employee's multiple assignments. Dynamic components (rest, fairness) are expected to vary.

| Field | Description |
|-------|-------------|
| `employees_with_multiple` | Employees with 2+ assignments |
| `stable_components` | `{component: {mean_variance, expected: "near zero"}}` |
| `dynamic_components` | `{component: {mean_variance, expected: "may vary"}}` |

### Coverage Heatmap

Grid of `{date, shift_type, status}` where status is "filled" or "unfilled".

## Series Evaluation

Trend analysis over multiple plans:

| Field | Description |
|-------|-------------|
| `plan_id` | Plan identifier |
| `fill_rate` | Fill rate for this plan |
| `mean_score` | Average assignment score |
| `gini` | Gini coefficient |
| `assignment_kinds` | `{kind: count}` breakdown |

Useful for tracking allocation quality over time as profiles and data change.
