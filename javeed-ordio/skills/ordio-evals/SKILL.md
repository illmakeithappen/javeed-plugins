---
name: ordio-evals
description: >
  Use when the user asks about evaluating plans, plan quality, metrics,
  fill rate analysis, fairness assessment, scoring distribution, series
  comparison, meta evaluation, golden sample comparison, or needs to
  assess how well an allocation plan performs.
version: 1.0.0
---

# Ordio Evaluation Pipeline

This skill covers the eval pipeline for assessing allocation plan quality. It supports single-plan evaluation, series trend analysis, and cross-system meta comparison.

## Running Evaluations via Code Execution

### Single Plan Evaluation

```python
from evals.pipeline_plugin.eval_plugin import evaluate_plan

result = evaluate_plan(
    plan_id="plan-8e4456803f41",
    artifact_root="plugins/javeed-ordio/artifacts",
)
# Returns dict with: fill_rate, assignment_kinds, unassigned_analysis,
# scoring_distribution, applicant_dominance, scoring_consistency,
# coverage_heatmap, fairness, normalized_score_averages
```

### Series Evaluation (Trend Analysis)

```python
from evals.pipeline_plugin.eval_plugin import evaluate_plan_series

result = evaluate_plan_series(
    limit=5,
    artifact_root="plugins/javeed-ordio/artifacts",
)
# Returns: series of {plan_id, fill_rate, mean_score, gini, ...}
```

### Meta Evaluation (Cross-System Comparison)

Compare the plugin's allocation against the backend allocator:

```python
from evals.pipeline_meta.eval_meta import evaluate_meta

result = evaluate_meta(
    run_id=42,          # backend eval run ID
    plan_id="plan-abc", # plugin plan ID
    db_path="api/db/database.db",
    artifact_root="plugins/javeed-ordio/artifacts",
)
# Returns: decision_divergence, scoring_calibration, constraint_consistency,
# fill_rate_comparison, fairness_comparison, insights
```

## Key Metrics

| Metric | What it measures | Good value |
|--------|-----------------|------------|
| **Fill rate** | % of slots assigned | > 85% |
| **Gini coefficient** | Hours distribution equality (0 = equal, 1 = unequal) | < 0.3 |
| **Mean score** | Average assignment score | > 80 |
| **Applicant satisfaction** | % of applicant-driven assignments | > 60% |
| **Scoring consistency** | Variance of stable components across employees | Near zero |

## Interpreting Results

### Fill Rate
- **> 90%**: Healthy plan
- **70-90%**: Some gaps; check constraint strictness or staffing levels
- **< 70%**: Major issues; likely constraint over-restriction or insufficient applicants

### Fairness (Gini)
- **< 0.15**: Excellent distribution
- **0.15-0.30**: Acceptable
- **> 0.30**: Some employees over/under-allocated; check target hours settings

### Applicant Dominance
- `applicant_driven_pct` > 50%: applicant bonus dominates scoring (expected when many applicants)
- `avg_applicant_share` > 0.4: most assignment decisions are driven by who applied

### Scoring Consistency
- `stable_components` (role, skill) should have near-zero variance across an employee's assignments
- `dynamic_components` (rest, fairness) naturally vary as state updates between slots

For metric formulas: `references/metrics.md`
For golden comparison methodology: `references/golden-comparison.md`
