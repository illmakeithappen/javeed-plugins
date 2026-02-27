"""Tests for CSV extraction (no profile.json)."""
import json
from pathlib import Path

from allocation_core.io.extractors import extract_from_snapshot

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "minimal"


def _load_minimal_snapshot():
    meta = json.loads((FIXTURES_DIR / "meta.json").read_text())
    # Build a snapshot dict matching the fixture data
    return {
        "snapshot_id": meta["snapshot_id"],
        "betrieb": meta["betrieb"],
        "range": {"from": meta["range_from"], "to": meta["range_to"]},
        "employees": [
            {"ordio_employee_id": "E-4012", "full_name": "Omer Yilmaz",
             "role": "service", "employment": "Minijob",
             "hourly_wage": 12.50, "max_salary": 538.00, "skills": ["theke", "bar"]},
        ],
        "assigned_shifts": [],
        "open_shifts": [],
        "absences": [],
    }


class TestExtractFromSnapshot:
    def test_does_not_produce_profile_json(self, tmp_path):
        snapshot = _load_minimal_snapshot()
        profile = {"description": "test", "policy": {}, "employee_rules": {}}
        result = extract_from_snapshot(snapshot, profile, profile_name="test", directory=tmp_path)
        assert "profile.json" not in result
        assert not (tmp_path / "profile.json").exists()

    def test_produces_csvs_and_meta(self, tmp_path):
        snapshot = _load_minimal_snapshot()
        profile = {"description": "test", "policy": {}, "employee_rules": {}}
        result = extract_from_snapshot(snapshot, profile, profile_name="test", directory=tmp_path)
        assert "meta.json" in result
        assert "employees.csv" in result
        assert "shifts.csv" in result
        assert "open_slots.csv" in result
        assert "absences.csv" in result
