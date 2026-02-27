---
name: cowork-gap-resolution
description: >
  DRAFT v0.1 -- Diagnose unfilled shifts, identify blocking constraints,
  and recommend profile adjustments or manual actions to improve coverage.
  Cowork: improve this skill based on what works in practice.
version: 0.1.0
---

# Lücken-Analyse (Gap Resolution)

Systematic workflow for diagnosing why shifts are unfilled and recommending fixes. Use this when a plan has unassigned slots that need resolution.

## When to Use

- Fill rate < 90% after plan generation
- Betriebsleiter reports specific uncovered shifts
- After profile optimization still leaves gaps

## Workflow

### Step 0: Server Ready Check

The MCP server runs on Render free tier and spins down after 15 min idle. The first tool call may take ~30 seconds while the container cold-starts.

```
list_profiles()
```

If this call takes more than 5 seconds, inform the user: "Der MCP-Server startet gerade -- bitte einen Moment Geduld (~30 Sek.)." Then wait for the response before proceeding.

### Step 1: Evaluate the Plan

```
evaluate_plan(plan_id="plan-...")
```

Focus on the `unassigned_analysis` section:
- **count**: Total unfilled slots
- **reason_distribution**: Why slots are unfilled
- **by_shift_type**: Which shift types are most affected
- **by_date**: Which days have the most gaps
- **top_blocked_reasons**: The specific constraints blocking candidates

### Step 2: Load Full Plan for Details

The eval summary aggregates reasons, but for per-slot diagnosis load the full plan:

```
load_plan(plan_id="plan-...")
```

Inspect `unassigned[]` entries. Each contains:
- `slot_id`, `date`, `start`, `end`, `shift_type`
- `reason`: Why unassigned (`all_candidates_blocked_by_constraints`, `no_candidates_available`)
- `top_candidates[]`: Employees who were considered, each with `blocked_reasons[]` and `score`

### Step 3: Cross-Reference with Snapshot

```
load_snapshot(snapshot_id="...")
```

Check:
- How many employees are in the snapshot? If very few, the issue is staffing, not constraints.
- Are absences concentrated on specific dates?
- Are there employees with relevant skills who could cover the gap?

### Step 4: Inspect the Profile

```
load_profile(profile_name="...")
```

Look at:
- `employee_rules` for employees who appear in `top_candidates` as blocked
- Their `max_monthly_hours`, `no_additional_shifts`, `target_weekly_hours` settings
- Whether constraints are stricter than necessary

## Diagnosis Patterns

### Pattern: `monthly_hours_limit` dominates

Many candidates blocked by monthly hour caps.

**Root cause**: Profile caps are too strict for the available workforce.
**Resolution**: Recommend increasing `max_monthly_hours` for specific employees. Calculate how many additional hours are needed: `unassigned_count * avg_shift_hours`.

### Pattern: `no_additional_shifts` dominates

Employees flagged as unavailable for extra shifts.

**Root cause**: Too many employees excluded from scheduling.
**Resolution**: Review which employees truly need this flag. Recommend removing it for employees who could take 1-2 more shifts.

### Pattern: `rest_lt_11h` dominates

Insufficient rest time between shifts.

**Root cause**: This is ArbZG labor law -- cannot be relaxed by profile changes.
**Resolution**: The shift schedule itself needs adjustment (e.g. move a Spaet shift earlier, or skip a Frueh shift the next day). Flag for manual intervention.

### Pattern: `weekly_hours_limit` dominates

Candidates hit weekly hour caps.

**Root cause**: Employment-type caps (Werkstudent 20h, Minijob ~43h/month).
**Resolution**: Check if some employees have capacity in other weeks. The issue may resolve with a broader planning window. Or recruit additional staff for the specific shift type.

### Pattern: `no_candidates_available`

No employees exist with matching roles/skills.

**Root cause**: Staffing gap for this shift type or working area.
**Resolution**: This cannot be fixed by profile adjustments. Requires recruitment or cross-training.

### Pattern: Concentrated on specific dates

Gaps cluster on weekends, holidays, or specific days.

**Root cause**: Many employees have `no_weekend` preference or concentrated absences.
**Resolution**: Check absence calendar. If preference-driven, consider whether `mechanism="loose"` would help (it softens preference constraints).

## Resolution Strategy Matrix

| Blocked Reason | Profile Fix? | Mechanism Fix? | Manual Action? |
|---------------|-------------|---------------|----------------|
| monthly_hours_limit | Increase cap | loose may help | -- |
| no_additional_shifts | Remove flag | -- | -- |
| rest_lt_11h | No | No | Adjust schedule |
| weekly_hours_limit | Increase cap | loose may help | -- |
| max_salary_limit | Increase or disable | loose may help | -- |
| no_weekend / only_weekend | No | loose softens | Outreach |
| starts_too_early / ends_too_late | No | loose softens | Outreach |
| no_candidates_available | No | No | Recruit / cross-train |
| absence | No | No | Wait / substitute |
| consecutive_days_limit | Increase max | loose may help | -- |

## What Cowork Must NOT Do

- **Never modify Ordio data** -- all changes are profile recommendations
- **Never create or modify constraint profiles** -- recommend changes to the user
- **Never promise coverage** -- some gaps require human staffing decisions
- **Never relax ArbZG constraints** -- these are labor law, not negotiable

## Output Template

```
## Lücken-Analyse {Betrieb} KW{week}

**Unbesetzte Schichten**: {count} von {total}
**Hauptblockergrund**: {top_reason} ({pct}%)

### Diagnose

| Datum | Schichttyp | Zeit | Grund | Top-Kandidat | Blocker |
|-------|-----------|------|-------|-------------|---------|
{per-slot table}

### Empfohlene Maßnahmen

1. **Profil-Anpassung**: {specific change with employee name and new value}
2. **Mechanismus**: {if loose would help, recommend re-running}
3. **Manuell**: {shifts that need human intervention}

### Erwartete Verbesserung
Mit den empfohlenen Anpassungen könnten ca. {estimate} zusätzliche Schichten besetzt werden.
```
