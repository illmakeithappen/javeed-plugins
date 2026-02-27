---
description: Deep-dive into a single employee's shift profile and anomalies
allowed-tools: Read
argument-hint: <name>
---

# Ordio Employee Deep-Dive

Look up a single employee's complete shift profile, cross-reference with plan fairness data, and flag anomalies.

## Usage

`/ordio-employee <name>`

- **name** -- Employee name (supports fuzzy/partial match, e.g. "annika", "Raphael Morsi")

## Instructions

Follow these steps in order. Do NOT skip steps or combine them.

### Step 1: Look up the employee

Call `get_employee_shift_profile(employee_query=name)`.

If no match is found, tell the user and suggest partial name matches or ask them to clarify.

Present the employee profile:

```
## [Full Name]
| Field | Value |
|-------|-------|
| Role | [role] |
| Employment | [employment type] |
| Hourly Wage | [wage] |
| Max Salary | [max_salary] |
| Skills | [skills list] |
```

Then present their current workload:

```
### Current Workload (Snapshot Period)
| Metric | Value |
|--------|-------|
| Assigned Shifts | X |
| Total Hours | Xh |
| Open Applications | X |
| Absences | X |

### Assigned Shifts
| Date | Time | Type | Area |
|------|------|------|------|
| ... | ... | ... | ... |

### Pending Applications
| Date | Time | Type | Area |
|------|------|------|------|
| ... | ... | ... | ... |
```

If the employee has absences, list them with dates and type (Urlaub, Krank, etc.).

### Step 2: Cross-reference with latest plan (if one exists)

Call `list_plans(limit=1)`.

If a plan exists:

Call `plan_summary(plan_id)`.

Extract this employee's row from `hours_by_employee`. Calculate:
- Planned additional hours from the plan
- Total projected hours (snapshot assigned + plan assigned)
- Delta to target (if target is known from the profile)

```
### Plan Allocation
| Metric | Value |
|--------|-------|
| Plan Hours (additional) | Xh |
| Total Projected Hours | Xh |
| Target Hours | Xh |
| Delta to Target | +/-Xh |
```

### Step 3: Fairness context

If a plan exists, call `ask_plan(plan_question="How does [employee name] compare to other employees in hours and shift count?")`.

Summarize whether this employee is over- or under-allocated relative to peers.

### Step 4: Flag anomalies

Check for and explicitly flag any of these:
- **Over target** -- projected hours exceed target by more than 15%
- **Under target** -- projected hours are more than 15% below target
- **Near salary limit** -- projected monthly salary (hours * wage) exceeds 85% of max_salary
- **Salary limit breach** -- projected monthly salary exceeds max_salary
- **Absence conflicts** -- any planned shifts overlap with absence dates
- **High application count** -- employee has applied to many shifts but few were assigned (may indicate constraint blocks)
- **No shifts at all** -- employee has zero assigned shifts and zero plan assignments (may be inactive or fully blocked)

### Step 5: Commentary

End with a concise summary:
- "[Name] is a [employment type] working [X]h this period against a [T]h target ([delta])."
- Flag the most important anomaly if any exist
- If under-allocated: "Consider assigning more shifts or checking if constraint profile rules are too restrictive."
- If over-allocated: "Close to limits -- avoid additional assignments."
- If salary limit is near: "At [X]% of max salary ([amount]/[max]) -- Minijob limit risk."

## Reference Documents

Before flagging anomalies or explaining allocation, read:

- **Constraints**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/constraints.md`
- **Algorithm**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/algorithm.md`

## Output Format

All output in chat as formatted markdown. Focus on actionable insights, not raw data dumps.
