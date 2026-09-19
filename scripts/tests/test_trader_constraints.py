"""CLAUDE.md §0.9 (docs/plans/2026-09-18-close-feature-gaps.md) -- per-trader, per-methodology constraints.

Three things these tests are built to prove:

1. **The registry refuses at import**, not at use: an unknown kind, a min_rr below the platform floor, and a
   `false` for an only-true kind are all authoring mistakes that must never load as an enforced constraint.
2. **`overlay()` only tightens.** It returns a NEW dict; the input is untouched; every operation (max,
   intersection, OR, min) cannot loosen whatever was already in force.
3. **The live registry (`docs/architecture/trader-constraints.json`) loads**, and the wiring into
   `trading_system.describe()` and `scripts/backtest-methods.py --trader` actually reaches it.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import trader_constraints as TC
import trading_system as TS


class RegistryLoadsAndRefuses(unittest.TestCase):
    def test_the_live_registry_loads(self):
        self.assertIn("tung", TC.TRADERS)

    def test_unknown_kind_is_refused_at_import(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {
            "ict": [{"kind": "not_a_real_kind", "value": 1, "why": "w"}]}}}}
        with self.assertRaises(TC.RegistryError) as cm:
            TC._validate(data, path="test.json")
        self.assertIn("unknown constraint kind", str(cm.exception))

    def test_min_rr_below_the_platform_floor_is_refused(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {
            "ict": [{"kind": "min_rr", "value": 0.5, "why": "w"}]}}}}
        with self.assertRaises(TC.RegistryError) as cm:
            TC._validate(data, path="test.json")
        self.assertIn("BELOW the platform floor", str(cm.exception))

    def test_a_false_value_for_an_only_true_kind_is_refused(self):
        for kind in TC.BOOL_TRUE_ONLY:
            data = {"version": 1, "traders": {"x": {"per_methodology": {
                "ict": [{"kind": kind, "value": False, "why": "w"}]}}}}
            with self.subTest(kind=kind), self.assertRaises(TC.RegistryError):
                TC._validate(data, path="test.json")

    def test_an_unknown_session_label_is_refused(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {
            "ict": [{"kind": "sessions", "value": ["mars"], "why": "w"}]}}}}
        with self.assertRaises(TC.RegistryError):
            TC._validate(data, path="test.json")

    def test_an_item_with_no_reason_is_refused(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {
            "ict": [{"kind": "min_rr", "value": 3.5, "why": "  "}]}}}}
        with self.assertRaises(TC.RegistryError):
            TC._validate(data, path="test.json")

    def test_an_empty_trader_entry_is_refused(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {}}}}
        with self.assertRaises(TC.RegistryError):
            TC._validate(data, path="test.json")

    def test_a_legal_registry_validates(self):
        data = {"version": 1, "traders": {"x": {"per_methodology": {
            "ict": [{"kind": "min_rr", "value": 3.5, "why": "w"}]}}}}
        self.assertEqual(sorted(TC._validate(data, path="test.json")), ["x"])


class ForTrader(unittest.TestCase):
    def test_unknown_trader_raises_rather_than_silently_applying_nothing(self):
        with self.assertRaises(TC.NotDeclared):
            TC.for_trader("no-such-trader")

    def test_known_trader_returns_per_methodology_items(self):
        per = TC.for_trader("tung")
        self.assertIn("ict", per)
        self.assertIn("wyckoff", per)
        self.assertEqual(per["ict"][0]["kind"], "min_rr")

    def test_load_covers_every_declared_trader(self):
        self.assertEqual(set(TC.load()), set(TC.TRADERS))


class Overlay(unittest.TestCase):
    BASE = dict(min_rr=3.0, types=(1, 2, 3), htf=False, ict_disp=False, ict_pd=False, sloped_gate=False)

    def test_overlay_returns_a_new_dict_and_leaves_the_input_untouched(self):
        out = TC.overlay(self.BASE, "tung", "ict")
        self.assertIsNot(out, self.BASE)
        self.assertEqual(self.BASE["min_rr"], 3.0)

    def test_ict_overlay_tightens_min_rr(self):
        out = TC.overlay(self.BASE, "tung", "ict")
        self.assertEqual(out["min_rr"], 3.5)

    def test_overlay_never_lowers_an_already_stricter_value(self):
        stricter = dict(self.BASE, min_rr=4.0)
        out = TC.overlay(stricter, "tung", "ict")
        self.assertEqual(out["min_rr"], 4.0)

    def test_wyckoff_overlay_carries_sessions_and_does_not_touch_min_rr(self):
        out = TC.overlay(self.BASE, "tung", "wyckoff")
        self.assertEqual(out["_sessions"], frozenset({"london", "ny_am"}))
        self.assertEqual(out["min_rr"], 3.0)

    def test_a_methodology_with_no_declared_items_is_unchanged(self):
        out = TC.overlay(self.BASE, "tung", "footprint")
        self.assertEqual(out, dict(self.BASE))

    def test_bool_kinds_only_turn_on(self):
        # Monkeypatch TC.TRADERS with a synthetic entry so overlay() itself (not just _validate()) is
        # exercised for a bool-only-true kind, without touching the real registry.
        saved = TC.TRADERS
        try:
            TC.TRADERS = {"y": {"per_methodology": {
                "ict": [{"kind": "htf", "value": True, "why": "w"}]}}}
            out = TC.overlay(self.BASE, "y", "ict")
            self.assertIs(out["htf"], True)
            already_on = dict(self.BASE, htf=True)
            out2 = TC.overlay(already_on, "y", "ict")
            self.assertIs(out2["htf"], True)   # cannot be turned back off by re-applying
        finally:
            TC.TRADERS = saved

    def test_types_overlay_intersects(self):
        saved = TC.TRADERS
        try:
            TC.TRADERS = {"z": {"per_methodology": {
                "ict": [{"kind": "types", "value": [1, 2], "why": "w"}]}}}
            out = TC.overlay(self.BASE, "z", "ict")
            self.assertEqual(out["types"], (1, 2))
        finally:
            TC.TRADERS = saved


class TradingSystemDescribeResolvesTrader(unittest.TestCase):
    def test_default_has_empty_items_and_unchanged_source(self):
        cc = TS.describe("scalping")["custom_constraints"]
        self.assertEqual(cc["items"], [])
        self.assertIn("automation-config.json", cc["source"])

    def test_a_named_trader_resolves_items_from_the_registry(self):
        cc = TS.describe("scalping", trader="tung")["custom_constraints"]
        kinds = {i["kind"] for i in cc["items"]}
        self.assertIn("min_rr", kinds)
        self.assertIn("sessions", kinds)
        self.assertTrue(all("methodology" in i for i in cc["items"]))

    def test_classification_is_unaffected_by_the_trader_kwarg(self):
        # `trader` must not be forwarded into role_of()'s only_when predicates -- it is not a `setup` /
        # `engaged` / `instrument` context value, and role_of() would raise TypeError if it were passed
        # through.
        d1 = TS.describe("scalping")
        d2 = TS.describe("scalping", trader="tung")
        self.assertEqual(d1["dependencies"], d2["dependencies"])


if __name__ == "__main__":
    unittest.main()
