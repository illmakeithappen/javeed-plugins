# Ordio-Lite Allocation Algorithm

## Overview

The allocator is a **deterministic, single-pass, greedy** algorithm that assigns employees to open shift slots. It is read-only -- it never writes back to the Ordio API.

**Inputs:**
- A **snapshot** containing normalized employees, assigned shifts, open shifts, applications, and absences (produced by the ingest layer)
- A **date range** (`range_from`, `range_to`) filtering which open slots to consider
- A **constraint profile** (from `config/constraint_profiles.json`) providing per-employee rules and policy flags

**Outputs:**
- A **plan** object containing:
  - `assignments` -- list of slot-to-employee mappings with scores, reasons, and alternatives
  - `unassigned` -- list of slots that could not be filled, with diagnostic info
  - `metrics` -- fill rate, assignment kind counts
  - `fairness` -- per-employee hours/slots summary with target deltas

**Determinism guarantee:** Given the same snapshot, date range, and profile, the algorithm always produces the same assignments. Tiebreaking uses alphabetical employee name then employee ID, never randomness.

---

## Slot Prioritization

Before processing, open slots are sorted:

```
sort key = (-has_applicants, date, start_time, slot_id)
```

| Priority | Criterion | Rationale |
|----------|-----------|-----------|
| 1 (highest) | Slots **with** applicants first | Applicant preferences should be honored before the pool is depleted by non-applicant slots |
| 2 | Earlier date | Chronological processing keeps schedule building predictable |
| 3 | Earlier start time | Within a day, morning shifts are filled before evening |
| 4 | Slot ID (string sort) | Deterministic tiebreaker for slots on the same shift |

This ordering means an employee who applied for a specific shift is more likely to receive it, because that slot is processed while the employee is still available.

---

## Scoring Equation

For each candidate `e` and open slot `s`:

```
S(e, s) = A(e,s) + R(e,s) + F(e,s) + Ro(e,s) + Sk(e,s) + X(e,s) + P(e,s) + Sa(e,s)

where:
  A   = applicant bonus       [0, 80]     +80 if e applied for s
  R   = rest / target hours   [0, 40]     (remaining_h / target_h) * 40
  F   = fairness              [0, 30]     30 - 6 * week_shift_count
  Ro  = role fit              [0, 20]     affinity(role, shift_type)
  Sk  = skill match           [0, 12]     skills intersect working_area
  X   = fixed pattern         [0, 12]     historical weekday+time match
  P   = preference            [0, 15]     preferred shift type match
  Sa  = salary guard        [-12,  0]     penalty if projected > 90% cap

  S(e, s) = 0  if  e is blocked by any hard constraint
```

**Theoretical maximum:** 80 + 40 + 30 + 20 + 12 + 12 + 15 + 0 = **209 points**
**Theoretical minimum (unblocked):** 0 + 0 + 0 + 10 + 0 + 0 + 0 + (-12) = **-2 points**

---

## Score Components

| # | Component | Key | Max / Value | Calculation |
|---|-----------|-----|-------------|-------------|
| 1 | **Applicant bonus** | `applicant` | **80** | Full 80 points if the employee applied for this specific shift. 0 otherwise. |
| 2 | **Rest / target hours** | `rest` | **0 -- 40** | `min((remaining_hours / target_hours) * 40, 40)` where `remaining_hours = max(target - (existing_month + run_month), 0)`. If no target exists, defaults to `40 * 0.5 = 20`. Rewards employees who are furthest below their target. |
| 3 | **Fairness** | `fairness` | **0 -- 30** | `max(30 - 6 * week_shift_count, 0)` where `week_shift_count` is the number of shifts the employee already has in this ISO week (existing + run). Decays by 6 points per shift, reaching 0 at 5 shifts. |
| 4 | **Role match** | `role` | **10 or 20** | **20** if the employee's role matches the slot's shift type (direct substring match or via ROLE_AFFINITY lookup). **10** (partial) if no match or no role defined. |
| 5 | **Skill / area match** | `skill` | **0 or 12** | **12** if the employee's skills or preferred working areas (from profile) overlap with the slot's shift_type or working_area. |
| 6 | **Fixed pattern bonus** | `fixed` | **0 or 12** | **12** if the employee has historically worked this exact (weekday, start, end) combination 3+ times in the snapshot data. Rewards schedule stability. |
| 7 | **Preference match** | `preference` | **-35 to +15** | **+15** if the employee prefers this shift type (e.g., "lieber frueh" matches a "frueh" shift). **+7.5** if the slot's shift_type matches `preferred_shift_types` from the profile. **-35** if preferences are violated (but this triggers a block, so negative scores are not reached in practice). |
| 8 | **Salary warning** | `salary` | **0 or -12** | **-12** if projected monthly salary exceeds 90% of `max_salary`. Deprioritizes candidates approaching their salary limit. |

---

## Score Breakdown Example

Assignment: Raphael Yasin Morsi -> Mon Feb 23, 10:00-13:00, Kiosk (frueh)

```
                       0    10    20    30    40    50    60    70    80
  applicant    (A)  80 |█████████████████████████████████████████████████
  rest         (R)  24 |██████████████████████████████
  fairness     (F)  18 |██████████████████████
  skill       (Sk)  12 |███████████████
  role        (Ro)  10 |████████████
  preference   (P)   0 |
  fixed        (X)   0 |
  salary      (Sa)   0 |
                       ─────────────────────────────────────────────────
                                              Total: 144.35
```

Best alternative: Annika Geyer (score 92, non-applicant). Delta: -52.35.

---

## Processing Pipeline

```
  1. INGEST         Load snapshot (employees, assigned shifts, absences,
                    open shifts, applications)

  2. PREPARE        Build lookup tables:
                    - employee_by_id, rules_lookup, fixed_patterns
                    - existing_shifts_by_emp, absences_by_emp

  3. SORT SLOTS     Order: applicant slots first, then by date, start time
                    Key: (-has_applicants, date, start, slot_id)

  4. FOR EACH SLOT:
     a. EVALUATE    Score every employee against this slot
     b. BLOCK       Check hard constraints -> mark blocked candidates
     c. RANK        Sort unblocked by (-score, name, id)
     d. SELECT      If applicants exist and prefer_applicants: narrow pool
                    Pick top candidate from pool
     e. ASSIGN      Record assignment, update running state:
                    - hours_by_month, hours_by_week
                    - shift_count_by_week, working_days
     f. TRACK       Store alternatives (top 7 runners-up)

  5. OUTPUT         Build plan with assignments, unassigned, metrics, fairness
```

---

## Selection Logic

### Candidate Sorting

After scoring, candidates are sorted deterministically:

```
sort key = (blocked_flag, -score, canonical_name, employee_id)
```

- Unblocked candidates come first.
- Among unblocked, highest score wins.
- Ties broken by alphabetical canonical name (lowercase, diacritics removed).
- Final tiebreaker: employee ID string comparison.

### Applicant Preference Policy

If the slot has applicants and `policy.prefer_applicants` is true (default):

1. Filter unblocked candidates to only those who are applicants.
2. If at least one applicant is unblocked, select from applicants only.
3. If all applicants are blocked, fall back to the full unblocked pool.

This ensures that employees who proactively applied for a shift get priority, but shifts are still filled if no applicant is available.

### Assignment Kinds

Each assignment is tagged with one of three kinds:

| Kind | Meaning |
|------|---------|
| `applicant` | The assigned employee applied for this shift |
| `recommendation_without_applicant` | No one applied; the algorithm recommended the best candidate |
| `recommendation_despite_applicants` | Applicants existed but were all blocked; the algorithm recommended a non-applicant |

### State Updates After Assignment

When an employee is assigned a slot, the plan's running state is updated:

- `run_hours_by_emp_month[(emp_id, month)]` -- incremented
- `run_hours_by_emp_week[(emp_id, week)]` -- incremented
- `run_shift_count_by_emp_week[(emp_id, week)]` -- incremented
- `run_days_by_emp[emp_id]` -- date added to the set
- `run_total_hours_by_emp[emp_id]` -- incremented

These running totals feed back into constraint checks and scoring for subsequent slots. This is what makes the algorithm **greedy** -- each assignment is final and affects all later decisions.

---

## Fairness Mechanisms

### Weekly Shift Count Decay (Fairness Score)

```
fairness_score = max(30 - 6 * week_shift_count, 0)
```

- An employee with 0 shifts this week gets **30 points**.
- 1 shift: **24 points**.
- 2 shifts: **18 points**.
- 3 shifts: **12 points**.
- 4 shifts: **6 points**.
- 5+ shifts: **0 points**.

This creates a strong incentive to spread shifts across different employees within each week.

### Target Hours Tracking (Rest Score)

```
remaining = max(target - (existing_month_hours + run_month_hours), 0)
rest_score = min((remaining / target) * 40, 40)
```

Employees who are far below their monthly target receive up to **40 points**, while those who have reached their target receive **0**. This naturally balances hours toward each employee's contractual target.

### Salary Warning Penalty

Employees approaching 90% of their `max_salary` receive a **-12 point penalty**, gently deprioritizing them before the hard `max_salary_limit` block kicks in.

### Fairness Reporting

After allocation, the fairness overview produces a per-employee summary:
- `assigned_hours` -- total hours assigned in this plan
- `assigned_slots` -- number of shifts
- `target_hours` -- from their profile/contract
- `delta_to_target` -- over/under target (positive = over)

---

## Unassigned Slot Handling

When no valid candidate exists for a slot, it is added to the `unassigned` list with a diagnostic reason:

| Reason | Condition |
|--------|-----------|
| `no_candidates_available` | The employee list is empty (should not occur in practice) |
| `all_candidates_blocked_by_constraints` | Every employee was blocked by at least one hard constraint |
| `all_applicants_blocked` | Applicants exist but are all blocked, and all non-applicants are also blocked |
| `no_valid_candidate` | Generic fallback reason |

Each unassigned entry includes `top_candidates` -- the top 5 evaluated candidates (blocked or not) with their blocking reasons and scores. This enables diagnostic queries like "why was this slot unfilled?" and "who was closest to being eligible?".

---

## Data Normalization

The allocator operates on a normalized snapshot built by the ingest layer. Key normalization steps:

### Employee Normalization

- Extracts `hourly_wage` and `max_salary` from the active wage record.
- Maps `branch_working_area_ids` to human-readable skill names.
- Derives `employment` type name (Minijob, Werkstudent, etc.) from wage or employment lookup.
- Computes `full_name` and `name_key` (canonical form for matching).
- Candidate-only employees (those who appear in shift applications but not in the employee list) are backfilled.

### Shift Type Inference

| Type | Inference rule |
|------|---------------|
| `theke` | Working area or note contains "theke" |
| `bar` | Working area or note contains "bar" |
| `kueche` | Working area or note contains "kueche" or "kuche" |
| `frueh` | Start time before 11:00 |
| `spaet` | Start time >= 16:00 or end time >= 22:00 |
| `doppel` | Start <= 11:00 and end >= 20:00 |
| `normal` | Default fallback |

Working area/note keywords take priority over time-based rules.

### Open Slot Construction

For each Ordio shift, the ingest layer computes:
- `required_employee_count = max(employee_count field, number of active candidates, 1)`
- `open_count = required - active_candidates`
- Creates `open_count` individual slot records, each carrying the list of `applicant_employee_ids`

### Fixed Pattern Detection

Scans all assigned shifts in the snapshot and identifies (employee, weekday, start, end) combinations that appear **3 or more times**. These are treated as "fixed" schedule patterns, earning the employee a +12 bonus when a matching slot appears.

---

## Role Affinity Table

| Role | Compatible shift types |
|------|----------------------|
| `service` | frueh, normal, spaet, doppel, service, theke |
| `kellner` | frueh, normal, spaet, service, theke |
| `bar` | spaet, normal, bar, theke |
| `koch` | frueh, normal, spaet, kueche |
| `kueche` | frueh, normal, spaet, kueche |

---

## Constraint Profiles

Profiles are stored in `config/constraint_profiles.json`. Each profile contains a `policy` block (global settings) and an `employee_rules` block (per-employee overrides).

### Policy Settings

| Key | Type | Default | Effect |
|-----|------|---------|--------|
| `prefer_applicants` | bool | `true` | When true, applicants are preferred over non-applicants for slots they applied to |
| `max_consecutive_days` | int | `5` | Maximum consecutive working days before blocking |
| `distribute_applications_across_month` | bool | `false` | (Declared but not yet implemented) |
| `prefer_shift_type_variation` | bool | `false` | (Declared but not yet implemented) |

### Employee Rules

Employee rules are matched by canonical name (lowercase, diacritics stripped). The lookup tries full name, then first name, then username.

| Key | Type | Effect |
|-----|------|--------|
| `target_weekly_hours` | float | Sets the employee's target (converted to monthly via * 4.33). Drives the "rest" score component and acts as a monthly cap. |
| `target_monthly_hours` | float | Direct monthly target. Takes priority over weekly target. |
| `max_monthly_hours` | float | Hard monthly hours cap. If no target is set, also acts as the target for scoring. |
| `max_weekly_hours` | float | Hard weekly hours cap applied to plan-run hours only. |
| `max_additional_monthly_hours` | float | Limits how many hours the plan can add in a month (independent of existing hours). |
| `base_weekly_hours` | float | Informational only; not used in allocation logic. Documents the employee's base contract. |
| `no_additional_shifts` | bool | Hard block -- the employee receives no plan assignments at all. |
| `disable_max_hours` | bool | Removes the monthly hours cap entirely. |
| `preferred_working_areas` | list[str] | Contributes to skill score (+12) when the slot's area matches. |
| `preferred_shift_types` | list[str] | Contributes to preference score (+7.5) when the slot's type matches. |
| `notes` | str | Free-text field parsed for structured preferences (see constraints reference). |

---

## Limitations and Improvement Ideas

### Current Limitations

- **Single-pass greedy:** The algorithm makes irrevocable decisions. An early assignment may prevent a globally better solution. For example, assigning Employee A to Slot 1 may leave Slot 2 unfillable, whereas assigning Employee B to Slot 1 could have filled both.

- **No swap detection:** After the plan is built, there is no post-processing to identify beneficial swaps (e.g., "if A and B switch slots, both get higher scores").

- **Preference violations are hard blocks:** An employee who prefers no weekends will never be assigned a weekend shift even if they are the only candidate. Soft-penalty mode could improve fill rates.

- **max_shifts_week parsed but not enforced:** The "max N schichten" note pattern is parsed into preferences but never checked as a hard constraint during evaluation.

- **distribute_applications_across_month not implemented:** The policy flag exists in profiles but has no allocator logic. Intent is to prevent one employee from being assigned all their applications in the first week.

- **prefer_shift_type_variation not implemented:** Would encourage assigning different shift types to the same employee across the week.

- **Monthly cap as proxy for target:** When `target_monthly_hours` or `target_weekly_hours` is set, it also acts as a hard monthly cap. This means an employee cannot exceed their target even if slots are unfilled, which may not always be desired.

### Potential Improvements

- **Multi-pass optimization:** Run the greedy pass, then attempt swaps between assignments to improve total score or fill rate.

- **Backtracking on unassigned slots:** When a slot cannot be filled, check whether reassigning a previous slot's employee would free up a candidate for the current slot.

- **Configurable hard/soft preference mode:** Allow profile rules to specify whether preferences are blocking or just scoring penalties.

- **Shift type variation scoring:** Add a score component that rewards employees for working different shift types.

- **Demand-based slot weighting:** Allow certain slots (e.g., Friday evening) to be marked as high-priority, influencing which employees are reserved for them.
