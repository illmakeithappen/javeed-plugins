# Ordio-Lite Constraint Reference

## Overview

The allocator enforces two layers of constraints:

- **Hard blockers**: if any apply, the candidate is excluded (score = 0, never assigned)
- **Soft modifiers**: score adjustments that make a candidate more or less likely

All hard blockers are checked before scoring. A single violation is enough to block.

---

## Hard Blockers

| # | Constraint | Code Key | Source | Threshold | Example |
|---|-----------|----------|--------|-----------|---------|
| 1 | No additional shifts | `no_additional_shifts` | Profile | Flag set in employee rule | Elena, Luise: fully staffed, no extra shifts |
| 2 | Absence | `absence` | Ordio data | Absence record covers slot date | Sick leave Feb 23-25 blocks all slots in range |
| 3 | Same-day shift | `already_has_shift_same_day` | Business rule | Employee already has any shift that day | Assigned to 06:45-14:45, blocked for 15:00-22:30 same day |
| 4 | Time overlap | `overlap_same_day` | ArbZG | Shift times physically overlap | 10:00-16:00 overlaps with 14:00-22:30 |
| 5 | Daily 10h limit | `daily_hours_gt_10` | ArbZG 3 | Sum of shift hours on one day > 10h | 8h existing + 3h new = 11h -> blocked |
| 6 | Weekly hours limit | `weekly_hours_limit` | ArbZG / Contract | 48h default, 20h Werkstudent | 45h existing + 7.5h new = 52.5h -> blocked |
| 7 | 11h rest period | `rest_lt_11h` | ArbZG 5 | < 11h gap between adjacent-day shifts | Shift ends 22:30, next day starts 06:45 = 8h15m rest -> blocked |
| 8 | Consecutive days | `consecutive_days_limit` | ArbZG / Policy | Default 5 consecutive working days | Working Mon-Fri, Sat slot = 6th day -> blocked |
| 9 | Monthly hours cap | `monthly_hours_limit` | Contract | 43h Mini, 87h Werki, custom | Minijobber at 41h + 3h slot = 44h -> blocked |
| 10 | Additional monthly hours | `max_additional_monthly_hours` | Profile | Custom cap on plan-run hours only | Jonas: max 8h extra, already at 7h, 3h slot -> blocked |
| 11 | Weekly hours (profile) | `max_weekly_hours` | Profile | Custom weekly limit | Jana: max 8h/week, at 6h + 3h slot -> blocked |
| 12 | Salary limit | `max_salary_limit` | Contract | Projected salary > max_salary | 44h * 12.82/h = 564 > 556 max -> blocked |
| 13 | No weekend | `no_weekend` | Preference | Slot is on Sat/Sun, employee note says "kein Wochenende" | Saturday shift for employee with weekend exclusion |
| 14 | Only weekend | `only_weekend` | Preference | Slot is Mon-Fri, employee note says "nur Wochenende" | Wednesday shift for weekend-only employee |
| 15 | Too early | `starts_too_early` | Preference | Shift starts before "ab X Uhr" | "ab 15 Uhr" but shift starts at 10:00 |
| 16 | Too late | `ends_too_late` | Preference | Shift ends after "bis X Uhr" | "bis 20 Uhr" but shift ends at 22:30 |

---

## Monthly Hour Cap Decision Tree

The monthly cap determines when `monthly_hours_limit` triggers. It depends on the employee's profile rule and employment type.

```
  Employee e, Profile rule r
  |
  +-- r.disable_max_hours = true?
  |     \-- NO CAP (e.g., Felix: unlimited)
  |
  +-- r.max_monthly_hours set?
  |     \-- use that value (e.g., Luma: 40h, Maja: 40h)
  |
  +-- r.target_monthly_hours set?
  |     \-- use that value (e.g., Joelle: 40h, Julie: 40h)
  |
  +-- r.target_weekly_hours set?
  |     \-- weekly * 4.33 (e.g., Annika: 8 * 4.33 = 34.6h)
  |
  +-- employment type?
        |
        +-- Minijobber --> min(43, max_salary / hourly_wage)
        |
        +-- Werkstudent --> 20 * 4.33 = 86.6h
        |
        +-- Other --> max_salary / hourly_wage, or 160h fallback
```

---

## Weekly Hour Cap

```
  r.max_weekly_hours set?  --> use it (e.g., Jana: 8h)
  employment = Werkstudent? --> 20h
  default                   --> 48h (ArbZG)
```

---

## Soft Score Modifiers

These do not block candidates but adjust their ranking:

| Modifier | Effect | Motivation |
|----------|--------|------------|
| Applicant bonus (+80) | Strongly favors employees who applied | Respect employee initiative; self-selected availability |
| Rest / target hours (+0-40) | Favors employees with remaining capacity | Distribute hours toward targets; avoid underutilization |
| Fairness (+0-30) | Penalizes employees with many shifts this week | Prevent overloading; spread work across team |
| Role fit (+10 or +20) | Favors employees whose role matches shift type | Right person for the job (via ROLE_AFFINITY map) |
| Preference match (+7.5 or +15) | Favors employees whose preferred type matches | Honor stated shift-type preferences |
| Skill match (+12) | Favors employees with matching skills/areas | Assign to areas where employee is qualified |
| Fixed pattern (+12) | Favors employees with historical consistency | Stability for employees with regular schedules |
| Salary warning (-12) | Penalizes approaching salary cap | Early warning before hard block at 100% |

---

## Constraint Profiles

### Policy Flags

| Flag | Default | Description |
|------|---------|-------------|
| `prefer_applicants` | `true` | When a slot has applicants, restrict selection to applicant pool first |
| `distribute_applications_across_month` | `false` | Spread applicant assignments evenly (not yet fully implemented) |
| `max_consecutive_days` | `5` | Maximum consecutive working days before blocker triggers |
| `prefer_shift_type_variation` | `false` | Encourage different shift types across the week |

### Active Profiles

**default** -- Generic fair distribution. No employee-specific rules.

**hinweg_march_2026** -- Hin&Weg, March 2026:

| Employee | Rule | Value |
|----------|------|-------|
| Annika | target_weekly_hours | 8 |
| Besiane | target_weekly_hours | 10 |
| Ece | preferred_shift_types | mittel, normal |
| Elena | no_additional_shifts | true |
| Felix | preferred_shift_types + disable_max_hours | mittel, normal; no cap |
| Jana | max_weekly_hours | 8 |
| Joelle | target_monthly_hours | 40 |
| Jonas | max_additional_monthly_hours | 8 |
| Julie | target_monthly_hours | 40 |
| Luise | no_additional_shifts | true |
| Luma | max_monthly_hours | 40 |
| Maja | max_monthly_hours | 40 |
| Niklas | max_additional_monthly_hours | 6 |
| Raphael | max_monthly_hours | 40 |

**bacchus_march_2026** -- Bacchus, March 2026:

| Employee | Rule | Value |
|----------|------|-------|
| Bar | target_weekly_hours | 20 (reduced from 24, overtime) |
| Clara | target_weekly_hours | 8 |
| David | target_weekly_hours | 20 |
| Lilia | target_weekly_hours | 10 |
| Matteo | target_weekly_hours + preferred_areas | 28; theke |
| Nele | target_weekly_hours | 10 |
| Nico | target_weekly_hours | 8 |
| Omer | target_weekly_hours + preferred_areas | 16 (reduced from 28); theke |
| Rosa | target_weekly_hours | 8 |
| Nell | target_weekly_hours | 8 |

---

## Employee Rule Keys

| Key | Type | Effect |
|-----|------|--------|
| `target_weekly_hours` | float | Target hours/week; used for rest score and monthly cap (*4.33) |
| `target_monthly_hours` | float | Target hours/month; overrides weekly-based calculation |
| `max_monthly_hours` | float | Hard monthly cap; blocks if exceeded |
| `max_weekly_hours` | float | Hard weekly cap; blocks if exceeded |
| `max_additional_monthly_hours` | float | Cap on hours added by this plan run only |
| `no_additional_shifts` | bool | Blocks all assignments |
| `disable_max_hours` | bool | Removes monthly hour cap entirely |
| `preferred_working_areas` | list[str] | Boosts skill score when slot area matches |
| `preferred_shift_types` | list[str] | Boosts preference score when shift type matches |
| `notes` | str | Free-text; parsed for German preference keywords |

---

## Preference Parsing

Employee notes (German free-text) are parsed into structured preferences:

| Pattern | Parsed As | Effect |
|---------|-----------|--------|
| "kein Wochenende" / "nicht Wochenende" | `no_weekend: true` | Blocks Sat/Sun slots |
| "nur Wochenende" | `only_weekend: true` | Blocks Mon-Fri slots |
| "lieber frueh" / "bevorzugt frueh" | `prefer: "frueh"` | +15 for frueh shifts |
| "lieber spaet" / "bevorzugt spaet" | `prefer: "spaet"` | +15 for spaet shifts |
| "max N Schichten" | `max_shifts_week: N` | (tracked, not yet blocking) |
| "ab X Uhr" | `earliest: X*60` | Blocks shifts starting before X:00 |
| "bis X Uhr" | `latest: X*60` | Blocks shifts ending after X:00 |
