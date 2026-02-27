---
name: ordio-data
description: >
  Use when the user asks about syncing Ordio data, snapshots, the Ordio data model,
  employee records, shift structures, applications, absences, branches,
  or needs to understand what data is available in the system.
version: 1.0.0
---

# Ordio Data Layer

This skill covers the Ordio workforce management data model and how to sync, load, and navigate snapshot data using the javeed-ordio MCP tools.

## MCP Tools Available

| Tool | Purpose |
|------|---------|
| `sync_snapshot(betrieb, start, end)` | Fetch fresh data from Ordio API |
| `list_snapshots(limit)` | Browse local snapshots |
| `load_snapshot(snapshot_id)` | Load full snapshot JSON |
| `list_plans(limit)` | Browse local plan artifacts |
| `load_plan(plan_id)` | Load full plan JSON |
| `save_plan(plan_json)` | Persist a plan artifact |
| `list_profiles()` | List constraint profiles |
| `load_profile(profile_name)` | Load full profile JSON |

## Ordio Data Model

The Ordio API is the source of truth for Javeed's gastro venues. It stores:

- **Employees** -- staff records with role, employment type, wages, skills
- **Shifts** -- scheduled time slots with candidates and working areas
- **Applications** -- employee applications for open shifts
- **Absences** -- sick leave, vacation, free days
- **Branches** -- venue locations with working areas

## Snapshot Structure

A snapshot is a normalized point-in-time capture of Ordio data for a specific betrieb (location) and date range. Snapshots are local, read-only artifacts.

```json
{
  "snapshot_id": "hinweg-2026-03-03-2026-03-09-a1b2c3d4",
  "betrieb": "hinweg",
  "range": {"from": "2026-03-03", "to": "2026-03-09"},
  "employees": [...],
  "assigned_shifts": [...],
  "open_shifts": [...],
  "applications": [...],
  "absences": [...],
  "metadata": {"counts": {...}}
}
```

### Key Fields

**Employee record:**
- `ordio_employee_id`, `full_name`, `name_key` (canonical, lowercase)
- `role` (e.g., "Service", "Koch", "Bar")
- `employment` (e.g., "Minijob", "Werkstudent", "Teilzeit")
- `hourly_wage`, `max_salary`, `max_salary_type`
- `skills` (working area qualifications)

**Open shift slot:**
- `slot_id`, `ordio_shift_id`
- `date`, `start`, `end`, `shift_type`, `working_area`
- `applicant_employee_ids` (who applied for this slot)

**Application:**
- `ordio_employee_id`, `employee_name`
- `date`, `start`, `end`, `shift_type`

**Assigned shift:**
- Same as open shift plus `ordio_employee_id`, `employee_name`, `hours`

## Shift Type Inference

| Type | Rule |
|------|------|
| `theke` | Working area/note contains "theke" |
| `bar` | Working area/note contains "bar" |
| `kueche` | Working area/note contains "kueche"/"kuche" |
| `frueh` | Start before 11:00 |
| `spaet` | Start >= 16:00 or end >= 22:00 |
| `doppel` | Start <= 11:00 and end >= 20:00 |
| `normal` | Default fallback |

## Betriebe (Locations)

Javeed operates three venues:
- **Hin&Weg** (`hinweg`) -- cafe/restaurant
- **Bacchus** (`bacchus`) -- bar/restaurant
- **Rosa** (`rosa`) -- cafe

Each has its own Ordio API credentials (env vars: `ORDIO_API_KEY_{BETRIEB}`, `ORDIO_COMPANY_ID_{BETRIEB}`).

## Key Terminology

| German | English | Context |
|--------|---------|---------|
| Betrieb | Location/business | e.g., Hin&Weg, Bacchus |
| Schicht | Shift | A time slot to be filled |
| Werkstudent (Werki) | Working student | 20h/week cap |
| Minijobber (Mini) | Mini-job employee | ~43h/month, salary capped |
| Frueh/Spaet/Normal | Early/Late/Normal | Shift type categories |

## Read-Only Boundary

The plugin never writes back to Ordio. Snapshots and plans are local artifacts. After review, confirmed assignments are entered manually in Ordio by the Betriebsleiter.
