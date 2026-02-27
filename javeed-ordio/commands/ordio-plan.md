---
description: Generate allocation plan, review fairness, and produce reports
allowed-tools: Read, Write, Bash(open:*)
argument-hint: [start] [end] [profile]
---

# Ordio Allocation Plan

Generate a deterministic shift allocation plan, review fairness and fill rate, explain contested decisions, and produce an HTML report.

## Usage

`/ordio-plan [start] [end] [profile]`

- **start** -- ISO date, plan range start. Default: this Monday.
- **end** -- ISO date, plan range end. Default: this Sunday.
- **profile** -- Constraint profile name. Default: `default`. Use `list_profiles()` to see available profiles.

## Instructions

Follow these steps in order. Do NOT skip steps or combine them.

### Step 1: Check for a fresh snapshot

Call `list_snapshots(limit=1)`.

- If a snapshot exists and its date range covers the requested plan range, use it.
- If no snapshot exists or the range doesn't match, tell the user and call `sync_snapshot(betrieb, start, end)` using the betrieb from the existing snapshot. If no snapshot exists at all, ask the user for the betrieb.

### Step 2: Show available profiles

Call `list_profiles()`.

If `profile` was not provided, briefly list the available profiles with their descriptions. If there is a location-specific profile matching the snapshot's betrieb (e.g. `hinweg_march_2026` for betrieb `hinweg`), suggest it. Otherwise proceed with `default`.

If the user provided a profile, validate it exists. If not, show available options and ask.

### Step 3: Generate the plan

Call `generate_plan(range_from=start, range_to=end, profile_name=profile, snapshot_id=snapshot_id)`.

Report immediate metrics:
- Fill rate (assigned / total slots)
- Assigned count vs unassigned count

### Step 4: Review the plan

Call `plan_summary(plan_id)`.

Present detailed KPIs:

```
## Allocation Plan: [plan_id]
**Profile:** [profile] | **Range:** [start] -- [end] | **Fill Rate:** X%

### Assignment Breakdown
| Kind | Count |
|------|-------|
| Applicant (employee applied) | X |
| Recommendation (no applicants) | X |
| Recommendation (applicants blocked) | X |
| Unassigned | X |

### Hours by Employee
| Employee | Hours | Shifts | Delta to Target |
|----------|-------|--------|-----------------|
| ... | ... | ... | ... |
```

### Step 5: Identify concerns

Analyze the plan summary for concerning patterns:

1. **Fairness flags** -- employees with disproportionately high or low hours relative to their target (delta > 15%). Call these out explicitly.
2. **Unassigned slots** -- group by reason. If `all_candidates_blocked_by_constraints` is the top reason, suggest relaxing constraints or using a different profile.
3. **Contested decisions** -- assignments of type `recommendation_despite_applicants` (an applicant existed but was blocked). These need explanation.

### Step 6: Explain notable decisions

If there are assignments of type `recommendation_despite_applicants`, or if the fill rate is below 80%, pick up to 3 notable assignments and call `explain_plan_assignment(assignment_id, plan_id)` for each.

Present each explanation:
```
### Why [Employee] was assigned [Date] [Time]?
- **Score:** X points
- **Key reasons:** [list from reasons field]
- **Alternatives considered:**
  - [Alt employee]: blocked because [reasons]
  - [Alt employee]: score X (lower because [reason])
```

### Step 7: Generate reports

Call `plan_report(plan_id)` for the HTML report. Tell the user the file path and open it with `open <path>`.

Call `plan_report_md(plan_id)` for the Markdown report. Tell the user the file path.

### Step 8: Commentary and recommendations

End with an opinionated summary:
- Lead with fill rate and the most important fairness finding
- If unassigned slots remain, explain why and suggest concrete actions:
  - "Relax constraints for [employee] in the profile"
  - "Re-run with profile [X] which has looser limits"
  - "These slots need manual outreach -- run `/ordio-gaps` for recommendations"
- If fill rate >= 90%: note that the plan looks healthy
- If contested decisions exist: summarize whether the algorithm's choices seem reasonable
- Suggest: "Run `/ordio-compare` to test alternative profiles" if relevant

## Reference Documents

Before explaining decisions or scores, read these spec docs:

- **Algorithm**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/algorithm.md`
- **Constraints**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/constraints.md`
- **Review Sheet**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/review-sheet.md`

Use this context when explaining decisions. Translate score components into plain language (e.g. "Annika scored highest because she applied for this shift (+80) and is still below her weekly target (+35)"). Use German reasoning labels from the review sheet when presenting to the user.

## Output Format

All output should be in the chat as formatted markdown. Both an HTML report and a Markdown report are generated as artifacts. The user should get the full picture from the chat text alone.
