# Golden Sample Comparison Methodology

## Overview

The golden comparison evaluates algorithm output against a manually verified "golden" set of assignments. It answers: "How closely does the algorithm match what a human expert would assign?"

**Computed by:** `evals.shared.metrics.compute_golden_comparison()`

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `golden_rows` | CSV or manual entry | `[{slot_id, employee_name}]` -- expert assignments |
| `assignments` | Algorithm output | Plan assignments from `run_mechanism()` |
| `unassigned` | Algorithm output | Slots the algorithm could not fill |
| `plan` (optional) | Full plan dict | Provides `evaluation_matrix` for alternative lookup |

## Slot-Level Classification

For each slot, the comparison classifies the outcome:

| Classification | Condition | Meaning |
|---------------|-----------|---------|
| `exact_match` | Golden and algo assign the same employee | Perfect agreement |
| `different_employee` | Both assign someone, but different people | Divergent decisions |
| `algo_only` | Algo assigned, golden has no assignment | Algo fills a gap golden left open |
| `golden_only` | Golden assigned, algo did not | Algo missed an assignment |
| `both_empty` | Neither assigned anyone | Both agree slot is unfillable |

## Aggregate Metrics

**Dataclass:** `GoldenComparison`

| Metric | Formula | Description |
|--------|---------|-------------|
| `total_slots` | Count of all slot IDs | Total compared |
| `exact_match` | Count of exact matches | Agreement count |
| `different_employee` | Count of divergences | Disagreement count |
| `algo_only` | Count | Algo filled, golden didn't |
| `golden_only` | Count | Golden filled, algo didn't |
| `both_empty` | Count | Neither filled |
| `match_rate` | `exact_match / (exact_match + different_employee) * 100` | Agreement % (comparable slots only) |
| `coverage_rate` | `golden_with_employee / total_golden * 100` | Golden sample completeness |

## Per-Slot Detail

Each slot comparison includes:

| Field | Description |
|-------|-------------|
| `slot_id` | Slot identifier |
| `date`, `start`, `end` | Shift timing |
| `shift_type`, `area` | Shift classification |
| `golden_employee` | Who the expert assigned |
| `algo_employee` | Who the algorithm assigned |
| `match` | Classification (exact_match, different_employee, etc.) |
| `algo_score` | Algorithm's score for its chosen employee |
| `golden_in_alternatives` | Whether the golden employee appears in algo's alternatives |
| `golden_alt_rank` | Golden employee's rank in alternatives (if present) |

## Per-Employee Hours Comparison

For each employee mentioned in either golden or algo:

| Field | Description |
|-------|-------------|
| `employee` | Employee name |
| `algo_hours` | Total hours assigned by algorithm |
| `golden_hours` | Total hours assigned in golden |
| `delta` | `algo_hours - golden_hours` (positive = algo assigns more) |

## Interpreting Results

### Match Rate
- **> 80%**: Strong alignment -- algorithm closely matches expert judgment
- **60-80%**: Moderate alignment -- review divergent cases
- **< 60%**: Significant divergence -- investigate constraint or scoring differences

### Divergence Analysis

When `different_employee` count is high:
1. Check if golden employees appear in algo's alternatives (field: `golden_in_alternatives`)
2. If yes, the algo scored them lower -- investigate scoring weights
3. If no, the algo blocked them -- check constraint differences

### Golden-Only Cases

When golden assigns but algo doesn't:
- Algo may have stricter constraints
- Golden expert may have overridden a constraint (e.g., allowing a 6th consecutive day)

### Algo-Only Cases

When algo assigns but golden doesn't:
- Golden expert may have intentionally left the slot open
- Algo may be over-filling with marginal candidates
