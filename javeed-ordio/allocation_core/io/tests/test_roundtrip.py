"""Roundtrip test: load_input -> generate_plan -> write_output -> verify."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from allocation_core.allocator import generate_plan
from allocation_core.io.reader import load_input
from allocation_core.io.writer import write_output

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "minimal"


@pytest.fixture
def minimal_input():
    """Load the minimal fixture as (snapshot, profile, meta)."""
    return load_input(FIXTURES_DIR)


@pytest.fixture
def plan(minimal_input):
    """Run generate_plan on the minimal fixture."""
    snapshot, profile, meta = minimal_input
    return generate_plan(
        snapshot,
        range_from=meta["range_from"],
        range_to=meta["range_to"],
        profile_name=profile.get("name", "test"),
        profile=profile,
    )


class TestLoadInput:
    def test_loads_employees(self, minimal_input):
        snapshot, _, _ = minimal_input
        assert len(snapshot["employees"]) == 3
        names = {e["full_name"] for e in snapshot["employees"]}
        assert "Omer Yilmaz" in names
        assert "Anna Meier" in names
        assert "Lukas Schmidt" in names

    def test_employee_fields(self, minimal_input):
        snapshot, _, _ = minimal_input
        omer = next(e for e in snapshot["employees"] if e["full_name"] == "Omer Yilmaz")
        assert omer["ordio_employee_id"] == "E-4012"
        assert omer["role"] == "service"
        assert omer["employment"] == "Minijob"
        assert omer["hourly_wage"] == 12.50
        assert omer["max_salary"] == 538.00
        assert omer["skills"] == ["theke", "bar"]

    def test_loads_shifts(self, minimal_input):
        snapshot, _, _ = minimal_input
        assert len(snapshot["assigned_shifts"]) == 2

    def test_shift_hours_computed(self, minimal_input):
        snapshot, _, _ = minimal_input
        shift = snapshot["assigned_shifts"][0]
        assert shift["hours"] == 6.0  # 09:00-15:00

    def test_loads_open_slots(self, minimal_input):
        snapshot, _, _ = minimal_input
        assert len(snapshot["open_shifts"]) == 3

    def test_open_slot_applicants(self, minimal_input):
        snapshot, _, _ = minimal_input
        slot = next(s for s in snapshot["open_shifts"] if s["slot_id"] == "bacchus-7801")
        assert set(slot["applicant_employee_ids"]) == {"E-4012", "E-4098"}

    def test_open_slot_no_applicants(self, minimal_input):
        snapshot, _, _ = minimal_input
        slot = next(s for s in snapshot["open_shifts"] if s["slot_id"] == "bacchus-7802")
        assert slot["applicant_employee_ids"] == []

    def test_loads_absences(self, minimal_input):
        snapshot, _, _ = minimal_input
        assert len(snapshot["absences"]) == 1
        assert snapshot["absences"][0]["ordio_employee_id"] == "E-5001"

    def test_loads_profile(self, minimal_input):
        _, profile, _ = minimal_input
        assert profile["name"] == "bacchus_march_2026"
        assert "Omer Yilmaz" in profile["employee_rules"]

    def test_loads_meta(self, minimal_input):
        _, _, meta = minimal_input
        assert meta["betrieb"] == "bacchus"
        assert meta["range_from"] == "2026-03-03"
        assert meta["range_to"] == "2026-03-09"


class TestGeneratePlan:
    def test_plan_has_assignments(self, plan):
        assert len(plan["assignments"]) > 0

    def test_plan_slot_count(self, plan):
        total = len(plan["assignments"]) + len(plan["unassigned"])
        assert total == 3  # 3 open slots in fixture

    def test_plan_has_fairness(self, plan):
        assert len(plan["fairness"]) > 0

    def test_plan_metrics(self, plan):
        m = plan["metrics"]
        assert m["total_slots"] == 3
        assert m["assigned_slots"] + m["unassigned_slots"] == 3


class TestWriteOutput:
    def test_writes_metrics_json_only(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        assert "metrics.json" in paths
        assert len(paths) == 1
        assert paths["metrics.json"].exists()

    def test_metrics_json_has_enriched_structure(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        # Metadata
        assert metrics["plan_id"] == plan["plan_id"]
        assert metrics["betrieb"] == plan.get("betrieb", "")

        # fill_rate is now a nested dict
        fr = metrics["fill_rate"]
        assert isinstance(fr, dict)
        assert fr["total_slots"] == plan["metrics"]["total_slots"]
        assert fr["pct"] == plan["metrics"]["fill_rate"]
        assert "by_shift_type" in fr
        assert "by_weekday" in fr

    def test_metrics_json_has_fairness(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        fair = metrics["fairness"]
        assert "avg_abs_delta" in fair
        assert "max_abs_delta" in fair
        assert "gini" in fair
        assert isinstance(fair["per_employee"], list)
        assert len(fair["per_employee"]) == len(plan["fairness"])

    def test_metrics_json_has_scoring(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        scoring = metrics["scoring"]
        assert "avg" in scoring
        assert "min" in scoring
        assert "max" in scoring
        assert "per_component_avg" in scoring

    def test_metrics_json_has_constraints(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        constraints = metrics["constraints"]
        assert "unassigned_by_reason" in constraints
        assert isinstance(constraints["unassigned_by_reason"], dict)

    def test_metrics_json_has_workforce(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        wf = metrics["workforce"]
        assert wf["total_employees"] == len(plan["fairness"])
        assert wf["active"] >= 0
        assert wf["total_hours"] >= 0

    def test_metrics_json_has_assessment(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        assert isinstance(metrics["assessment"], list)
        for bullet in metrics["assessment"]:
            assert "level" in bullet
            assert "text" in bullet
            assert bullet["level"] in ("green", "yellow", "red")

    def test_metrics_json_has_monatsuebersicht_data(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        assert isinstance(metrics["open_by_day"], list)
        assert isinstance(metrics["shift_types"], dict)
        assert isinstance(metrics["per_employee_schedule"], list)

    def test_metrics_json_has_slot_assignments(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        slots = metrics["slot_assignments"]
        assert isinstance(slots, list)
        # Total slot_assignments = assigned + unassigned
        assert len(slots) == len(plan["assignments"]) + len(plan["unassigned"])
        # Each assigned slot has employee_name set
        assigned = [s for s in slots if s["employee_name"] is not None]
        assert len(assigned) == len(plan["assignments"])
        # Each slot has required fields
        for s in slots:
            assert "slot_id" in s
            assert "date" in s
            assert "start" in s
            assert "end" in s

    def test_slot_assignments_sorted_by_date(self, plan, tmp_path):
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        slots = metrics["slot_assignments"]
        dates = [(s["date"], s["start"]) for s in slots]
        assert dates == sorted(dates)


class TestRoundtrip:
    """Full roundtrip: load -> plan -> write -> verify consistency."""

    def test_roundtrip_metrics_consistency(self, plan, tmp_path):
        """Verify metrics.json counts match plan data."""
        out_dir = tmp_path / "out"
        paths = write_output(plan, out_dir)
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        fr = metrics["fill_rate"]
        assert fr["assigned"] + fr["unassigned"] == fr["total_slots"]
        assert fr["assigned"] == len(plan["assignments"])
        assert fr["unassigned"] == len(plan["unassigned"])

    def test_roundtrip_fairness_per_employee_count(self, plan, tmp_path):
        out_dir = tmp_path / "out"
        paths = write_output(plan, out_dir)
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        assert len(metrics["fairness"]["per_employee"]) == len(plan["fairness"])

    def test_roundtrip_schedule_matches_assignments(self, plan, tmp_path):
        out_dir = tmp_path / "out"
        paths = write_output(plan, out_dir)
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))

        # Total algo slots in schedule should equal assignment count
        total_algo_slots = sum(
            s["algo_slots"] for s in metrics["per_employee_schedule"]
        )
        assert total_algo_slots == len(plan["assignments"])


class TestMechanisms:
    """Test mechanism field flows through to metrics.json."""

    def test_algo_mechanism_in_metrics(self, minimal_input, tmp_path):
        from allocation_core.mechanisms import run_mechanism
        snapshot, profile, meta = minimal_input
        plan = run_mechanism(
            "algo", snapshot,
            range_from=meta["range_from"],
            range_to=meta["range_to"],
            profile_name=profile.get("name", "test"),
            profile=profile,
        )
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))
        assert metrics["mechanism"] == "algo"

    def test_loose_mechanism_in_metrics(self, minimal_input, tmp_path):
        """Loose mode (algo only, no LLM) should produce mechanism='loose'."""
        snapshot, profile, meta = minimal_input
        plan = generate_plan(
            snapshot,
            range_from=meta["range_from"],
            range_to=meta["range_to"],
            profile_name=profile.get("name", "test"),
            profile=profile,
            constraint_mode="loose",
        )
        plan["mechanism"] = "loose"
        plan["soft_violations"] = plan.get("soft_violations", [])
        paths = write_output(plan, tmp_path / "out")
        metrics = json.loads(paths["metrics.json"].read_text(encoding="utf-8"))
        assert metrics["mechanism"] == "loose"
        assert "soft_violations_count" in metrics

    def test_comparison_builder(self, minimal_input, tmp_path):
        from allocation_core.comparison import build_comparison
        snapshot, profile, meta = minimal_input

        # Generate two mechanisms worth of metrics
        all_metrics = {}
        for mech in ("algo", "loose"):
            mode = "strict" if mech == "algo" else "loose"
            plan = generate_plan(
                snapshot,
                range_from=meta["range_from"],
                range_to=meta["range_to"],
                profile_name=profile.get("name", "test"),
                profile=profile,
                constraint_mode=mode,
            )
            plan["mechanism"] = mech
            mech_dir = tmp_path / "out" / mech
            paths = write_output(plan, mech_dir)
            all_metrics[mech] = json.loads(
                paths["metrics.json"].read_text(encoding="utf-8")
            )

        comparison = build_comparison(all_metrics)
        assert "mechanisms" in comparison
        assert "kpis" in comparison
        assert "per_employee" in comparison
        assert set(comparison["mechanisms"]) == {"algo", "loose"}

    def test_comparison_per_slot_has_slot_detail(self, minimal_input, tmp_path):
        """Per-slot comparison should include slot metadata from slot_assignments."""
        from allocation_core.comparison import build_comparison
        snapshot, profile, meta = minimal_input

        all_metrics = {}
        for mech in ("algo", "loose"):
            mode = "strict" if mech == "algo" else "loose"
            plan = generate_plan(
                snapshot,
                range_from=meta["range_from"],
                range_to=meta["range_to"],
                profile_name=profile.get("name", "test"),
                profile=profile,
                constraint_mode=mode,
            )
            plan["mechanism"] = mech
            mech_dir = tmp_path / "out" / mech
            paths = write_output(plan, mech_dir)
            all_metrics[mech] = json.loads(
                paths["metrics.json"].read_text(encoding="utf-8")
            )

        comparison = build_comparison(all_metrics)
        per_slot = comparison["per_slot"]
        assert len(per_slot) > 0
        for slot in per_slot:
            assert "slot_id" in slot
            assert "date" in slot
            assert "start" in slot
            assert "end" in slot
            assert "agreement" in slot
            assert "algo_employee" in slot
            assert "loose_employee" in slot
