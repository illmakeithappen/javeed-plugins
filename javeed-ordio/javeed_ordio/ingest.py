from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from .ordio_client import ACTIVE_CANDIDATE_STATUSES, CANDIDATE_APPLIED
from .utils import (
    BERLIN_TZ,
    calc_shift_hours,
    canonical_name,
    date_from_dt,
    full_name,
    hhmm_from_dt,
    infer_shift_type,
    now_utc_iso,
    parse_rfc2822,
)


@dataclass(frozen=True)
class SnapshotBuildInput:
    betrieb: str
    start_date: date
    end_date: date
    payload: dict[str, Any]


def _parse_dt_any(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        dt = parse_rfc2822(value)
        if dt is not None:
            return dt
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
    return None


def _active_wage(wages: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not wages:
        return None
    for item in wages:
        if item.get("active"):
            return item
    return wages[0]


def _build_working_area_map(branches: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for branch in branches:
        collections = []
        for key in ("branch_working_areas", "working_areas"):
            if isinstance(branch.get(key), list):
                collections.extend(branch[key])

        for item in collections:
            if not isinstance(item, dict):
                continue
            wa_id = item.get("id") or item.get("branch_working_area_id")
            name = None
            if isinstance(item.get("working_area"), dict):
                name = item["working_area"].get("name")
            if not name:
                name = item.get("name")
            if wa_id is not None and name:
                mapping[str(wa_id)] = str(name)
    return mapping


def _normalize_employees(
    employee_rows: list[dict[str, Any]],
    employments: dict[str, str],
    working_areas: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    employees: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    for raw in employee_rows:
        emp_id = raw.get("id")
        if emp_id is None:
            continue
        emp_key = str(emp_id)

        wage = _active_wage(raw.get("wages"))
        employment_name = ""
        if wage and isinstance(wage.get("employment"), dict):
            employment_name = str(wage["employment"].get("name") or "")
        if not employment_name:
            employment_name = str(employments.get(str(raw.get("employment") or ""), ""))

        skills: list[str] = []
        for bwa_id in raw.get("branch_working_area_ids", []) or []:
            name = working_areas.get(str(bwa_id))
            if name:
                skills.append(name)

        raw_skill = raw.get("employee_skill")
        if raw_skill:
            if isinstance(raw_skill, list):
                skills.extend(str(v) for v in raw_skill if v)
            else:
                skills.append(str(raw_skill))

        role_name = ""
        role_obj = raw.get("role")
        if isinstance(role_obj, dict):
            role_name = str(role_obj.get("name") or "")

        first_name = str(raw.get("first_name") or "")
        last_name = str(raw.get("second_name") or "")

        normalized = {
            "ordio_employee_id": emp_key,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name(first_name, last_name),
            "name_key": canonical_name(full_name(first_name, last_name)),
            "username": str(raw.get("username") or ""),
            "email": str(raw.get("email") or ""),
            "phone": str(raw.get("phone") or ""),
            "birthday": str(raw.get("birthday") or ""),
            "role": role_name,
            "employment": employment_name,
            "hourly_wage": float((wage or {}).get("wage") or 0),
            "max_salary": float((wage or {}).get("max_salary") or 0),
            "max_salary_type": str((wage or {}).get("max_salary_type") or ""),
            "enabled": bool(raw.get("enabled", True)),
            "employee_status": str(raw.get("employee_status") or ""),
            "skills": sorted({s for s in skills if s}),
        }
        by_id[emp_key] = normalized
        employees.append(normalized)

    return employees, by_id


def _ensure_candidate_employee(
    employee_by_id: dict[str, dict[str, Any]],
    emp_payload: dict[str, Any],
    *,
    fallback_wage: float = 0,
) -> None:
    eid = emp_payload.get("id")
    if eid is None:
        return
    eid_key = str(eid)
    if eid_key in employee_by_id:
        existing = employee_by_id[eid_key]
        if not existing.get("email") and emp_payload.get("email"):
            existing["email"] = str(emp_payload.get("email"))
        return

    first_name = str(emp_payload.get("first_name") or "")
    last_name = str(emp_payload.get("second_name") or "")
    row = {
        "ordio_employee_id": eid_key,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name(first_name, last_name),
        "name_key": canonical_name(full_name(first_name, last_name)),
        "username": str(emp_payload.get("username") or ""),
        "email": str(emp_payload.get("email") or ""),
        "phone": str(emp_payload.get("phone") or ""),
        "birthday": "",
        "role": str((emp_payload.get("role") or {}).get("name") or ""),
        "employment": "",
        "hourly_wage": float(fallback_wage or 0),
        "max_salary": 0.0,
        "max_salary_type": "",
        "enabled": True,
        "employee_status": "",
        "skills": [],
    }
    employee_by_id[eid_key] = row


def build_snapshot(data: SnapshotBuildInput) -> dict[str, Any]:
    payload = data.payload
    working_area_map = _build_working_area_map(payload.get("branches", []))

    employees, employee_by_id = _normalize_employees(
        payload.get("employees", []),
        payload.get("employments", {}),
        working_area_map,
    )

    assigned_shifts: list[dict[str, Any]] = []
    open_shifts: list[dict[str, Any]] = []
    applications: list[dict[str, Any]] = []

    for raw_shift in payload.get("shifts", []):
        ordio_shift_id = str(raw_shift.get("id") or "")
        if not ordio_shift_id:
            continue

        start_dt = _parse_dt_any(raw_shift.get("start_tz"))
        end_dt = _parse_dt_any(raw_shift.get("end_tz"))

        if start_dt is None or end_dt is None:
            continue

        start_dt = start_dt.astimezone(BERLIN_TZ)
        end_dt = end_dt.astimezone(BERLIN_TZ)
        datum = date_from_dt(start_dt)
        beginn = hhmm_from_dt(start_dt)
        ende = hhmm_from_dt(end_dt)

        note = str(raw_shift.get("note") or "")
        working_area = str(
            ((raw_shift.get("branch_working_area") or {}).get("working_area") or {}).get("name")
            or ""
        )
        shift_type = infer_shift_type(beginn, ende, working_area, note)

        candidates = raw_shift.get("candidates") or []
        active_candidates: list[dict[str, Any]] = []
        applied_candidates: list[dict[str, Any]] = []

        for c in candidates:
            status = int(c.get("status") or 0)
            emp = c.get("employee") or {}
            fallback_wage = float(((c.get("price") or {}).get("hours_wage") or 0))
            _ensure_candidate_employee(employee_by_id, emp, fallback_wage=fallback_wage)

            emp_id = emp.get("id")
            if emp_id is None:
                continue
            emp_id_str = str(emp_id)

            entry = {
                "ordio_candidate_id": str(c.get("id") or ""),
                "ordio_employee_id": emp_id_str,
                "status": status,
                "working_time_minutes": int(c.get("working_time") or 0),
                "hourly_wage": float(((c.get("price") or {}).get("hours_wage") or 0)),
            }
            if status in ACTIVE_CANDIDATE_STATUSES:
                active_candidates.append(entry)
            if status == CANDIDATE_APPLIED:
                applied_candidates.append(entry)

        required_count = int(raw_shift.get("employee_count") or max(len(active_candidates), 1))
        required_count = max(required_count, len(active_candidates))
        open_count = max(required_count - len(active_candidates), 0)

        for c in active_candidates:
            emp = employee_by_id.get(c["ordio_employee_id"], {})
            assigned_shifts.append(
                {
                    "ordio_shift_id": ordio_shift_id,
                    "ordio_candidate_id": c["ordio_candidate_id"],
                    "ordio_employee_id": c["ordio_employee_id"],
                    "date": datum,
                    "start": beginn,
                    "end": ende,
                    "shift_type": shift_type,
                    "working_area": working_area,
                    "note": note,
                    "status": c["status"],
                    "hours": calc_shift_hours(beginn, ende),
                    "employee_name": full_name(emp.get("first_name", ""), emp.get("last_name", "")),
                }
            )

        applicant_ids = [c["ordio_employee_id"] for c in applied_candidates if c.get("ordio_employee_id")]
        for index in range(open_count):
            slot_id = f"{ordio_shift_id}-open-{index + 1}"
            open_shifts.append(
                {
                    "slot_id": slot_id,
                    "ordio_shift_id": ordio_shift_id,
                    "date": datum,
                    "start": beginn,
                    "end": ende,
                    "shift_type": shift_type,
                    "working_area": working_area,
                    "note": note,
                    "required_employee_count": required_count,
                    "assigned_employee_count": len(active_candidates),
                    "applicant_employee_ids": applicant_ids,
                }
            )

        for c in applied_candidates:
            emp = employee_by_id.get(c["ordio_employee_id"], {})
            applications.append(
                {
                    "ordio_candidate_id": c["ordio_candidate_id"],
                    "ordio_shift_id": ordio_shift_id,
                    "ordio_employee_id": c["ordio_employee_id"],
                    "employee_name": full_name(emp.get("first_name", ""), emp.get("last_name", "")),
                    "date": datum,
                    "start": beginn,
                    "end": ende,
                    "shift_type": shift_type,
                    "working_area": working_area,
                }
            )

    # Absence normalization.
    absences: list[dict[str, Any]] = []
    for raw in payload.get("absences", []):
        emp = raw.get("employee") or {}
        emp_id = raw.get("employee_id") or emp.get("id")
        if emp_id is None:
            continue
        emp_id_str = str(emp_id)
        _ensure_candidate_employee(employee_by_id, emp)

        start_value = raw.get("from_tz") or raw.get("startDate") or raw.get("start_date")
        end_value = raw.get("to_tz") or raw.get("endDate") or raw.get("end_date")
        start_dt = _parse_dt_any(start_value)
        end_dt = _parse_dt_any(end_value)
        if start_dt is None or end_dt is None:
            continue

        typ = str(((raw.get("absence_type") or {}).get("name") or raw.get("type") or "Frei"))
        absences.append(
            {
                "ordio_employee_id": emp_id_str,
                "employee_name": full_name(emp.get("first_name", ""), emp.get("second_name", "")),
                "start_date": date_from_dt(start_dt),
                "end_date": date_from_dt(end_dt),
                "type": typ,
                "note": str(raw.get("note") or ""),
            }
        )

    # Make sure the list reflects possible candidate-only users.
    employees = sorted(employee_by_id.values(), key=lambda row: row.get("full_name") or row.get("ordio_employee_id"))

    snapshot_id = f"{data.betrieb}-{data.start_date.isoformat()}-{data.end_date.isoformat()}-{uuid4().hex[:8]}"
    generated_at = now_utc_iso()
    return {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "betrieb": data.betrieb,
        "range": {
            "from": data.start_date.isoformat(),
            "to": data.end_date.isoformat(),
        },
        "employees": employees,
        "assigned_shifts": sorted(assigned_shifts, key=lambda s: (s["date"], s["start"], s["employee_name"])),
        "open_shifts": sorted(open_shifts, key=lambda s: (s["date"], s["start"], s["slot_id"])),
        "applications": sorted(applications, key=lambda a: (a["date"], a["start"], a["employee_name"])),
        "absences": sorted(absences, key=lambda a: (a["start_date"], a["employee_name"])),
        "metadata": {
            "counts": {
                "employees": len(employees),
                "assigned_shifts": len(assigned_shifts),
                "open_shift_slots": len(open_shifts),
                "applications": len(applications),
                "absences": len(absences),
            }
        },
    }
