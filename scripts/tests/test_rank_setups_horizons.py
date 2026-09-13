"""scripts/rank-setups.py --horizons must select one setup per (horizon, method) -- not one per horizon --
so that every method-switch preset (docs/architecture/methods.json), whichever methods it engages, still
gets all three horizons (scalping/day/swing). Runtime filtering of which methods may fire is
strategy-runner.py's allowed_methods() (out of scope here per the task -- replicated via methods.py
runner_methods(), never re-implemented or hardcoded).

Fixes a bug where main_horizons() picked ranked[0] across ALL methods per horizon: whichever single
method happened to rank best at a given horizon crowded out every other method there, so a preset
engaging only one method (e.g. `ict`) could be left with zero setups at two of the three horizons.
"""
import importlib.util, json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

_spec = importlib.util.spec_from_file_location("rank_setups", os.path.join(ROOT, "scripts", "rank-setups.py"))
RS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(RS)


def _row(tf, method, n=200, ann=10.0, cfg="A", target="border"):
    """Minimal stability-report row: enough fields for rank()/fmt() to run without KeyError."""
    return {"tf": tf, "cfg": cfg, "method": method, "target": target, "file": "test-fixture.json",
            "first": "2025-01-01", "last": "2026-01-01",
            "n": n, "ann": ann, "dd": 10.0, "final": 11000.0, "ruin": None,
            "q_pos": 60.0, "q_worst": -5.0, "q_med": 2.0, "q_mean": 2.0, "q_sd": 1.0, "stab": 1.0,
            "y_pos": 1, "y_n": 1, "years": [["2025", ann]], "quarters": [1.0, 2.0, 3.0, 4.0],
            "w1y": {"n": n, "ann": ann, "dd": 10.0, "final": 11000.0, "ruin": None, "q_pos": 60.0,
                    "q_worst": -5.0, "q_med": 2.0, "q_mean": 2.0, "q_sd": 1.0, "stab": 1.0,
                    "y_pos": 1, "y_n": 1, "since": "2025-01-01"}}


class Args:
    """Stand-in for argparse.Namespace with just the fields main_horizons() reads."""
    def __init__(self, crypto_rows, cfd_rows, window="all", n=5,
                 crypto_symbols="BTCUSDT", cfd_symbols="XAUUSD"):
        self._crypto_rows, self._cfd_rows = crypto_rows, cfd_rows
        self.window = window; self.n = n
        self.crypto_symbols = crypto_symbols; self.cfd_symbols = cfd_symbols
        self.crypto = []; self.cfd = []   # unused: load_rows is monkeypatched per-test
        self.out = None; self.select = None


class SelectionCoversEveryMethodPerHorizon(unittest.TestCase):
    """Algorithmic regression guard: with qualifying data for two different RUNNABLE methods at the
    SAME horizon, both must survive as separate setups (not just the one that ranks higher)."""

    def setUp(self):
        self.runnable = sorted(M.runnable())
        self.assertGreaterEqual(len(self.runnable), 2, "need >=2 runnable methods for this test to be meaningful")
        self.method_a, self.method_b = self.runnable[0], self.runnable[1]

    def _run(self, rows_by_market):
        orig_load_rows = RS.load_rows
        RS.load_rows = lambda paths, market: rows_by_market.get(market, [])
        try:
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "out.md"); sel = os.path.join(td, "sel.json")
                a = Args(rows_by_market.get("crypto", []), rows_by_market.get("cfd", []))
                a.out = out; a.select = sel
                RS.main_horizons(a, "2026-09-13")
                return json.load(open(sel, encoding="utf-8"))["setups"]
        finally:
            RS.load_rows = orig_load_rows

    def test_two_methods_same_horizon_both_survive(self):
        # Both methods qualify at 5m (scalping) with plenty of trades -- old code (ranked[0] across all
        # methods) would keep only the higher-ranked one and drop the other entirely.
        rows = {"crypto": [_row("5m", self.method_a, n=300, ann=20.0),
                            _row("5m", self.method_b, n=300, ann=5.0)],
                "cfd": []}
        setups = self._run(rows)
        methods_at_scalping = {s["method"] for s in setups if s["market"] == "crypto" and s["horizon"] == "scalping"}
        self.assertEqual(methods_at_scalping, {self.method_a, self.method_b},
                          "both methods must get their own scalping setup, not just the top-ranked one")

    def test_setup_ids_unique(self):
        rows = {"crypto": [_row("5m", self.method_a), _row("5m", self.method_b),
                            _row("30m", self.method_a), _row("4H", self.method_b)],
                "cfd": []}
        setups = self._run(rows)
        ids = [s["id"] for s in setups]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate setup ids: {ids}")

    def test_missing_method_at_one_horizon_does_not_drop_others(self):
        """method_a has no qualifying row at swing; method_b does. Both horizons' rows for method_b
        (scalping/day/swing) must still appear, and the swing/method_a gap must not remove swing/method_b."""
        rows = {"crypto": [_row("5m", self.method_a, n=300), _row("5m", self.method_b, n=300),
                            _row("4H", self.method_b, n=300)],  # method_a has nothing at 4H (swing)
                "cfd": []}
        setups = self._run(rows)
        self.assertIn(("swing", self.method_b), {(s["horizon"], s["method"]) for s in setups})
        self.assertNotIn(("swing", self.method_a), {(s["horizon"], s["method"]) for s in setups})


class PresetCoverageOfRealSelection(unittest.TestCase):
    """The committed selection file: every method-switch preset must have all 3 horizons covered for
    crypto once strategy-runner.py's allowed_methods() filters it -- replicated here via
    methods.py runner_methods() (never re-implemented / hardcoded), per the task's instruction not to
    touch strategy-runner.py. This is the acceptance test: it fails if a future change reverts the
    per-(horizon, method) selection back to a single best-of-all-methods pick per horizon."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, "docs", "architecture", "pilot-top5.json")
        cls.setups = [s for s in json.load(open(path, encoding="utf-8"))["setups"] if s["market"] == "crypto"]

    def test_every_preset_covers_all_three_horizons_for_crypto(self):
        """A preset may be left without a horizon ONLY when the stability data has no candidate that clears the
        threshold -- never because the ranking crowded one method out with another, which is the bug this class
        exists to catch.

        Live case (2026-09-13): the `ict` preset has no crypto swing setup. Its swing candidates are 4H with 4
        trades in the ranking year and 1D with 0, against a threshold of 6. Nothing was crowded out; there was
        nothing to rank. User accepted that rather than lowering the bar to make a 4-trade setup selectable
        (option A) -- so the assertion below is that every gap is explained by the data, not that gaps cannot
        exist."""
        stability = json.load(open(os.path.join(ROOT, "data", "history", "stability", "crypto-live.json"),
                                   encoding="utf-8"))
        rows = stability if isinstance(stability, list) else stability.get("rows", stability)
        min_1y = {"scalping": 20, "day": 15, "swing": 6}      # rank-setups.main_horizons, --window 1y

        unexplained = []
        for p in M.PRESETS:
            allowed = M.runner_methods(M.flags_for(p["id"])) & M.runnable()
            covered = {s["horizon"] for s in self.setups if s["method"] in allowed}
            for hz in {"scalping", "day", "swing"} - covered:
                qualifying = [r for r in rows
                              if r.get("method") in allowed
                              and r.get("tf") in RS.HORIZONS[hz]
                              and (r.get("w1y") or {}).get("n", 0) >= min_1y[hz]]
                if qualifying:
                    unexplained.append((p["id"], hz, [(r["tf"], r["method"], r["w1y"]["n"]) for r in qualifying]))
        self.assertEqual(unexplained, [],
                         "a preset lost a horizon even though the stability data HAS a candidate clearing the "
                         f"threshold -- that is the crowding-out bug, not a data gap: {unexplained}")

    def test_the_ict_swing_gap_is_still_the_only_one_and_is_still_data_driven(self):
        """Pins the accepted gap so it cannot silently grow. If another preset/horizon goes empty, this fails and
        someone has to look at whether the rules got more selective or the data got thinner."""
        empty = []
        for p in M.PRESETS:
            allowed = M.runner_methods(M.flags_for(p["id"])) & M.runnable()
            covered = {s["horizon"] for s in self.setups if s["method"] in allowed}
            for hz in sorted({"scalping", "day", "swing"} - covered):
                empty.append((p["id"], hz))
        self.assertEqual(empty, [("ict", "swing")],
                         f"the set of uncovered (preset, horizon) cells changed: {empty}")


if __name__ == "__main__":
    unittest.main()
