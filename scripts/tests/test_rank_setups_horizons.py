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
        # Both methods qualify at 15m (scalping -- the horizon's one live timeframe) with plenty of trades --
        # old code (ranked[0] across all methods) would keep only the higher-ranked one and drop the other.
        rows = {"crypto": [_row("15m", self.method_a, n=300, ann=20.0),
                            _row("15m", self.method_b, n=300, ann=5.0)],
                "cfd": []}
        setups = self._run(rows)
        methods_at_scalping = {s["method"] for s in setups if s["market"] == "crypto" and s["horizon"] == "scalping"}
        self.assertEqual(methods_at_scalping, {self.method_a, self.method_b},
                          "both methods must get their own scalping setup, not just the top-ranked one")

    def test_setup_ids_unique(self):
        rows = {"crypto": [_row("15m", self.method_a), _row("15m", self.method_b),
                            _row("1H", self.method_a), _row("4H", self.method_b)],
                "cfd": []}
        setups = self._run(rows)
        ids = [s["id"] for s in setups]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate setup ids: {ids}")

    def test_a_retired_timeframe_is_never_selectable(self):
        """`HORIZONS[hz]` is ONE timeframe string since 2026-09-13, so the candidate filter must be `==`. Under
        the old set-per-horizon -- or under `in` against the string, where `"5m" in "15m"` is also True -- a row
        at a rung the scanner does not scan would be selected, and nothing could execute the selection."""
        for retired in ("5m", "30m", "2H", "1D"):
            rows = {"crypto": [_row(retired, self.method_a, n=300, ann=20.0)], "cfd": []}
            self.assertEqual(self._run(rows), [],
                             f"a row at the retired {retired} rung produced a setup")

    def test_missing_method_at_one_horizon_does_not_drop_others(self):
        """method_a has no qualifying row at swing; method_b does. Both horizons' rows for method_b
        (scalping/day/swing) must still appear, and the swing/method_a gap must not remove swing/method_b."""
        rows = {"crypto": [_row("15m", self.method_a, n=300), _row("15m", self.method_b, n=300),
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

        A gap is explained by the data when no candidate clears BOTH bars: the trade minimum, and rank-setups'
        solvent() -- at least 3 months of history, no blow-up, and actually profitable (user decision
        2026-09-13). Before that decision only the trade minimum applied here, so this test would have called a
        solvency gap "unexplained" and failed on a selection that is behaving exactly as asked."""
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
                              # `==`, never `in`: RS.HORIZONS[hz] is one timeframe STRING since 2026-09-13, so
                              # `in` is a SUBSTRING test -- it passes vacuously ("15m" in "15m") and, worse,
                              # accepts the retired five-minute rung ("5m" in "15m" is also True).
                              and r.get("tf") == RS.HORIZONS[hz]
                              and (r.get("w1y") or {}).get("n", 0) >= min_1y[hz]
                              and RS.solvent(r, "1y")]
                if qualifying:
                    unexplained.append((p["id"], hz, [(r["tf"], r["method"], r["w1y"]["n"]) for r in qualifying]))
        self.assertEqual(unexplained, [],
                         "a preset lost a horizon even though the stability data HAS a candidate clearing the "
                         f"threshold -- that is the crowding-out bug, not a data gap: {unexplained}")

    def test_the_accepted_gaps_are_exactly_these_and_are_still_data_driven(self):
        """Pins the accepted gaps so they cannot silently grow. If another preset/horizon goes empty, this fails
        and someone has to look at whether the rules got more selective or the data got thinner.

        Was `[("ict", "swing")]` until 2026-09-13, when the user replaced "fill every slot with the best
        available candidate" with "only profitable candidates, otherwise leave the slot empty". Three more cells
        emptied as a direct result -- every crypto `day` candidate for WYCKOFF and for ICT either lost money or
        had too few trades in the ranking year. That is the rule working, not a regression; the test above is
        what proves each gap is a data gap rather than crowding-out."""
        empty = []
        for p in M.PRESETS:
            allowed = M.runner_methods(M.flags_for(p["id"])) & M.runnable()
            covered = {s["horizon"] for s in self.setups if s["method"] in allowed}
            for hz in sorted({"scalping", "day", "swing"} - covered):
                empty.append((p["id"], hz))
        self.assertEqual(empty, [("wyckoff", "day"), ("ict", "day"), ("ict", "swing"),
                                 ("wyckoff+footprint", "day")],
                         f"the set of uncovered (preset, horizon) cells changed: {empty}")




class LosersAreNeverSelected(unittest.TestCase):
    """User decision 2026-09-13, overriding the 2026-09-11 "run all 3 horizons for every runnable method even
    when the backtest edge is weak or negative" rule: with at least 3 months of data, drop every candidate that
    loses money and leave the slot EMPTY rather than filling it with the least-bad loser.

    What forced it: the 2026-09-13 re-rank selected cfd-day-wyckoff-1h-border-a, whose own ranking window ends
    at $988 from $10,000 (ruin 2026-01-29, -92.3 % drawdown). The old code filled the (cfd, day, WYCKOFF) slot
    with it because it was the best of three candidates that ALL blew up -- "best available" with no floor under
    it. Under 3 months of data there is no evidence either way, so nothing is selected (fail closed): that is the
    CFD case, whose history at the time was 71 days.
    """

    def _rank1(self, rows, window=None):
        return RS.rank(rows, min_trades=1, window=window)

    def _losing(self, **kw):
        r = _row("1H", "WYCKOFF", **kw)
        r["final"] = 900.0; r["ann"] = -90.0
        r["w1y"] = dict(r["w1y"], final=900.0, ann=-90.0)
        return r

    def _ruined(self):
        r = self._losing()
        r["ruin"] = "2026-01-29T04:00:00Z"
        r["w1y"] = dict(r["w1y"], ruin="2026-01-29T04:00:00Z")
        return r

    def test_a_blown_up_row_is_never_selected(self):
        self.assertEqual(self._rank1([self._ruined()]), [])
        self.assertEqual(self._rank1([self._ruined()], window="1y"), [])

    def test_a_losing_but_not_blown_up_row_is_never_selected(self):
        """$900 from $10,000 never crosses the 10 % ruin threshold in the *whole-history* sense but is still a
        rule that loses money. 'Not blown up' is not the bar; 'made money' is."""
        self.assertEqual(self._rank1([self._losing()]), [])
        self.assertEqual(self._rank1([self._losing()], window="1y"), [])

    def test_a_profitable_row_is_still_selected(self):
        self.assertEqual(len(self._rank1([_row("1H", "WYCKOFF")])), 1)
        self.assertEqual(len(self._rank1([_row("1H", "WYCKOFF")], window="1y")), 1)

    def test_a_window_shorter_than_three_months_is_not_rankable(self):
        """The CFD case: 2026-07-02 -> 2026-09-11 is 71 days. Profitable on 71 days is not evidence."""
        r = _row("1H", "WYCKOFF")
        r["first"], r["last"] = "2026-07-02", "2026-09-11"
        r["w1y"] = dict(r["w1y"], since="2026-07-02")
        self.assertEqual(self._rank1([r]), [])
        self.assertEqual(self._rank1([r], window="1y"), [])
        self.assertEqual(RS.MIN_WINDOW_DAYS, 90)

    def test_exactly_three_months_is_enough(self):
        r = _row("1H", "WYCKOFF")
        r["first"], r["last"] = "2026-01-01", "2026-04-01"      # 90 days
        r["w1y"] = dict(r["w1y"], since="2026-01-01")
        self.assertEqual(len(self._rank1([r])), 1)

    def test_the_slot_is_left_empty_not_filled_with_the_least_bad_loser(self):
        """Two losers at the same (horizon, method): the old code took the better of the two. Now: no setup."""
        rows = [self._losing(cfg="A"), self._ruined()]
        orig = RS.load_rows
        RS.load_rows = lambda paths, market: (rows if market == "crypto" else [])
        try:
            with tempfile.TemporaryDirectory() as td:
                a = Args(rows, []); a.out = os.path.join(td, "o.md"); a.select = os.path.join(td, "s.json")
                RS.main_horizons(a, "2026-09-13")
                setups = json.load(open(a.select, encoding="utf-8"))["setups"]
                md = open(a.out, encoding="utf-8").read()
        finally:
            RS.load_rows = orig
        self.assertEqual(setups, [], "a slot whose every candidate loses money must stay empty")
        self.assertIn("không đủ", md, "an empty slot must still be visible in the report, not silently dropped")

    def test_the_note_no_longer_claims_negative_rows_are_kept(self):
        """rank-setups.py's own header text stated the opposite rule ('kể cả khi lợi thế backtest yếu hoặc âm').
        Leaving it would make the document contradict the code it documents."""
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertNotIn("kể cả khi lợi thế backtest yếu hoặc âm", src)

if __name__ == "__main__":
    unittest.main()
