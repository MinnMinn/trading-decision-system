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


class Unverifiable(unittest.TestCase):
    def test_dimensions_with_no_runner_representation(self):
        """Footprint/heatmap never appear in any method's requires -- the page must say so honestly."""
        represented = set().union(*(set(v["requires"]) for v in M.RUNNER_METHODS.values()))
        self.assertEqual(set(M.ALL_DIMENSIONS) - represented, {"footprint", "heatmap"})
