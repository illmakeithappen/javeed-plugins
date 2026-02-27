"""Read a CSV input directory into the dict format that generate_plan() expects."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from allocation_core.time_utils import calc_shift_hours

from .schemas import pipe_split, to_float


def load_input(directory: Path) -> tuple[dict, dict, dict]:
    """Read CSV input dir -> (snapshot_dict, profile_dict, meta_dict).

    Raises FileNotFoundError if required files are missing.
    """
    d = Path(directory)

    # -- meta.json & profile.json -----------------------------------------------
    meta_dict = _read_json(d / "meta.json")
    profile_dict = _read_json(d / "profile.json")

    # -- employees.csv ----------------------------------------------------------
    employees_raw = _read_csv(d / "employees.csv")
    employees = []
    emp_name_lookup: dict[str, str] = {}  # employee_id -> full name
    for row in employees_raw:
        full_name = row["name"]
        first_name, last_name = _split_name(full_name)
        emp_id = row["employee_id"]
        emp_name_lookup[emp_id] = full_name
        employees.append(
            {
                "ordio_employee_id": emp_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "name_key": full_name.lower(),
                "role": row["role"],
                "employment": row["employment"],
                "hourly_wage": to_float(row.get("hourly_wage")),
                "max_salary": to_float(row.get("max_salary")),
                "skills": pipe_split(row.get("skills")),
                "username": "",
                "email": "",
                "phone": "",
                "birthday": "",
                "max_salary_type": "money_total_salary",
                "enabled": True,
                "employee_status": "active",
            }
        )

    # -- shifts.csv (assigned shifts) -------------------------------------------
    shifts_raw = _read_csv(d / "shifts.csv")
    assigned_shifts = []
    for row in shifts_raw:
        emp_id = row["employee_id"]
        start = row["start"]
        end = row["end"]
        assigned_shifts.append(
            {
                "ordio_employee_id": emp_id,
                "date": row["date"],
                "start": start,
                "end": end,
                "hours": calc_shift_hours(start, end),
                "ordio_shift_id": "",
                "ordio_candidate_id": "",
                "shift_type": "",
                "working_area": "",
                "note": "",
                "status": 0,
                "employee_name": emp_name_lookup.get(emp_id, ""),
            }
        )

    # -- open_slots.csv ---------------------------------------------------------
    open_slots_raw = _read_csv(d / "open_slots.csv")
    open_shifts = []
    for row in open_slots_raw:
        start = row["start"]
        end = row["end"]
        open_shifts.append(
            {
                "slot_id": row["slot_id"],
                "date": row["date"],
                "start": start,
                "end": end,
                "hours": calc_shift_hours(start, end),
                "shift_type": row["shift_type"],
                "working_area": row["area"],
                "applicant_employee_ids": pipe_split(row.get("applicants")),
                "ordio_shift_id": "",
                "note": "",
                "required_employee_count": 1,
                "assigned_employee_count": 0,
            }
        )

    # -- absences.csv -----------------------------------------------------------
    absences_raw = _read_csv(d / "absences.csv")
    absences = []
    for row in absences_raw:
        emp_id = row["employee_id"]
        absences.append(
            {
                "ordio_employee_id": emp_id,
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "employee_name": emp_name_lookup.get(emp_id, ""),
                "type": "",
                "note": "",
            }
        )

    # -- assemble snapshot dict -------------------------------------------------
    snapshot_dict = {
        "snapshot_id": meta_dict["snapshot_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "betrieb": meta_dict["betrieb"],
        "range": {
            "from": meta_dict["range_from"],
            "to": meta_dict["range_to"],
        },
        "employees": employees,
        "assigned_shifts": assigned_shifts,
        "open_shifts": open_shifts,
        "absences": absences,
        "applications": [],
        "metadata": {
            "counts": {
                "employees": len(employees),
                "assigned_shifts": len(assigned_shifts),
                "open_shift_slots": len(open_shifts),
                "applications": 0,
                "absences": len(absences),
            }
        },
    }

    # -- tag existing profile rules as "ordio" if no _rule_sources present ------
    if "_rule_sources" not in profile_dict:
        rule_sources = {
            name: {field: "ordio" for field in rules}
            for name, rules in profile_dict.get("employee_rules", {}).items()
        }
        profile_dict["_rule_sources"] = rule_sources

    return snapshot_dict, profile_dict, meta_dict


def load_golden(directory: Path) -> list[dict[str, str]] | None:
    """Load golden_assignments.csv if present. Returns None if not found."""
    path = Path(directory) / "golden_assignments.csv"
    if not path.exists():
        return None
    return _read_csv(path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict:
    """Read and parse a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file into a list of dicts via csv.DictReader."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _split_name(full_name: str) -> tuple[str, str]:
    """Split a full name into (first_name, last_name)."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]
