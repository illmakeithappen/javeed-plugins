---
name: ordio-profiles
description: >
  Use when the user asks about constraint profiles, employee rules, Vorgaben,
  input ingestion, profile building, target hours, max hours, salary limits,
  preferences, or how to customize allocation parameters for a venue or employee.
version: 1.0.0
---

# Ordio Profiles & Input Ingestion

This skill covers constraint profiles (per-employee rules that control allocation), input ingestion (CSV/snapshot extraction), and how to build profiles from Vorgaben (staffing requirements).

## Loading Profiles via MCP

```
list_profiles()       # See available profiles
load_profile(name)    # Get full profile JSON
```

## Profile JSON Structure

```json
{
  "policy": {
    "prefer_applicants": true,
    "max_consecutive_days": 5
  },
  "employee_rules": {
    "Annika Geyer": {
      "target_weekly_hours": 8,
      "preferred_working_areas": ["Kiosk"]
    },
    "Elena Schroeder": {
      "no_additional_shifts": true
    }
  }
}
```

## Employee Rule Keys

| Key | Type | Effect |
|-----|------|--------|
| `target_weekly_hours` | float | Target hours/week; drives rest score, converted to monthly * 4.33 |
| `target_monthly_hours` | float | Direct monthly target; overrides weekly |
| `max_monthly_hours` | float | Hard monthly cap |
| `max_weekly_hours` | float | Hard weekly cap |
| `max_additional_monthly_hours` | float | Cap on hours added by plan run only |
| `no_additional_shifts` | bool | Hard block -- zero plan assignments |
| `disable_max_hours` | bool | Removes monthly hour cap entirely |
| `preferred_working_areas` | list[str] | Boosts skill score (+12) when area matches |
| `preferred_shift_types` | list[str] | Boosts preference score (+7.5) when type matches |
| `notes` | str | German free-text, parsed for structured preferences |

## Building Profiles from Vorgaben

The `allocation_core.io.directives` module can build profiles from:
1. A base constraint profile (from `config/constraint_profiles.json`)
2. A `vorgaben.txt` file (German free-text staffing requirements)
3. An employee list (from `employees.csv`)

```python
from allocation_core.io.directives import build_profile

profile = build_profile(
    profile_name="hinweg_march_2026",
    profiles_path=Path("config/constraint_profiles.json"),
    vorgaben_text="Annika: max 8h/Woche\nElena: keine Zusatzschichten",
    employee_names=["Annika Geyer", "Elena Schroeder", ...],
)
```

## Extracting CSV Inputs from Snapshots

For evaluation or external processing, extract snapshot data to CSV:

```python
from allocation_core.io.extractors import extract_from_snapshot

paths = extract_from_snapshot(
    snapshot,           # dict from load_snapshot MCP tool
    profile,            # dict from load_profile MCP tool
    profile_name="hinweg_march_2026",
    directory=Path("eval_input/"),
)
# Creates: employees.csv, open_shifts.csv, applications.csv, profile.json, meta.json
```

## Loading CSV Inputs for Allocation

```python
from allocation_core.io.reader import load_input

snapshot, profile, meta = load_input(Path("eval_input/"))
# snapshot: normalized dict ready for run_mechanism()
# profile: constraint profile dict
# meta: {"betrieb": "...", "range_from": "...", "range_to": "..."}
```

## Built-in Profiles

| Name | Betrieb | Employees | Notes |
|------|---------|-----------|-------|
| `default` | Any | 0 rules | Generic fair distribution |
| `bacchus_march_2026` | Bacchus | 10 rules | Venue-specific for March 2026 |
| `hinweg_march_2026` | Hin&Weg | 14 rules | Venue-specific for March 2026 |

For full profile details: `references/constraint-profiles.md`
