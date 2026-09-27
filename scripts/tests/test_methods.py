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
        # forex was appended 2026-09-17 and removed 2026-09-27 (instruments.json history) -- order is a
        # contract because the config, the schema and the status display all render markets in it; it follows
        # docs/architecture/instruments.json -> markets.
        self.assertEqual(M.markets(), ["crypto", "cfd"])

    def test_every_preset_resolves_to_exactly_one_mode(self):
        """Added with SOLO (2026-09-12): every registry preset must carry a mode that exists in M.MODES."""
        for p in M.PRESETS:
            self.assertIn(p["mode"], M.MODES, f"preset {p['id']!r} names an unknown mode {p.get('mode')!r}")

    def test_single_dimension_presets_resolve_to_solo(self):
        """The two single-dimension presets (wyckoff, ict) are the only ones eligible for SOLO -- this is a
        registry-level property, checked directly against the real presets, not just at _validate() level."""
        for p in M.PRESETS:
            if len(p["dimensions"]) == 1:
                self.assertEqual(p["mode"], "SOLO", f"single-dimension preset {p['id']!r} must be mode SOLO")
            else:
                self.assertNotEqual(p["mode"], "SOLO",
                                     f"multi-dimension preset {p['id']!r} must never be mode SOLO")


class Panes(unittest.TestCase):
    """Every dimension declares a second-pane spec (docs/architecture/methods.json `pane`), so a future 5th
    dimension cannot silently render an empty pane the way the old hand-written ICT note did."""

    def test_every_dimension_has_a_pane_kind_and_label(self):
        for name, dim in M.DIMENSIONS.items():
            self.assertIn("pane", dim, f"dimension {name!r} has no pane spec")
            self.assertIn(dim["pane"]["kind"], M.PANE_KINDS, f"dimension {name!r} has an unknown pane kind")
            self.assertTrue(dim["pane"]["label"], f"dimension {name!r} pane has no label")

    def test_wyckoff_pane_is_volume_unchanged(self):
        self.assertEqual(M.DIMENSIONS["wyckoff"]["pane"]["kind"], "volume")

    def test_ict_pane_is_range_pct_not_volume(self):
        """ICT carries no volume concept (knowledge/integrated/method.md §4.1) -- its pane must never be
        the volume kind."""
        self.assertEqual(M.DIMENSIONS["ict"]["pane"]["kind"], "range_pct")

    def test_footprint_and_heatmap_panes_are_unavailable(self):
        """No live CoinGlass source yet (SYSTEM-DESIGN.md §12) -- must say so honestly, not render an
        empty box."""
        self.assertEqual(M.DIMENSIONS["footprint"]["pane"]["kind"], "unavailable")
        self.assertEqual(M.DIMENSIONS["heatmap"]["pane"]["kind"], "unavailable")


class Modes(unittest.TestCase):
    """SYSTEM-DESIGN.md §6.2 SOLO mode: minimum 1, threshold strictly higher than NORMAL's (no
    cross-confirmation to lean on). NORMAL/ENHANCED/STRICT are unchanged from the master spec."""

    def test_solo_minimum_is_one(self):
        self.assertEqual(M.MODES["SOLO"]["minimum"], 1)

    def test_solo_threshold_is_strictly_greater_than_normal(self):
        self.assertGreater(M.MODES["SOLO"]["threshold"], M.MODES["NORMAL"]["threshold"])

    def test_normal_enhanced_strict_minimums_and_thresholds_are_unchanged(self):
        self.assertEqual(M.MODES["NORMAL"]["minimum"], 2)
        self.assertEqual(M.MODES["NORMAL"]["threshold"], 70)
        self.assertEqual(M.MODES["ENHANCED"]["minimum"], 3)
        self.assertEqual(M.MODES["ENHANCED"]["threshold"], 80)
        self.assertEqual(M.MODES["STRICT"]["minimum"], 3)
        self.assertEqual(M.MODES["STRICT"]["threshold"], 85)


class Validation(unittest.TestCase):
    """_validate(d) is the invariant enforcement _load() calls at import time. Tested directly with small
    inline dicts so a weakened check fails loudly instead of only showing up if the real registry ever
    happens to collide (docs/specs/2026-09-12-method-switch-design.md §6 invariant 3)."""

    def _base(self):
        return {
            "dimensions": {
                "wyckoff": {"markets": ["crypto"], "owns_invalidation": True, "reads": "giá + khối lượng", "pane": {"kind": "volume", "label": "Khối lượng"}, "overlay_engine": "wyckoff"},
                "ict": {"markets": ["crypto"], "owns_invalidation": True, "reads": "cấu trúc giá", "pane": {"kind": "range_pct", "label": "Dealing range"}, "overlay_engine": "ict"},
            },
            "presets": [{"id": "a", "dimensions": ["wyckoff"], "mode": "SOLO"}],
            "runner_methods": {"WYCKOFF-BOOK": {"requires": ["wyckoff"]}},
            "modes": {"SOLO": {"minimum": 1, "threshold": 85}, "NORMAL": {"minimum": 2, "threshold": 70}},
        }

    def test_dimension_missing_pane_spec_raises(self):
        """Exit criteria: a dimension with no declared pane must fail the build, not silently render an
        empty pane the way the old hand-written ICT note did."""
        d = self._base()
        del d["dimensions"]["ict"]["pane"]
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertIn("ict", str(ctx.exception))
        self.assertIn("pane", str(ctx.exception))

    def test_dimension_unknown_pane_kind_raises(self):
        d = self._base()
        d["dimensions"]["ict"]["pane"] = {"kind": "confetti", "label": "x"}
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertIn("ict", str(ctx.exception))
        self.assertIn("confetti", str(ctx.exception))

    def test_dimension_missing_owns_invalidation_raises(self):
        """A new dimension must SAY whether it can own a stop; defaulting either way silently changes
        narrative.schema.json's owner enum via scripts/sync-methods.py."""
        d = self._base()
        del d["dimensions"]["ict"]["owns_invalidation"]
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertIn("ict", str(ctx.exception))
        self.assertIn("owns_invalidation", str(ctx.exception))

    def test_dimension_missing_overlay_engine_raises(self):
        """build-artifact.py OVERLAY_LANES and chart.js `drawnFor` (plan §0.7) key on this instead of a
        hand-kept ("wyckoff", "ict") pair -- a 5th dimension must SAY whether it has a shape-drawing engine."""
        d = self._base()
        del d["dimensions"]["ict"]["overlay_engine"]
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertIn("ict", str(ctx.exception))
        self.assertIn("overlay_engine", str(ctx.exception))

    def test_dimension_overlay_engine_null_is_valid(self):
        """footprint/heatmap have no live source to draw from yet (CLAUDE.md §57) -- null must be accepted,
        not just a lane name. `_base()` has no preset label, so `_validate` still raises further down; the
        assertion is that it is no longer THIS check that objects."""
        d = self._base()
        d["dimensions"]["ict"]["overlay_engine"] = None
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertNotIn("overlay_engine", str(ctx.exception))

    def test_dimension_missing_reads_gloss_raises(self):
        """`reads` is the short phrase naming WHAT the dimension reads, quoted by the page lede for each engaged
        method. Before it existed the lede hard-coded "Wyckoff (giá + khối lượng) và ICT (cấu trúc giá)", so an
        ICT-only page claimed a Wyckoff read; a 5th dimension without a gloss would push someone straight back
        to that literal."""
        d = self._base()
        del d["dimensions"]["ict"]["reads"]
        with self.assertRaises(ValueError) as ctx:
            M._validate(d)
        self.assertIn("ict", str(ctx.exception))
        self.assertIn("reads", str(ctx.exception))

    def test_duplicate_preset_dimension_sets_raise(self):
        d = self._base()
        d["presets"].append({"id": "b", "dimensions": ["wyckoff"], "mode": "SOLO"})
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
        """Every method backtest-methods.py can produce must map, or a future RUNNABLE growth KeyErrors.
        WYCKOFF, COMBINED and PARTIAL were removed 2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md
        finding 6): WYCKOFF's trading range had no CHoCH gate and no Phase A/B, so it could fire a "Spring"
        mid-trend with no accumulation structure behind it; COMBINED and PARTIAL depended on that same range."""
        self.assertEqual(set(M.RUNNER_METHODS), {"WYCKOFF-BOOK", "ICT", "COMBINED-BOOK"})

    def test_derivation(self):
        allow = lambda *on: M.runner_methods({d: d in on for d in M.ALL_DIMENSIONS})
        self.assertEqual(allow("wyckoff"), {"WYCKOFF-BOOK"})
        self.assertEqual(allow("ict"), {"ICT"})
        self.assertEqual(allow("wyckoff", "ict"), {"WYCKOFF-BOOK", "ICT", "COMBINED-BOOK"})
        self.assertEqual(allow("wyckoff", "footprint"), {"WYCKOFF-BOOK"})
        self.assertEqual(allow("footprint", "heatmap"), set())
        self.assertEqual(allow(), set())

    def test_runnable_subset_matches_the_runner(self):
        self.assertEqual(M.runnable(), {"ICT", "WYCKOFF-BOOK"})

    def test_runner_methods_for_a_footprint_preset_does_not_widen(self):
        self.assertEqual(M.runner_methods(M.flags_for("wyckoff+footprint")), {"WYCKOFF-BOOK"})
        self.assertEqual(M.runner_methods(M.flags_for("full")), {"WYCKOFF-BOOK", "ICT", "COMBINED-BOOK"})


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
        # side effects (argparse/file I/O all live inside main()/run(), guarded by
        # `if __name__ == "__main__":`).
        import importlib.util
        spec = importlib.util.spec_from_file_location("rank_setups", os.path.join(ROOT, "scripts", "rank-setups.py"))
        rank_setups = importlib.util.module_from_spec(spec); spec.loader.exec_module(rank_setups)
        self.assertEqual(rank_setups.RUNNABLE, M.runnable())


class DispatchPlan(unittest.TestCase):
    def plan(self, instrument, cfg, unavailable=None):
        import json, tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        try:
            return M.dispatch_plan(instrument, config_path=tmp.name, unavailable=unavailable)
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

    def test_structure_agent_is_dropped_when_both_its_dimensions_are_off_AND_scope_is_preset(self):
        """Updated 2026-09-18 for CLAUDE.md §15, deliberately -- the original asserted the behaviour §15
        forbids.

        It used to hold unconditionally: turning wyckoff and ict off in the preset stopped them being
        analysed at all, so their agent was dropped. That is the "active trading configuration acting as a
        global analysis filter" §15 names. Under the default `available` scope both are still ANALYSED (they
        are live-sourced from candles), so structure-agent is still dispatched -- it just contributes nothing
        to the trade decision.

        The original intent -- an agent with nothing to do is not dispatched -- survives under
        `analysis_scope: "preset"`, the deliberate narrowing, and that is what this now pins."""
        cfg = self.base({"wyckoff": False, "ict": False, "footprint": True, "heatmap": True})
        cfg["markets"]["crypto"]["analysis_scope"] = "preset"
        p = self.plan("BTCUSDT", cfg)
        self.assertNotIn("structure-agent", p["dispatch"])
        self.assertEqual(p["analysis_scope"], "preset")

    def test_under_the_default_scope_an_untraded_methodology_is_still_analysed(self):
        """The §15 fix itself: the preset says what may qualify a trade, not what may be read."""
        p = self.plan("BTCUSDT", self.base({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}))
        self.assertEqual(p["analysis_scope"], "available")
        self.assertEqual(p["engaged"], ["ict"], "only the preset's dimension may qualify a trade")
        self.assertIn("wyckoff", p["analysed"], "an untraded but live-sourced methodology must still be read")
        self.assertEqual(p["analysed_not_traded"], ["wyckoff"])
        self.assertIn("structure-agent", p["dispatch"])

    def test_a_dimension_with_no_live_source_is_not_analysed_whatever_the_preset_says(self):
        """§15 and §6 together: 'when their data and capabilities are available'. Footprint's only provider is
        a fixture, so analysing it would be the mock-satisfies-a-requirement failure in another hat."""
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": True, "footprint": True, "heatmap": True}))
        self.assertNotIn("footprint", p["analysed"])
        self.assertIn("coinglass", p["analysis_skipped"]["footprint"])

    def test_a_traded_dimension_is_dispatched_even_when_its_source_is_a_fixture(self):
        """Dispatch is the UNION. Making it follow `analysed` alone would stop dispatching an agent for a
        dimension the preset DOES trade whenever its only provider is a fixture -- silently breaking the
        deliberate mock rehearsal runs the fixtures exist for."""
        p = self.plan("BTCUSDT", self.base({"wyckoff": False, "ict": False, "footprint": True, "heatmap": False}))
        self.assertIn("footprint", p["engaged"])
        self.assertNotIn("footprint", p["analysed"])
        self.assertIn("flow-agent", p["dispatch"])

    def test_plan_reports_the_engaged_count_and_the_mode_minimum(self):
        """wyckoff-only now names the real 'wyckoff' preset, which is mode SOLO (minimum 1) since 2026-09-12
        -- so this exact config now MEETS its mode minimum, unlike before SOLO existed."""
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": False, "heatmap": False}))
        self.assertEqual(p["engaged_count"], 1)
        self.assertEqual(p["mode"], "SOLO")
        self.assertEqual(p["mode_minimum"], 1)
        self.assertTrue(p["meets_mode_minimum"])

    def test_dispatch_plan_reports_solo_for_a_single_dimension_preset(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}))
        self.assertEqual(p["preset"], "ict")
        self.assertEqual(p["mode"], "SOLO")
        self.assertEqual(p["mode_minimum"], 1)
        self.assertEqual(p["engaged_count"], 1)
        self.assertTrue(p["meets_mode_minimum"])

    def test_dispatch_plan_reports_normal_for_a_two_dimension_preset(self):
        p = self.plan("BTCUSDT", self.base({"wyckoff": True, "ict": False, "footprint": True, "heatmap": False}))
        self.assertEqual(p["preset"], "wyckoff+footprint")
        self.assertEqual(p["mode"], "NORMAL")
        self.assertEqual(p["mode_minimum"], 2)
        self.assertEqual(p["engaged_count"], 2)
        self.assertTrue(p["meets_mode_minimum"])

    def test_trap_a_degraded_multi_dimension_preset_never_reports_solo(self):
        """THE most important test in this task (SYSTEM-DESIGN.md §6.2 'preset, not runtime'). The user
        deliberately selected 'wyckoff+footprint' (both flags ON in config -- NORMAL, minimum 2). Footprint's
        live data source is unavailable for this run (e.g. CoinGlass down), so only 1 dimension is actually
        engaged. If mode were derived from the runtime engaged count, this would silently become SOLO
        (minimum 1) and could pass -- exactly the after-the-fact mode downgrade the mode-lock rule forbids.
        The correct behaviour: mode/preset stay exactly what the config selected, engaged_count drops to 1,
        the mode minimum (2) is NOT met, and the run is NO TRADE on count -- same as if there were no SOLO
        mode at all."""
        cfg = self.base({"wyckoff": True, "ict": False, "footprint": True, "heatmap": False})
        p = self.plan("BTCUSDT", cfg, unavailable={"footprint"})
        self.assertEqual(p["preset"], "wyckoff+footprint", "preset must stay the one the config selected")
        self.assertEqual(p["mode"], "NORMAL", "mode must stay NORMAL, not be recomputed from engaged_count")
        self.assertNotEqual(p["mode"], "SOLO", "a degraded multi-dimension preset must NEVER report SOLO")
        self.assertEqual(p["engaged_count"], 1)
        self.assertEqual(p["mode_minimum"], 2)
        self.assertFalse(p["meets_mode_minimum"], "engaged_count 1 must NOT meet NORMAL's minimum of 2")
        self.assertIn("footprint", p["skipped"])
