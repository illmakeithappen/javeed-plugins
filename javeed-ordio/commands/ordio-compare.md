---
description: Compare allocation plans across constraint profiles
allowed-tools: Read
argument-hint: <start> <end> [profile1,profile2,...]
---

# Ordio Plan Comparison

Generate allocation plans with multiple constraint profiles and compare fill rates, fairness, and trade-offs side by side.

## Usage

`/ordio-compare <start> <end> [profile1,profile2,...]`

- **start** -- ISO date, plan range start.
- **end** -- ISO date, plan range end.
- **profiles** -- Comma-separated profile names to compare. Default: all profiles that match the current betrieb.

## Instructions

Follow these steps in order. Do NOT skip steps or combine them.

### Step 1: Check for snapshot

Call `list_snapshots(limit=1)`.

If no snapshot exists, tell the user to run `/ordio-weekly` first. Do not proceed without a snapshot.

Note the snapshot's betrieb for profile filtering.

### Step 2: Determine profiles to compare

Call `list_profiles()`.

If profiles were provided, validate each exists. If any don't exist, report the error and continue with valid ones.

If profiles were NOT provided, select all profiles. Always include `default`. Filter to profiles whose name or description matches the snapshot's betrieb if possible (e.g. `hinweg_march_2026` for betrieb `hinweg`). If no location-specific profiles exist, compare just `default`.

Minimum 2 profiles required for comparison. If only 1 is available, tell the user and suggest creating a custom profile.

Tell the user which profiles will be compared.

### Step 3: Generate plans

For each profile, call `generate_plan(range_from=start, range_to=end, profile_name=profile, snapshot_id=snapshot_id)`.

Collect the plan_id and immediate fill rate for each.

### Step 4: Collect plan summaries

For each plan, call `plan_summary(plan_id)`.

Collect: fill rate, assignment kind counts, hours_by_employee, unassigned count and reasons.

### Step 5: Build comparison table

Present the side-by-side comparison:

```
## Plan Comparison: [start] -- [end]

| Metric | [Profile A] | [Profile B] | ... |
|--------|------------|------------|-----|
| Fill Rate | X% | X% | |
| Assigned (applicant) | X | X | |
| Assigned (recommendation) | X | X | |
| Unassigned | X | X | |
| Applicant Satisfaction | X% | X% | |
| Employees Used | X | X | |
| Max Hours (single emp) | Xh | Xh | |
| Min Hours (single emp) | Xh | Xh | |
| Hours Std Dev | X | X | |
```

**Applicant satisfaction** = assignments where the employee applied / total assignments with applicants.

**Hours Std Dev** = standard deviation of hours across assigned employees (lower = fairer distribution).

### Step 6: Identify trade-offs

Analyze the comparison for key trade-offs:

- **Fill rate vs fairness** -- does a higher fill rate come at the cost of concentrating hours on fewer employees?
- **Applicant satisfaction vs coverage** -- does prioritizing applicants leave more slots unfilled?
- **Constraint strictness** -- which profile blocks the most candidates, and why?

Also identify **divergent assignments** -- slots that are assigned to different employees across profiles. Pick up to 3 notable divergences and briefly explain why. Use `ask_plan(plan_question="why was [employee] assigned to [date] [time]?")` on each plan if needed.

### Step 7: Recommendation

Based on the comparison, recommend the best-fit profile:

```
### Recommendation

**[Profile name]** provides the best balance:
- Fill rate: X% ([comparison to others])
- Fairness: [assessment]
- Applicant satisfaction: X%

**Trade-off:** [what you give up vs the other profile]

**When to use [other profile] instead:** [scenario where the other profile is better]
```

### Step 8: Offer report generation

Ask the user if they want to generate an HTML report for the recommended plan:
- "Generate the full HTML report for [recommended profile]? Run `/ordio-plan [start] [end] [profile]` for the detailed view."

## Reference Documents

Before explaining trade-offs between profiles or divergent assignments, read:

- **Algorithm**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/algorithm.md`
- **Constraints**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/constraints.md`

## Output Format

All output in chat as formatted markdown. The comparison table is the centerpiece. Lead with it, then explain the trade-offs, then give the recommendation. Keep the recommendation direct and opinionated.
