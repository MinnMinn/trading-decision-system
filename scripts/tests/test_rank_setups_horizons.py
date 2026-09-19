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
        # CLAUDE.md §38 (2026-09-18): every ranking mode passes the CLI's --require-stamped through to
        # load_rows. These tests monkeypatch load_rows, so the value is never read -- but the field has to
        # exist, because the stand-in is a stand-in for the real Namespace.
        self.require_stamped = False


class SelectionCoversEveryMethodPerHorizon(unittest.TestCase):
    """Algorithmic regression guard: with qualifying data for two different RUNNABLE methods at the
    SAME horizon, both must survive as separate setups (not just the one that ranks higher)."""

    def setUp(self):
        self.runnable = sorted(M.runnable())
        self.assertGreaterEqual(len(self.runnable), 2, "need >=2 runnable methods for this test to be meaningful")
        self.method_a, self.method_b = self.runnable[0], self.runnable[1]

    def _run(self, rows_by_market):
        orig_load_rows = RS.load_rows
        RS.load_rows = lambda paths, market, **kw: rows_by_market.get(market, [])
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

        Re-pinned 2026-09-19, and the jump is large. Two user decisions landed the same day: the WYCKOFF
        proxy engine and COMBINED/PARTIAL were removed as unfaithful to the books (so the runnable set is
        {ICT, WYCKOFF-BOOK}), and the selection criterion became PROP-PASS under a declared account. Crypto
        now earns exactly ONE setup -- ICT scalping -- because no other crypto rule cleared both the account's
        survival test and HORIZON_MIN_TRADES (day needs 60 trades). Every gap below is therefore a rule that
        did not earn selection, not a rule that was dropped. If this list SHRINKS, a rule earned its way back
        in; if it grows, something stopped earning it and that is worth looking at.

        Was `[("ict", "swing")]` until 2026-09-13, when the user replaced "fill every slot with the best
        available candidate" with "only profitable candidates, otherwise leave the slot empty". Three more cells
        emptied as a direct result -- every crypto `day` candidate for WYCKOFF and for ICT either lost money or
        had too few trades in the ranking year. That is the rule working, not a regression; the test above is
        what proves each gap is a data gap rather than crowding-out.

        Re-pinned AGAIN on 2026-09-19, and this time it pins an EMPTY crypto selection -- every preset, every
        horizon. That is not the test giving up: it is the measured state, and the assertion below fails the
        moment crypto earns a setup back, which is the direction anyone should want it to fail in. The
        ICT backtest was booking trades whose FVG limit had already been passed by the bar the setup became
        detectable -- orders no live runner could have placed, and which scripts/strategy-runner.py correctly
        refuses. Measured over the last 30 000 15m bars: BTCUSDT 19 -> 6 trades, ETHUSDT 17 -> 1, SOLUSDT
        11 -> 0; 85 % of the crypto ICT population was unreachable. With that corrected, ICT clears no horizon
        on either market, and the whole selection is ONE row: cfd swing WYCKOFF-BOOK 4H at n = 5. So every ICT
        cell is empty here. The ONE row that survived the re-rank is CFD (swing WYCKOFF-BOOK 4H, n = 5), and
        this class looks at crypto only -- so crypto's coverage is zero across the board. A list this complete
        is not a passing state; it is the honest reading of the evidence, and it is what the next round of
        method work has to move.

        Two more emptied on 2026-09-18, on the re-rank that followed the CFD venue-fee correction and the
        regeneration of both stability files: `("wyckoff", "scalping")` and `("wyckoff+footprint", "scalping")`.
        Checked before this snapshot was widened, on the fresh 1-year window: every WYCKOFF 15m config ends
        around $1,000 of a $10,000 start (n = 709 / 1,192 / 1,263), and every WYCKOFF-BOOK 15m config finishes
        BELOW the start ($7,772 / $8,796 / $9,912). Sample size is not the reason -- the trade counts clear
        `min_1y` comfortably -- the reason is that the method lost money on the fifteen-minute rung, so the
        solvency rule leaves the slot empty rather than shipping a loser. Same rule, thinner data."""
        empty = []
        for p in M.PRESETS:
            allowed = M.runner_methods(M.flags_for(p["id"])) & M.runnable()
            covered = {s["horizon"] for s in self.setups if s["method"] in allowed}
            for hz in sorted({"scalping", "day", "swing"} - covered):
                empty.append((p["id"], hz))
        self.assertEqual(empty, [(p["id"], hz) for p in M.PRESETS for hz in ("day", "scalping", "swing")],
                         f"the set of uncovered (preset, horizon) cells changed: {empty}")
        self.assertEqual(self.setups, [],
                         "crypto has a selected setup again -- that is GOOD news, and this pin must be "
                         "rewritten to name it rather than asserting the empty state")




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
        r = _row("1H", "WYCKOFF-BOOK", **kw)
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
        self.assertEqual(len(self._rank1([_row("1H", "WYCKOFF-BOOK")])), 1)
        self.assertEqual(len(self._rank1([_row("1H", "WYCKOFF-BOOK")], window="1y")), 1)

    def test_a_window_shorter_than_three_months_is_not_rankable(self):
        """The CFD case: 2026-07-02 -> 2026-09-11 is 71 days. Profitable on 71 days is not evidence."""
        r = _row("1H", "WYCKOFF-BOOK")
        r["first"], r["last"] = "2026-07-02", "2026-09-11"
        r["w1y"] = dict(r["w1y"], since="2026-07-02")
        self.assertEqual(self._rank1([r]), [])
        self.assertEqual(self._rank1([r], window="1y"), [])
        self.assertEqual(RS.MIN_WINDOW_DAYS, 90)

    def test_exactly_three_months_is_enough(self):
        r = _row("1H", "WYCKOFF-BOOK")
        r["first"], r["last"] = "2026-01-01", "2026-04-01"      # 90 days
        r["w1y"] = dict(r["w1y"], since="2026-01-01")
        self.assertEqual(len(self._rank1([r])), 1)

    def test_the_slot_is_left_empty_not_filled_with_the_least_bad_loser(self):
        """Two losers at the same (horizon, method): the old code took the better of the two. Now: no setup."""
        rows = [self._losing(cfg="A"), self._ruined()]
        orig = RS.load_rows
        RS.load_rows = lambda paths, market, **kw: (rows if market == "crypto" else [])
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


class PropPassRanking(unittest.TestCase):
    """User decision 2026-09-19: rank by whether THIS account's challenge is passed, not by positive quarters.
    The account-blind key selected two CFD rules that BOTH fail an FTMO-style challenge while rules that pass
    sat in the same file (docs/audits/2026-09-19-knowledge-fidelity.md §3)."""

    def row(self, **kw):
        base = dict(tf="1H", cfg="C", method="ICT", n=50, first="2020-01-01", last="2026-01-01",
                    ruin=None, ann=10.0, q_pos=60, q_worst=-3.0, stab=1.0, y_pos=3, y_n=4,
                    failed_by=None, perf={})
        base.update(kw); return base

    def test_a_rule_that_broke_the_account_is_not_selectable(self):
        broke = self.row(failed_by="drawdown: equity 89000 <= 90% of initial_balance", q_pos=99)
        kept = self.row(perf={"prop_pass_probability": {"value": 0.1}})
        out = RS.rank([broke, kept], 1, rank_by="prop-pass")
        self.assertEqual([r["failed_by"] for r in out], [None])

    def test_higher_pass_probability_wins(self):
        lo = self.row(method="ICT", perf={"prop_pass_probability": {"value": 0.20}})
        hi = self.row(method="WYCKOFF-BOOK", perf={"prop_pass_probability": {"value": 0.66}})
        out = RS.rank([lo, hi], 1, rank_by="prop-pass")
        self.assertEqual(out[0]["method"] if len(out) == 1 else
                         sorted(out, key=RS.prop_key, reverse=True)[0]["method"], "WYCKOFF-BOOK")

    def test_an_unmeasurable_pass_probability_never_outranks_a_measured_one(self):
        measured = self.row(method="ICT", perf={"prop_pass_probability": {"value": 0.05}})
        unknown = self.row(method="WYCKOFF-BOOK",
                           perf={"prop_pass_probability": {"unavailable": "sample too small", "owner": "§39"}})
        self.assertGreater(RS.prop_key(measured), RS.prop_key(unknown))

    def test_ties_on_pass_break_on_failure_probability_then_drawdown(self):
        a = self.row(method="ICT", perf={"prop_pass_probability": {"value": 0.5},
                                         "account_failure_probability": {"value": 0.10},
                                         "max_drawdown": {"value": 0.08}})
        b = self.row(method="WYCKOFF-BOOK", perf={"prop_pass_probability": {"value": 0.5},
                                                  "account_failure_probability": {"value": 0.40},
                                                  "max_drawdown": {"value": 0.03}})
        self.assertGreater(RS.prop_key(a), RS.prop_key(b), "lower failure probability must win before drawdown")

    def test_the_consistency_mode_is_unchanged_by_default(self):
        rows = [self.row(q_pos=10, method="ICT"), self.row(q_pos=90, method="WYCKOFF-BOOK")]
        out = RS.rank(rows, 1)
        self.assertTrue(out, "consistency mode still returns the best row per (tf, method)")


class SmallSampleDoesNotWinOnNoise(unittest.TestCase):
    """A 14-trade row measured at 66% must not outrank a 51-trade row measured at 60%: §39's nested-bootstrap
    spread on 14 trades runs roughly 0..1, so the point estimate is not evidence. Ranking takes the
    conservative end of a flagged-wide estimate (2026-09-19)."""

    def test_a_wide_estimate_is_ranked_at_its_lower_bound(self):
        wide = {"value": 0.662, "low_confidence": True, "spread": {"prop_pass_probability": [0.0025, 1.0]}}
        self.assertAlmostEqual(RS._pass_estimate(wide), 0.0025)

    def test_a_solid_estimate_is_ranked_at_its_value(self):
        solid = {"value": 0.605}
        self.assertAlmostEqual(RS._pass_estimate(solid), 0.605)

    def test_the_bigger_sample_wins_when_the_small_one_is_wide(self):
        small = dict(tf="4H", cfg="C", method="WYCKOFF-BOOK", n=14, failed_by=None,
                     perf={"prop_pass_probability": {"value": 0.662, "low_confidence": True,
                                                     "spread": {"prop_pass_probability": [0.0025, 1.0]}}})
        big = dict(tf="4H", cfg="B", method="WYCKOFF-BOOK", n=51, failed_by=None,
                   perf={"prop_pass_probability": {"value": 0.605}})
        self.assertGreater(RS.prop_key(big), RS.prop_key(small))

    def test_a_wide_estimate_with_no_spread_falls_back_to_its_value(self):
        self.assertAlmostEqual(RS._pass_estimate({"value": 0.4, "low_confidence": True}), 0.4)
        self.assertIsNone(RS._pass_estimate({"unavailable": "n too small"}))
