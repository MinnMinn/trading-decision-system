"""The method registry has ONE source: docs/architecture/methods.json. Same contract as instruments.json
(SYSTEM-DESIGN.md §1 for instruments; spec docs/specs/2026-09-12-method-switch-design.md §3 for methods)."""
import itertools, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M


class Registry(unittest.TestCase):
    def test_dimensions_per_market(self):
        self.assertEqual(M.dimensions("crypto"), ["wyckoff", "ict", "footprint", "heatmap"])
        self.assertEqual(M.dimensions("cfd"), ["wyckoff", "ict"])

    def test_preset_dimension_sets_are_pairwise_distinct(self):
        """profile_of must be a function: two presets may never name the same set of flags."""
        sets = [frozenset(p["dimensions"]) for p in M.PRESETS]
        self.assertEqual(len(sets), len(set(sets)))

    def test_profile_of_round_trips_every_preset(self):
        for p in M.PRESETS:
            self.assertEqual(M.profile_of({d: d in p["dimensions"] for d in M.ALL_DIMENSIONS}), p["id"])

    def test_every_other_combination_is_custom(self):
        named = {frozenset(p["dimensions"]) for p in M.PRESETS}
        n = 0
        for bits in itertools.product([False, True], repeat=len(M.ALL_DIMENSIONS)):
            dims = dict(zip(M.ALL_DIMENSIONS, bits))
            on = frozenset(d for d, v in dims.items() if v)
            if on not in named:
                self.assertEqual(M.profile_of(dims), "custom", f"{sorted(on)} should be custom")
                n += 1
        self.assertEqual(n, 2 ** len(M.ALL_DIMENSIONS) - len(M.PRESETS))

    def test_presets_for_cfd_excludes_coinglass_dimensions(self):
        ids = [p["id"] for p in M.presets_for("cfd")]
        self.assertEqual(ids, ["wyckoff", "ict", "wyckoff+ict"])

    def test_markets_order_is_a_declared_contract(self):
        self.assertEqual(M.markets(), ["crypto", "cfd"])


class Validation(unittest.TestCase):
    """_validate(d) is the invariant enforcement _load() calls at import time. Tested directly with small
    inline dicts so a weakened check fails loudly instead of only showing up if the real registry ever
    happens to collide (docs/specs/2026-09-12-method-switch-design.md §6 invariant 3)."""

    def _base(self):
        return {
            "dimensions": {"wyckoff": {"markets": ["crypto"]}, "ict": {"markets": ["crypto"]}},
            "presets": [{"id": "a", "dimensions": ["wyckoff"]}],
            "runner_methods": {"WYCKOFF": {"requires": ["wyckoff"]}},
        }

    def test_duplicate_preset_dimension_sets_raise(self):
        d = self._base()
        d["presets"].append({"id": "b", "dimensions": ["wyckoff"]})
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        msg = str(ctx.exception)
        self.assertIn("a", msg)
        self.assertIn("b", msg)

    def test_preset_naming_unknown_dimension_raises(self):
        d = self._base()
        d["presets"].append({"id": "c", "dimensions": ["heatmap"]})
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        msg = str(ctx.exception)
        self.assertIn("c", msg)
        self.assertIn("heatmap", msg)

    def test_runner_method_requiring_unknown_dimension_raises(self):
        d = self._base()
        d["runner_methods"]["ICT"] = {"requires": ["heatmap"]}
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        msg = str(ctx.exception)
        self.assertIn("ICT", msg)
        self.assertIn("heatmap", msg)


class RunnerMethods(unittest.TestCase):
    def test_requires_is_total_over_the_backtest_vocabulary(self):
        """Every method backtest-methods.py can produce must map, or a future RUNNABLE growth KeyErrors."""
        self.assertEqual(set(M.RUNNER_METHODS),
                         {"WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL"})

    def test_derivation(self):
        allow = lambda *on: M.runner_methods({d: d in on for d in M.ALL_DIMENSIONS})
        self.assertEqual(allow("wyckoff"), {"WYCKOFF", "WYCKOFF-BOOK"})
        self.assertEqual(allow("ict"), {"ICT"})
        self.assertEqual(allow("wyckoff", "ict"),
                         {"WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL"})
        self.assertEqual(allow("wyckoff", "footprint"), {"WYCKOFF", "WYCKOFF-BOOK"})
        self.assertEqual(allow("footprint", "heatmap"), set())
        self.assertEqual(allow(), set())

    def test_runnable_subset_matches_the_runner(self):
        self.assertEqual(M.runnable(), {"ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK"})

    def test_runner_methods_for_a_footprint_preset_does_not_widen(self):
        self.assertEqual(M.runner_methods(M.flags_for("wyckoff+footprint")), {"WYCKOFF", "WYCKOFF-BOOK"})
        self.assertEqual(M.runner_methods(M.flags_for("full")),
                         {"WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL"})


class Unverifiable(unittest.TestCase):
    def test_dimensions_with_no_runner_representation(self):
        """Footprint/heatmap never appear in any method's requires -- the page must say so honestly."""
        represented = set().union(*(set(v["requires"]) for v in M.RUNNER_METHODS.values()))
        self.assertEqual(set(M.ALL_DIMENSIONS) - represented, {"footprint", "heatmap"})


class AutomationUsesRegistry(unittest.TestCase):
    def test_no_hand_kept_dimension_list_left(self):
        """The whole point of the registry: automation.py must not carry a second copy."""
        src = open(os.path.join(ROOT, "scripts", "automation.py"), encoding="utf-8").read()
        self.assertNotIn('"wyckoff", "ict", "footprint", "heatmap"', src)

    def test_market_dimensions_comes_from_the_registry(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("auto", os.path.join(ROOT, "scripts", "automation.py"))
        auto = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto)
        self.assertEqual(auto.methods.PATH, M.PATH,
                         "automation.py must read THE registry file, not a look-alike")
        for m in M.markets():
            self.assertEqual(auto.MARKET_DIMENSIONS[m], M.dimensions(m))

    def test_rank_setups_has_no_second_method_list(self):
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertNotIn('{"ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK"}', src)
        # Behavioural, not just textual: rank-setups.py's own RUNNABLE must be the live
        # registry value, not a hand-kept copy. Importing the module at top level has no
        # side effects (argparse/file I/O all live inside main()/main_window_1y()/
        # main_horizons(), guarded by `if __name__ == "__main__":`).
        import importlib.util
        spec = importlib.util.spec_from_file_location("rank_setups", os.path.join(ROOT, "scripts", "rank-setups.py"))
        rank_setups = importlib.util.module_from_spec(spec); spec.loader.exec_module(rank_setups)
        self.assertEqual(rank_setups.RUNNABLE, M.runnable())


class DispatchPlan(unittest.TestCase):
    def plan(self, instrument, cfg):
        import json, tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        try:
            return M.dispatch_plan(instrument, config_path=tmp.name)
        finally:
            os.unlink(tmp.name)

    def base(self, crypto_dims):
        return {"markets": {"crypto": {"enabled": True, "dimensions": crypto_dims},
                            "cfd": {"enabled": True, "dimensions": {"wyckoff": True, "ict": True}}}}

    def test_cfd_never_dispatches_coinglass_agents(self):
        p = self.plan("XAUUSD", self.base({"wyckoff": True, "ict": True, "footprint": True, "heatmap": True}))
        self.assertNotIn("flow-agent", p["dispatch"])
        self.assertNotIn("liquidity-agent", p["dispatch"])
        self.assertTrue(any("CoinGlass" in r for r in p["skipped"].values()))

    def test_a_disabled_dimension_is_skipped_with_a_reason(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": True, "heatmap": False}))
        self.assertIn("ict", p["skipped"])
        self.assertIn("heatmap", p["skipped"])
        self.assertIn("flow-agent", p["dispatch"])

    def test_structure_agent_is_dropped_when_both_its_dimensions_are_off(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": False, "ict": False, "footprint": True, "heatmap": True}))
        self.assertNotIn("structure-agent", p["dispatch"])

    def test_plan_reports_the_engaged_count_and_the_normal_minimum(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": False, "heatmap": False}))
        self.assertEqual(p["engaged_count"], 1)
        self.assertFalse(p["meets_normal_minimum"])
