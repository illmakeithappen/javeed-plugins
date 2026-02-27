---
name: cowork-optimization
description: >
  DRAFT v0.1 -- Generate plans with multiple constraint profiles,
  compare them, and recommend the best-fit profile for a given week.
  Cowork: improve this skill based on what works in practice.
version: 0.1.0
---

# Profil-Optimierung (Profile Optimization)

When a single plan does not meet quality targets, generate plans with different profiles and compare them to find the best fit.

## When to Use

- Fill rate is between 70-90% and you want to see if a different profile improves it
- Betriebsleiter wants to understand the trade-offs between constraint strictness and coverage
- A new constraint profile has been created and needs validation against the existing one

## Workflow

### Step 0: Server Ready Check

The MCP server runs on Render free tier and spins down after 15 min idle. The first tool call may take ~30 seconds while the container cold-starts.

```
list_profiles()
```

If this call takes more than 5 seconds, inform the user: "Der MCP-Server startet gerade -- bitte einen Moment Geduld (~30 Sek.)." Then wait for the response before proceeding. (This call also serves Step 1 below.)

### Step 1: Discover Available Profiles

```
list_profiles()
```

Identify profiles relevant to the target Betrieb. Usually there is a `default` profile and one or more venue-specific profiles (e.g. `bacchus_march_2026`, `hinweg_march_2026`).

### Step 2: Generate Plans for Each Profile

Run `generate_plan` once per profile, against the same snapshot:

```
generate_plan(range_from="2026-03-09", range_to="2026-03-15",
              profile_name="default", snapshot_id="...")

generate_plan(range_from="2026-03-09", range_to="2026-03-15",
              profile_name="hinweg_march_2026", snapshot_id="...")
```

Note the `plan_id` from each response.

### Step 3: Pairwise Comparison

```
compare_plans(plan_id_a="plan-...", plan_id_b="plan-...")
```

This returns:
- **plan_a / plan_b**: Aggregate metrics for each plan
- **deltas**: Differences in fill rate, mean score, gini, assigned count
- **slot_divergence**: How many slots got the same vs different employees, agreement rate
- **employee_comparison**: Per-employee hour differences, sorted by largest delta

### Step 4: Evaluate the Winner

Run `evaluate_plan` on the better plan for a detailed quality breakdown:

```
evaluate_plan(plan_id="plan-...")
```

## How to Read Comparison Results

### Significance Thresholds

| Metric | Threshold | Interpretation |
|--------|-----------|---------------|
| fill_rate delta | > 5% | Meaningful difference in coverage |
| fill_rate delta | <= 5% | Noise -- profiles are roughly equivalent |
| gini delta | > 0.05 | Meaningful shift in fairness |
| gini delta | <= 0.05 | Negligible fairness difference |
| mean_score delta | > 10 | One profile produces notably better-scored assignments |
| agreement_rate | > 90% | Profiles agree on almost all slots |
| agreement_rate | 70-90% | Moderate divergence -- worth investigating |
| agreement_rate | < 70% | Very different plans -- check the top divergent slots |

### Divergent Slot Analysis

The `top_divergent_slots` list shows the slots where the two plans assigned different employees, sorted by score delta. For each:

- Check if plan A's employee has a higher score (positive delta = plan A chose better)
- Check the shift type and date -- patterns may emerge (e.g. all Spaet shifts diverge)
- Cross-reference with employee rules in the profile to understand why

### Employee Hour Analysis

The `employee_comparison` shows who gets more/fewer hours in each plan. Large deltas indicate the profile significantly reshuffles workload. Check whether the employee with more hours is approaching their monthly cap.

## Iteration: When No Profile Satisfies

If all profiles produce a fill rate < 70% or gini > 0.35:

1. Identify the top blocking constraints from `evaluate_plan` -> `unassigned_analysis.top_blocked_reasons`
2. Suggest specific profile adjustments:
   - `monthly_hours_limit` blocks? "Increase max_monthly_hours for employee X from 43 to 55"
   - `no_additional_shifts` blocks? "Remove no_additional_shifts flag for employee Y"
   - `rest_lt_11h` blocks? This is ArbZG law -- cannot be relaxed. Schedule must change.
3. Present adjustments as recommendations to the user. Do NOT create profiles autonomously.

## Output Template

```
## Profilvergleich KW{week}

| Metrik | {profile_a} | {profile_b} | Delta |
|--------|-------------|-------------|-------|
| Besetzungsquote | {fill_a}% | {fill_b}% | {delta}% |
| Gini | {gini_a} | {gini_b} | {delta} |
| Mean Score | {score_a} | {score_b} | {delta} |
| Slotübereinstimmung | -- | -- | {agreement_rate}% |

### Empfehlung
{profile_name} ist besser geeignet weil {reason}.

### Divergente Schichten
{top 3-5 divergent slots with explanation}
```
