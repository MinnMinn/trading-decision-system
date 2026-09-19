"""scripts/expectation_producer.py -- the caller docs/audits/2026-09-18-feature-audit.md row 11 found missing
("outside test no file calls create()"). Plan: docs/plans/2026-09-18-close-feature-gaps.md §0.5, Task B1."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import expectation as X
import expectation_producer as EP


def plan_row(**kw):
    kw.setdefault("entry", 77000.0)
    kw.setdefault("stop_loss", 76500.0)
    kw.setdefault("targets", [77500.0, 78000.0])
    kw.setdefault("direction", "LONG")
    kw.setdefault("date_opened", "2026-09-17T18:00:00Z")
    kw.setdefault("setup_type", "Top5 ict: sweep SSL -> MSS -> limit tại mép FVG")
    return dict(kw)


def signal(**kw):
    kw.setdefault("entry", 77000.0)
    kw.setdefault("stop", 76500.0)
    kw.setdefault("target", 78000.0)
    kw.setdefault("side", "long")
    kw.setdefault("time", "2026-09-17T18:00:00Z")
    return dict(kw)


def setup_row(method="ICT", tf="15m"):
    return {"method": method, "tf": tf, "id": f"{method.lower()}-15m"}


class FromPlan(unittest.TestCase):
    def test_returns_a_sealed_record_with_three_phases(self):
        r = EP.from_plan(plan_row(), "ict")
        phases = {leg["phase"] for leg in r["original"]["expected_path"]}
        self.assertEqual(phases, {"before_entry", "entry_area", "after_entry"})
        self.assertEqual(r["status"], "POTENTIAL")

    def test_invalidation_owner_is_the_methodology(self):
        r = EP.from_plan(plan_row(), "wyckoff")
        self.assertEqual(r["original"]["invalidation"]["owner"], "wyckoff")
        self.assertEqual(r["original"]["invalidation"]["level"], 76500.0)

    def test_kind_is_the_declared_mapping(self):
        self.assertEqual(EP.from_plan(plan_row(), "ict")["original"]["kind"], "structural_objective")
        self.assertEqual(EP.from_plan(plan_row(), "wyckoff")["original"]["kind"], "trading_range_objective")

    def test_available_time_derived_when_series_given(self):
        r = EP.from_plan(plan_row(), "ict", series=("BTCUSDT", "15m"))
        self.assertIsNotNone(r["original"]["available_time"])
        self.assertGreater(r["original"]["available_time"], r["original"]["event_time"])

    def test_no_available_time_without_a_series(self):
        r = EP.from_plan(plan_row(), "ict")
        self.assertIsNone(r["original"]["available_time"])

    def test_a_plan_with_no_targets_raises(self):
        with self.assertRaises(ValueError):
            EP.from_plan(plan_row(targets=[]), "ict")

    def test_unmapped_methodology_raises(self):
        with self.assertRaises(ValueError):
            EP.from_plan(plan_row(), "footprint")

    def test_after_entry_legs_are_one_per_target(self):
        r = EP.from_plan(plan_row(targets=[1.0, 2.0, 3.0]), "wyckoff")
        after = [leg for leg in r["original"]["expected_path"] if leg["phase"] == "after_entry"]
        self.assertEqual([leg["level"] for leg in after], [1.0, 2.0, 3.0])
        self.assertEqual([leg["label"] for leg in after], ["target_1", "target_2", "target_3"])

    def test_before_entry_and_entry_area_key_off_the_entry(self):
        r = EP.from_plan(plan_row(entry=100.0), "ict")
        before = next(l for l in r["original"]["expected_path"] if l["phase"] == "before_entry")
        area = next(l for l in r["original"]["expected_path"] if l["phase"] == "entry_area")
        self.assertEqual(before["level"], 100.0)
        self.assertEqual(area["level"], 100.0)


class FromSignal(unittest.TestCase):
    def test_single_method_yields_one_record(self):
        recs = EP.from_signal(signal(), setup_row("ICT"), "BTCUSDT")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["original"]["methodology"], "ict")

    def test_combined_yields_two_records_kept_apart_by_methodology(self):
        recs = EP.from_signal(signal(), setup_row("COMBINED-BOOK"), "BTCUSDT")
        methodologies = sorted(r["original"]["methodology"] for r in recs)
        self.assertEqual(methodologies, ["ict", "wyckoff"])
        paths = X.paths_by_methodology(recs)
        self.assertEqual(set(paths), {"ict", "wyckoff"})
        # never merged: each methodology's own path only carries its own record id
        self.assertNotEqual(paths["ict"][0][0], paths["wyckoff"][0][0])

    def test_unknown_runner_method_raises(self):
        with self.assertRaises(ValueError):
            EP.from_signal(signal(), setup_row("NOT-A-METHOD"), "BTCUSDT")

    def test_shared_created_at_gives_the_same_ids_across_calls(self):
        """The runner's step-11 tr.ok() and the persisted plan must name the SAME record ids -- only true if
        both derive from one from_signal() call (or the same created_at)."""
        r1 = EP.from_signal(signal(), setup_row("ICT"), "BTCUSDT", created_at="2026-09-17T18:00:00Z")
        r2 = EP.from_signal(signal(), setup_row("ICT"), "BTCUSDT", created_at="2026-09-17T18:00:00Z")
        self.assertEqual(r1[0]["id"], r2[0]["id"])


if __name__ == "__main__":
    unittest.main()
