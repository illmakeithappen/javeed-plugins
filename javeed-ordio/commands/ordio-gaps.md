---
description: Analyze coverage gaps and recommend staffing outreach
allowed-tools: Read
argument-hint: [start] [end]
---

# Ordio Coverage Gap Analysis

Identify open shifts with insufficient or zero applicants, cross-reference with available employees, and produce targeted staffing recommendations.

## Usage

`/ordio-gaps [start] [end]`

- **start** -- ISO date, narrow the analysis range. Default: snapshot range start.
- **end** -- ISO date. Default: snapshot range end.

## Instructions

Follow these steps in order. Do NOT skip steps or combine them.

### Step 1: Check for snapshot

Call `list_snapshots(limit=1)`.

If no snapshot exists, tell the user to run `/ordio-weekly` first. Do not proceed without a snapshot.

If `start`/`end` are not provided, use the snapshot's date range.

### Step 2: Get open shifts

Call `get_open_shifts(snapshot_id, range_from=start, range_to=end)`.

Categorize each shift by severity:
- **Critical** -- zero applicants
- **Fragile** -- exactly 1 applicant
- **Healthy** -- 2 or more applicants

Present the severity summary:

```
## Coverage Gap Analysis ([start] -- [end])

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | X | No applicants -- needs manual intervention |
| Fragile | X | Single applicant -- at risk if blocked |
| Healthy | X | Multiple applicants -- covered |
```

### Step 3: Get applications

Call `get_applications(snapshot_id, range_from=start, range_to=end)`.

Build two views:

**Application concentration** -- which shifts are over-applied vs under-applied:
```
### Application Distribution
| Date | Time | Type | Area | Applicants |
|------|------|------|------|------------|
| ... (sorted by applicant count, ascending) |
```

**Employee flexibility** -- which employees applied to the most shifts:
```
### Most Flexible Employees
| Employee | Applications | Shifts Applied To |
|----------|-------------|-------------------|
| ... | ... | ... |
```

### Step 4: Analyze critical gaps

For each critical gap (zero applicants), present:

```
### Critical Gaps (Zero Applicants)

#### [Date] [Time] -- [Shift Type] ([Area])
- **Day:** [weekday]
- **Duration:** [hours]h
- **Why it's uncovered:** No employee applied for this slot
- **Potential candidates:** [see below]
```

To identify potential candidates for each critical gap, reason about:
- Employees who applied for other shifts on the same day or adjacent days (they're available and willing to work)
- Employees who have matching shift type affinity based on their role
- Employees who are below their target hours

Do NOT call additional tools for this -- use the data already retrieved from open shifts and applications to cross-reference.

### Step 5: Analyze fragile shifts

For each fragile shift (1 applicant):

```
### Fragile Shifts (Single Applicant)

| Date | Time | Type | Applicant | Risk |
|------|------|------|-----------|------|
| ... | ... | ... | [name] | [see below] |
```

Note the risk: if that single applicant is blocked by constraints, the shift becomes unfillable.

### Step 6: Commentary and recommendations

End with an actionable summary:

```
### Recommendations

**Immediate actions:**
- [X] critical gaps need manual outreach. Priority targets:
  - [Date] [Time]: Reach out to [Employee A], [Employee B]
  - [Date] [Time]: Reach out to [Employee C]

**Systemic observations:**
- [Pattern, e.g. "All critical gaps are Spaet shifts"]
- [Pattern, e.g. "Tuesday and Friday consistently have zero applicants"]

**Next steps:**
- Run `/ordio-plan` to see how the allocator handles these gaps
- Consider adjusting constraint profiles if gaps are caused by blocking rules
```

## Reference Documents

Before analyzing gaps and explaining why candidates may be blocked, read:

- **Constraints**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/constraints.md`
- **Algorithm**: `Read ${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/algorithm.md`

## Output Format

All output in chat as formatted markdown. Lead with the severity summary, then drill into critical gaps with specific outreach recommendations. The goal is to give the user a concrete action list, not just data.
