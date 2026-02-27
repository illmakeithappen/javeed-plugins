---
description: Sync Ordio data, produce KPIs, and generate weekly reports
allowed-tools: Read, Write, Bash(open:*)
argument-hint: [betrieb] [start] [end]
---

# Ordio Weekly Overview

Sync the latest shift data from Ordio, produce KPIs, identify staffing pressure points, and generate an HTML report.

## Usage

`/ordio-weekly [betrieb] [start] [end]`

- **betrieb** -- Location identifier (e.g. `hinweg`, `bacchus`). If omitted, use the betrieb from the latest snapshot. If no snapshot exists, ask.
- **start** -- ISO date, start of range. Default: this Monday.
- **end** -- ISO date, end of range. Default: this Sunday.

## Instructions

Follow these steps in order. Do NOT skip steps or combine them.

### Step 1: Resolve defaults

- If `betrieb` is not provided, call `list_snapshots(limit=1)`. If a snapshot exists, use its betrieb. Otherwise ask the user.
- If `start`/`end` are not provided, calculate this week's Monday through Sunday from the current date.

### Step 2: Sync fresh data

Call `sync_snapshot(betrieb, start, end)`.

Report to the user:
- Betrieb and date range
- Employee count, assigned shift count, open slot count from the response

### Step 3: Get the summary

Call `snapshot_summary(snapshot_id)` using the snapshot_id from step 2.

Present a KPI block:

```
## This Week at [Betrieb]  ([start] -- [end])

| KPI | Value |
|-----|-------|
| Employees | X |
| Assigned Shifts | X |
| Open Slots | X |
| Applications | X |
| Coverage | X% |
```

Then highlight:
- Days with **zero applicants** for their open slots (staffing risk)
- Shift types with the most open slots
- Top 3 applicants by application count

### Step 4: Analyze open shifts

Call `get_open_shifts(snapshot_id)`.

Group open shifts by day and shift type. Identify clusters:
- "3 Spaet shifts uncovered on Saturday"
- "No applicants for any Friday shift"

Present a day-by-day table:

```
| Day | Open Slots | Applicants | Risk |
|-----|-----------|------------|------|
| Mon | 1 | 1 | OK |
| Tue | 1 | 0 | No applicants |
```

### Step 5: Generate reports

Call `snapshot_report(snapshot_id)` for the HTML report. Tell the user the file path and open it with `open <path>`.

Call `snapshot_report_md(snapshot_id)` for the Markdown report. Tell the user the file path.

### Step 6: Commentary

End with an opinionated summary:
- Lead with the most important finding (e.g. "5 of 8 open slots have zero applicants")
- Flag the riskiest days/shifts
- Suggest next action: "Run `/ordio-plan` to generate shift assignments" or "Run `/ordio-gaps` to analyze coverage gaps"

## Reference Documents

Before analyzing open shifts, read the constraint and algorithm reference for context on why shifts may be hard to fill:

- **Constraints**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/constraints.md`
- **Review Sheet**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/review-sheet.md`

## Output Format

All output should be in the chat as formatted markdown. Both an HTML report (with charts) and a Markdown report (portable, diffable) are generated as artifacts. The user should get the full picture from the chat text alone.
