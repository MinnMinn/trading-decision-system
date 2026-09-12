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
