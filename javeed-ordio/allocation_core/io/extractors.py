"""Extract CSV input files from existing data sources (plugin snapshot, backend DB)."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import (
    ABSENCES_COLS,
    EMPLOYEES_COLS,
    OPEN_SLOTS_COLS,
    SHIFTS_COLS,
    pipe_join,
)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def extract_from_snapshot(
    snapshot: dict[str, Any],
    profile: dict[str, Any],
    *,
    profile_name: str,
    directory: Path,
) -> dict[str, Path]:
    """Write a plugin snapshot dict + profile to CSV input format.

    Returns dict mapping filename to written path.
    """
    directory.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    # meta.json
    meta = {
        "snapshot_id": snapshot.get("snapshot_id", ""),
        "betrieb": snapshot.get("betrieb", ""),
        "range_from": snapshot.get("range", {}).get("from", ""),
        "range_to": snapshot.get("range", {}).get("to", ""),
    }
    meta_path = directory / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    result["meta.json"] = meta_path

    # employees.csv
    emp_rows = []
    for emp in snapshot.get("employees", []):
        emp_rows.append({
            "employee_id": emp.get("ordio_employee_id", ""),
            "name": emp.get("full_name", ""),
            "role": emp.get("role", ""),
            "employment": emp.get("employment", ""),
            "hourly_wage": emp.get("hourly_wage", 0),
            "max_salary": emp.get("max_salary", 0),
            "skills": pipe_join(emp.get("skills", [])),
        })
    result["employees.csv"] = _write_csv(directory / "employees.csv", EMPLOYEES_COLS, emp_rows)

    # shifts.csv (assigned shifts only)
    shift_rows = []
    for s in snapshot.get("assigned_shifts", []):
        shift_rows.append({
            "employee_id": s.get("ordio_employee_id", ""),
            "date": s.get("date", ""),
            "start": s.get("start", ""),
            "end": s.get("end", ""),
        })
    result["shifts.csv"] = _write_csv(directory / "shifts.csv", SHIFTS_COLS, shift_rows)

    # open_slots.csv
    slot_rows = []
    for s in snapshot.get("open_shifts", []):
        slot_rows.append({
            "slot_id": s.get("slot_id", ""),
            "date": s.get("date", ""),
            "start": s.get("start", ""),
            "end": s.get("end", ""),
            "shift_type": s.get("shift_type", ""),
            "area": s.get("working_area", ""),
            "applicants": pipe_join(s.get("applicant_employee_ids", [])),
        })
    result["open_slots.csv"] = _write_csv(directory / "open_slots.csv", OPEN_SLOTS_COLS, slot_rows)

    # absences.csv
    abs_rows = []
    for a in snapshot.get("absences", []):
        abs_rows.append({
            "employee_id": a.get("ordio_employee_id", ""),
            "start_date": a.get("start_date", ""),
            "end_date": a.get("end_date", ""),
        })
    result["absences.csv"] = _write_csv(directory / "absences.csv", ABSENCES_COLS, abs_rows)

    return result


def extract_from_db(
    *,
    betrieb: str,
    von: str,
    bis: str,
    db_path: Path | None = None,
    directory: Path,
) -> dict[str, Path]:
    """Query backend SQLite DB and write CSV input format.

    Args:
        betrieb: Branch identifier (e.g. "bacchus")
        von: Start date ISO string (YYYY-MM-DD)
        bis: End date ISO string (YYYY-MM-DD)
        db_path: Path to SQLite database. Defaults to api/db/database.db relative to project root.
        directory: Output directory for CSV files.
    """
    if db_path is None:
        db_path = Path(__file__).resolve().parents[2] / "api" / "db" / "database.db"

    directory.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # ---- meta.json ----
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        meta = {
            "snapshot_id": f"{betrieb}-{von}-{bis}-db",
            "betrieb": betrieb,
            "range_from": von,
            "range_to": bis,
        }
        meta_path = directory / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        result["meta.json"] = meta_path

        # ---- employees.csv ----
        cur.execute(
            """
            SELECT m.id, m.vorname, m.nachname, m.rolle, m.vertragsart,
                   m.stundenlohn, m.max_gehalt
            FROM mitarbeiter m
            WHERE m.betrieb = ? AND m.aktiv = 1 AND m.ai_ausgeschlossen = 0
            """,
            (betrieb,),
        )
        employees = cur.fetchall()
        emp_id_map: dict[int, str] = {}  # DB id -> employee_id string

        emp_rows = []
        for emp in employees:
            eid = f"DB-{emp['id']}"
            emp_id_map[emp["id"]] = eid

            # Fetch skills
            cur.execute(
                "SELECT skill_name FROM mitarbeiter_skills WHERE mitarbeiter_id = ?",
                (emp["id"],),
            )
            skills = [row["skill_name"] for row in cur.fetchall()]

            emp_rows.append({
                "employee_id": eid,
                "name": f"{emp['vorname']} {emp['nachname']}",
                "role": emp["rolle"] or "",
                "employment": emp["vertragsart"] or "",
                "hourly_wage": emp["stundenlohn"] or 0,
                "max_salary": emp["max_gehalt"] or 0,
                "skills": pipe_join(skills),
            })
        result["employees.csv"] = _write_csv(directory / "employees.csv", EMPLOYEES_COLS, emp_rows)

        # ---- shifts.csv (assigned shifts in range) ----
        cur.execute(
            """
            SELECT s.mitarbeiter_id, s.datum, s.beginn, s.ende
            FROM schichten s
            WHERE s.betrieb = ? AND s.datum >= ? AND s.datum <= ?
              AND s.mitarbeiter_id IS NOT NULL
            """,
            (betrieb, von, bis),
        )
        shift_rows = []
        for row in cur.fetchall():
            mid = row["mitarbeiter_id"]
            if mid not in emp_id_map:
                continue
            shift_rows.append({
                "employee_id": emp_id_map[mid],
                "date": row["datum"],
                "start": row["beginn"],
                "end": row["ende"],
            })
        result["shifts.csv"] = _write_csv(directory / "shifts.csv", SHIFTS_COLS, shift_rows)

        # ---- open_slots.csv (unassigned shifts in range) ----
        cur.execute(
            """
            SELECT s.id, s.datum, s.beginn, s.ende, s.typ, s.arbeitsbereich
            FROM schichten s
            WHERE s.betrieb = ? AND s.datum >= ? AND s.datum <= ?
              AND s.mitarbeiter_id IS NULL
            """,
            (betrieb, von, bis),
        )
        open_shifts = cur.fetchall()

        slot_rows = []
        for s in open_shifts:
            # Fetch applicants for this shift
            cur.execute(
                "SELECT mitarbeiter_id FROM bewerbungen WHERE schicht_id = ?",
                (s["id"],),
            )
            applicant_ids = [
                emp_id_map[r["mitarbeiter_id"]]
                for r in cur.fetchall()
                if r["mitarbeiter_id"] in emp_id_map
            ]

            slot_rows.append({
                "slot_id": f"{betrieb}-{s['id']}",
                "date": s["datum"],
                "start": s["beginn"],
                "end": s["ende"],
                "shift_type": s["typ"] or "",
                "area": s["arbeitsbereich"] or "",
                "applicants": pipe_join(applicant_ids),
            })
        result["open_slots.csv"] = _write_csv(directory / "open_slots.csv", OPEN_SLOTS_COLS, slot_rows)

        # ---- absences.csv ----
        cur.execute(
            """
            SELECT mitarbeiter_id, von_datum, bis_datum
            FROM abwesenheiten
            WHERE betrieb = ?
              AND bis_datum >= ? AND von_datum <= ?
            """,
            (betrieb, von, bis),
        )
        abs_rows = []
        for row in cur.fetchall():
            mid = row["mitarbeiter_id"]
            if mid not in emp_id_map:
                continue
            abs_rows.append({
                "employee_id": emp_id_map[mid],
                "start_date": row["von_datum"],
                "end_date": row["bis_datum"],
            })
        result["absences.csv"] = _write_csv(directory / "absences.csv", ABSENCES_COLS, abs_rows)

    finally:
        conn.close()

    return result
