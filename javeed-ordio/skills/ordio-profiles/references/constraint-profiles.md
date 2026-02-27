# Constraint Profiles Reference

Profiles are stored in `config/constraint_profiles.json`. Each profile contains a `policy` block (global settings) and an `employee_rules` block (per-employee overrides).

## Profile: default

Generic fair distribution with legal and contract limits.

**Policy:**
- `prefer_applicants`: true
- `distribute_applications_across_month`: false
- `max_consecutive_days`: 5

**Employee rules:** None. All employees are treated equally using their contract data from Ordio.

---

## Profile: hinweg_march_2026

Rules extracted from "Ordio-Vorgaben fuer Maerz 2026" (Hin&Weg).

**Policy:**
- `prefer_applicants`: true
- `distribute_applications_across_month`: true
- `max_consecutive_days`: 5
- `prefer_shift_type_variation`: true

**Employee Rules (14 employees):**

| Employee | Key | Value | Notes |
|----------|-----|-------|-------|
| Annika | `target_weekly_hours` | 8 | Low target, flexible schedule |
| Besiane | `target_weekly_hours` | 10 | |
| Ece | `preferred_shift_types` | ["mittel", "normal"] | Prefers mid-day shifts |
| Elena | `no_additional_shifts` | true | Fully staffed, no extra shifts |
| Felix | `preferred_shift_types` | ["mittel", "normal"] | Prefers mid-day shifts |
| Felix | `disable_max_hours` | true | No monthly cap |
| Jana | `max_weekly_hours` | 8 | Hard weekly cap |
| Joelle | `target_weekly_hours` | 9.2 | ~40h/month target |
| Jonas | `max_additional_monthly_hours` | 8 | Plan can add max 8h/month |
| Julie | `target_weekly_hours` | 9.2 | ~40h/month target |
| Luise | `no_additional_shifts` | true | Fully staffed, no extra shifts |
| Luma | `max_monthly_hours` | 40 | Hard monthly cap |
| Maja | `max_monthly_hours` | 40 | Hard monthly cap |
| Niklas | `max_additional_monthly_hours` | 6 | Plan can add max 6h/month |
| Raphael | `max_monthly_hours` | 40 | Hard monthly cap |

---

## Profile: bacchus_march_2026

Rules extracted from "Ordio-Vorgaben fuer Maerz 2026" (Bacchus).

**Policy:**
- `prefer_applicants`: true
- `distribute_applications_across_month`: true
- `max_consecutive_days`: 5

**Employee Rules (10 employees):**

| Employee | Key | Value | Notes |
|----------|-----|-------|-------|
| Bar | `target_weekly_hours` | 20 | Reduced from 24 due to overtime |
| Bar | `notes` | "March override due to overtime reduction (-4h)." | |
| Clara | `target_weekly_hours` | 8 | |
| David | `target_weekly_hours` | 20 | |
| Lilia | `target_weekly_hours` | 10 | |
| Matteo | `target_weekly_hours` | 28 | |
| Matteo | `preferred_working_areas` | ["theke"] | Theke specialist |
| Nele | `target_weekly_hours` | 10 | |
| Nico | `target_weekly_hours` | 8 | |
| Omer | `target_weekly_hours` | 16 | Reduced from 28 due to overtime |
| Omer | `preferred_working_areas` | ["theke"] | Theke specialist |
| Omer | `notes` | "March override due to overtime reduction (-12h)." | |
| Rosa | `target_weekly_hours` | 8 | |
| Nell | `target_weekly_hours` | 8 | |

---

## How Profile Rules Interact with Constraints

Profile rules feed into the allocator's constraint and scoring systems:

### Hard Constraints (blocking)
- `no_additional_shifts` -> blocker #1: zero assignments
- `max_monthly_hours` -> blocker #9: monthly cap
- `max_weekly_hours` -> blocker #11: weekly cap
- `max_additional_monthly_hours` -> blocker #10: plan-run-only cap

### Scoring (non-blocking)
- `target_weekly_hours` / `target_monthly_hours` -> rest score (0-40)
- `preferred_working_areas` -> skill score (+12)
- `preferred_shift_types` -> preference score (+7.5)
- `notes` -> parsed preferences (may trigger hard blocks like no_weekend)
- `disable_max_hours` -> removes monthly cap entirely

### Priority Cascade for Monthly Cap
1. `disable_max_hours: true` -> no cap
2. `max_monthly_hours` -> explicit cap
3. `target_monthly_hours` -> used as cap
4. `target_weekly_hours * 4.33` -> derived monthly cap
5. Employment type default (43h Mini, 86.6h Werki, 160h fallback)
