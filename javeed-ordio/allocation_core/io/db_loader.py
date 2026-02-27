"""Persist a plan to the backend SQLite eval_runs / eval_assignments tables."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def persist_to_db(plan: dict[str, Any], db_path: Path) -> int:
    """Write a plan to eval_runs + eval_assignments and return the run_id.

    This uses the same schema as the backend eval pipeline, so results
    are visible in the admin dashboard.

    Args:
        plan: Output of generate_plan().
        db_path: Path to SQLite database file.

    Returns:
        The eval_runs.id of the created run.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()

        metrics = plan.get("metrics", {})
        kind_counts = metrics.get("assignment_kind_counts", {})

        # Insert eval_run
        cur.execute(
            """
            INSERT INTO eval_runs (
                betrieb, von, bis, use_ai, ai_model,
                total_open_slots, total_assigned, total_candidates
            ) VALUES (?, ?, ?, 0, 'csv_pipeline', ?, ?, 0)
            """,
            (
                plan.get("betrieb", ""),
                plan.get("range", {}).get("from", ""),
                plan.get("range", {}).get("to", ""),
                metrics.get("total_slots", 0),
                metrics.get("assigned_slots", 0),
            ),
        )
        run_id = cur.lastrowid

        # Insert eval_assignments for each assignment
        for rank, a in enumerate(plan.get("assignments", []), 1):
            sd = a.get("score_detail", {})
            blocked_reasons = a.get("blocked_reasons", [])

            cur.execute(
                """
                INSERT INTO eval_assignments (
                    run_id, slot_id, slot_datum, slot_schicht_typ,
                    slot_beginn, slot_ende,
                    mitarbeiter_id, vorname, nachname, rolle,
                    rang, selected, score,
                    score_reststunden, score_fairness, score_rolle,
                    score_verfuegbarkeit, score_feste_schicht, score_praeferenz,
                    score_skill, score_salary, score_intent,
                    is_intent, rest_stunden, haben_stunden,
                    week_shifts, reason_deterministic,
                    blocked, arbzg_violations
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, 1, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, 0,
                    ?, ?, ?,
                    ?, ?,
                    0, ?
                )
                """,
                (
                    run_id,
                    a.get("slot_id", ""),
                    a.get("date", ""),
                    a.get("shift_type", ""),
                    a.get("start", ""),
                    a.get("end", ""),
                    0,  # mitarbeiter_id — CSV pipeline doesn't have DB IDs
                    _first_name(a.get("employee_name", "")),
                    _last_name(a.get("employee_name", "")),
                    "",  # rolle
                    rank,
                    a.get("score", 0),
                    sd.get("rest", 0),
                    sd.get("fairness", 0),
                    sd.get("role", 0),
                    0,  # score_verfuegbarkeit (not used in CSV pipeline)
                    sd.get("fixed", 0),
                    sd.get("preference", 0),
                    sd.get("skill", 0),
                    sd.get("salary", 0),
                    1 if a.get("is_applicant") else 0,
                    a.get("target_hours") or 0,
                    a.get("run_month_hours_before", 0),
                    a.get("week_shifts", 0),
                    "|".join(a.get("reasons", [])),
                    json.dumps(blocked_reasons) if blocked_reasons else "[]",
                ),
            )

        conn.commit()
        return run_id

    finally:
        conn.close()


def _first_name(full_name: str) -> str:
    parts = full_name.strip().split(None, 1)
    return parts[0] if parts else ""


def _last_name(full_name: str) -> str:
    parts = full_name.strip().split(None, 1)
    return parts[1] if len(parts) > 1 else ""
