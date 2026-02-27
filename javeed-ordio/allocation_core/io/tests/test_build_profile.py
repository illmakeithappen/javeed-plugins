"""Tests for build_profile() — constraint profile loading and vorgaben merge."""
from pathlib import Path

import pytest

from allocation_core.io.directives import build_profile

# Real constraint_profiles.json used by the pipeline
PROFILES_PATH = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "javeed-ordio"
    / "config"
    / "constraint_profiles.json"
)


class TestBuildProfile:
    def test_loads_named_profile(self):
        """Load bacchus_march_2026 and verify name, policy, employee rules."""
        profile = build_profile("bacchus_march_2026", profiles_path=PROFILES_PATH)
        assert profile["profile_name"] == "bacchus_march_2026"
        assert profile["policy"]["prefer_applicants"] is True
        assert profile["policy"]["distribute_applications_across_month"] is True
        assert "bar" in profile["employee_rules"]
        assert "matteo" in profile["employee_rules"]

    def test_falls_back_to_default(self):
        """A nonexistent profile name falls back to 'default'."""
        profile = build_profile("does_not_exist", profiles_path=PROFILES_PATH)
        assert profile["profile_name"] == "default"
        assert profile["policy"]["prefer_applicants"] is True
        # Default has no employee rules
        assert profile["employee_rules"] == {}

    def test_policy_fields_preserved(self):
        """hinweg_march_2026 policy has prefer_shift_type_variation and distribute_applications_across_month."""
        profile = build_profile("hinweg_march_2026", profiles_path=PROFILES_PATH)
        assert profile["policy"]["prefer_shift_type_variation"] is True
        assert profile["policy"]["distribute_applications_across_month"] is True

    def test_employee_rules_use_weekly_hours(self):
        """Constraint profile rules flow through — bar has target_weekly_hours."""
        profile = build_profile("bacchus_march_2026", profiles_path=PROFILES_PATH)
        bar_rules = profile["employee_rules"]["bar"]
        assert bar_rules["target_weekly_hours"] == 20

    def test_no_dead_fields(self):
        """base_weekly_hours and max_additional_weekly_hours must not appear in any employee rule."""
        for name in ("bacchus_march_2026", "hinweg_march_2026", "default"):
            profile = build_profile(name, profiles_path=PROFILES_PATH)
            for emp, rules in profile["employee_rules"].items():
                assert "base_weekly_hours" not in rules, (
                    f"base_weekly_hours found in {name}/{emp}"
                )
                assert "max_additional_weekly_hours" not in rules, (
                    f"max_additional_weekly_hours found in {name}/{emp}"
                )

    def test_rule_sources_all_ordio(self):
        """Without vorgaben, every field in _rule_sources should be 'ordio'."""
        profile = build_profile("bacchus_march_2026", profiles_path=PROFILES_PATH)
        for emp, sources in profile["_rule_sources"].items():
            for field, src in sources.items():
                assert src == "ordio", f"{emp}.{field} source is '{src}', expected 'ordio'"
