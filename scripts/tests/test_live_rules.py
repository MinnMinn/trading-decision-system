"""The backtest must see exactly what the live scanner saw: the same trailing window, and not one bar more.

A look-ahead bug here is invisible in the results (it just makes them better), so it is pinned by construction:
read_at(i) must depend only on candles[:i+1], which is asserted by mutating the future and re-reading, and by
truncating the candle list at i+1 and checking the read is unchanged (docs/plans/2026-09-13-unify-backtest-with-live-rules.md).

Code-quality review of the first cut (commit acd65c5) found two Critical defects, fixed here:
- read_at must require the FULL live window (len(window) == bars), not merely "enough" bars -- a partial
  window is a window live never produces (different median range/pivots/equilibrium).
- window() must raise IndexError for i outside [0, len(candles)), not silently slice to something plausible.
"""
import importlib.util, os, subprocess, unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def load_git_revision(ref, name):
    """Loads `name` as it existed at git ref `ref`, with __file__ pinned to the file's CURRENT path so
    ROOT-relative reads inside the module (docs/architecture/analysis-params.json, scripts/automation.py, the
    `import wyckoff_rules` on sys.path) resolve against the real repo, not a throwaway temp file. Used to derive
    an expectation from a prior revision's actual behaviour, not from reading today's source."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


def candles(n=800, base=100.0):
    out = []
    for i in range(n):
        out.append({"time": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", "open": base + (i % 3),
                    "high": base + 2 + (i % 7), "low": base - 2 - (i % 5), "close": base + (i % 3),
                    "volume": 10.0})
    return out


class Window(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_window_is_the_live_scan_window_for_that_timeframe(self):
        c = candles()
        w = self.lr.window(c, 700, "15m")
        self.assertEqual(len(w), 576)
        self.assertIs(w[-1], c[700])

    def test_window_is_short_near_the_start_not_padded(self):
        c = candles(100)
        self.assertEqual(len(self.lr.window(c, 40, "15m")), 41)

    def test_window_raises_index_error_for_negative_i(self):
        c = candles(800)
        with self.assertRaises(IndexError):
            self.lr.window(c, -2, "15m")
        with self.assertRaises(IndexError):
            self.lr.window(c, -50, "15m")

    def test_window_raises_index_error_for_i_at_or_past_len_candles(self):
        c = candles(800)
        with self.assertRaises(IndexError):
            self.lr.window(c, len(c), "15m")
        with self.assertRaises(IndexError):
            self.lr.window(c, 1000, "15m")


class ReadAtRequiresFullWindow(unittest.TestCase):
    """Pins Critical 1's fix: read_at must return None until the window is the FULL live window, not merely
    'enough' bars. Both boundary indices are derived from scan_spec(tf)[0] -- not hardcoded -- so this test
    would have caught a MIN_BARS-style partial-window bug for any timeframe, not just the one checked."""

    def setUp(self):
        self.lr = load("live_rules.py")

    def test_read_at_is_none_before_there_are_enough_bars(self):
        self.assertIsNone(self.lr.read_at(candles(20), 10, "15m", methods=("ict",)))

    def test_read_at_is_none_one_bar_short_of_the_full_window(self):
        bars, _ = self.lr.scan_spec("15m")
        c = candles(bars + 50)
        one_short = bars - 2  # index i=bars-2 -> window has bars-1 candles, one short of full
        self.assertIsNone(self.lr.read_at(c, one_short, "15m", methods=("ict",)))

    def test_read_at_returns_a_result_at_the_first_fully_windowed_index(self):
        bars, _ = self.lr.scan_spec("15m")
        c = candles(bars + 50)
        first_full = bars - 1  # index i=bars-1 -> window has exactly `bars` candles
        self.assertIsNotNone(self.lr.read_at(c, first_full, "15m", methods=("ict",)))


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_future_bars_cannot_change_the_read(self):
        c = candles()
        before = self.lr.read_at(c, 700, "15m", methods=("ict",))
        for x in c[701:]:
            x["high"] += 5000; x["low"] -= 5000; x["close"] += 5000
        after = self.lr.read_at(c, 700, "15m", methods=("ict",))
        self.assertEqual(before, after)

    def test_truncating_the_candle_list_at_i_plus_1_reads_the_same(self):
        """Catches a different class of bug than future-mutation: an index computed from len(candles)
        rather than from i would not notice future bars being untouched, but WOULD notice the list
        being shorter."""
        c = candles()
        full = self.lr.read_at(c, 700, "15m", methods=("ict",))
        truncated = self.lr.read_at(c[:701], 700, "15m", methods=("ict",))
        self.assertEqual(full, truncated)


class SetupLookback(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.auto = load("automation.py")

    def test_setup_lookback_matches_live_default_for_every_scanned_timeframe(self):
        """ict-scan.py:466 -- args.setup_lookback or max(12, args.recent * 6). Must be derived from
        SCAN_WINDOW's recent, not hardcoded per timeframe."""
        for tf, w in self.auto.SCAN_WINDOW.items():
            self.assertEqual(self.lr.setup_lookback(tf), max(12, w["recent"] * 6))


class UnknownTimeframe(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_scan_spec_raises_for_a_timeframe_live_never_scans(self):
        """The backtest must fail loudly on a timeframe live doesn't run, not invent a window for it."""
        with self.assertRaises(KeyError):
            self.lr.scan_spec("30m")
        with self.assertRaises(KeyError):
            self.lr.scan_spec("2H")


class BiasMatchesHtfContext(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.htf = load("htf_context.py")

    def test_bias_at_uses_htf_context_not_a_reimplementation(self):
        """methods=("wyckoff",) here, not ("ict",): ("ict",) happens to equal a plausible default, so a
        bias_at that forgot to forward `methods` at all could still pass by accident. wyckoff exercises the
        forwarding for real."""
        c = candles()
        facts = self.lr.read_at(c, 700, "15m", methods=("wyckoff",))
        self.assertEqual(self.lr.bias_at(c, 700, "15m", methods=("wyckoff",)),
                         self.htf.bias_of(None, facts, methods=("wyckoff",)))

    def test_bias_at_accepts_precomputed_facts_instead_of_recomputing(self):
        c = candles()
        facts = self.lr.read_at(c, 700, "15m", methods=("wyckoff",))
        self.assertEqual(self.lr.bias_at(c, 700, "15m", methods=("wyckoff",), facts=facts),
                          self.htf.bias_of(None, facts, methods=("wyckoff",)))


class MethodsIsRequired(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_read_at_without_methods_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.lr.read_at(candles(), 700, "15m")

    def test_bias_at_without_methods_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.lr.bias_at(candles(), 700, "15m")


class HtfGate(unittest.TestCase):
    """The gate strategy-runner.py:525 calls. `legacy` is the pre-2026-09-13 percentile proxy, kept so the two
    can be compared; `live` is htf_context.bias_of."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_live_gate_passes_only_when_the_bias_agrees(self):
        self.assertTrue(self.bt.bias_allows("long", "long"))
        self.assertTrue(self.bt.bias_allows("short", "short"))
        self.assertFalse(self.bt.bias_allows("short", "long"))

    def test_live_gate_refuses_neutral_and_unknown(self):
        self.assertFalse(self.bt.bias_allows("neutral", "long"))
        self.assertFalse(self.bt.bias_allows("unknown", "long"))

    def test_legacy_percentile_gate_is_still_reachable(self):
        self.assertTrue(self.bt.htf_allows([("t", 0.2)], "u", "long"))
        self.assertFalse(self.bt.htf_allows([("t", 0.5)], "u", "long"))

    def test_live_gate_refuses_neutral_and_unknown_on_the_short_side_too(self):
        """Mirrors test_live_gate_refuses_neutral_and_unknown for side='short', so a fix that only special-cased
        the long side would still be caught."""
        self.assertFalse(self.bt.bias_allows("neutral", "short"))
        self.assertFalse(self.bt.bias_allows("unknown", "short"))

    def test_live_gate_refuses_a_missing_bias(self):
        """No bias read at all (facts unavailable) must never be silently treated as permission -- capital
        preservation first."""
        self.assertFalse(self.bt.bias_allows(None, "long"))
        self.assertFalse(self.bt.bias_allows(None, "short"))


class HtfAllowsUnchanged(unittest.TestCase):
    """Guards that htf_allows -- the function strategy-runner.py:525 actually calls as the live order gate --
    was not altered by adding bias_allows alongside it. Expectations come from running a1c75d4's own
    htf_allows (load_git_revision), not from reading the new code: a change that happened to read the same to
    a human reviewer but altered behaviour would still be caught here."""

    def setUp(self):
        self.bt = load("backtest-methods.py")
        self.old = load_git_revision("a1c75d4", "backtest-methods.py")

    def test_htf_allows_matches_a1c75d4_across_representative_percentiles(self):
        cases = [-1.0, -0.2, -0.0001, 0.0, 0.1, 1 / 3, 0.34, 0.5, 2 / 3, 0.6667, 0.9, 1.0, 1.0001, 1.5]
        for pct in cases:
            for side in ("long", "short"):
                htf = [("t", pct)]
                self.assertEqual(
                    self.bt.htf_allows(htf, "u", side),
                    self.old.htf_allows(htf, "u", side),
                    f"pct={pct} side={side}",
                )

    def test_htf_allows_matches_a1c75d4_with_no_htf_bar_before_t(self):
        for side in ("long", "short"):
            self.assertEqual(
                self.bt.htf_allows([], "u", side),
                self.old.htf_allows([], "u", side),
                f"side={side}",
            )


class IctBranchUsesTheLiveScanner(unittest.TestCase):
    """The `--rules`/OPTS["rules"] toggle itself is gone (Task 8, see LegacyEngineIsGone below) -- the ICT branch
    of scan() now unconditionally uses the live scanner, which is what these tests check directly."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_live_ict_setups_come_from_setup_candidate(self):
        """The live entry/stop/target rule is ict-scan.setup_candidate; the backtest must not re-derive one."""
        import inspect
        src = inspect.getsource(self.bt.ict_setups_live)
        self.assertIn("setup_candidate", src)
        self.assertNotIn("find_ict", src)

    def test_live_ict_setups_require_the_limit_to_fill(self):
        """entry is a LIMIT at the FVG near edge. A setup whose limit never filled is not a trade."""
        import inspect
        src = inspect.getsource(self.bt.ict_setups_live)
        self.assertIn("fvg_fill", src)


class IctMethodsResolveFromAutomation(unittest.TestCase):
    """OPTS['methods'] must never be a hardcoded tuple: the default comes from /automation, the same source live
    resolves through (htf_context.engaged_methods_for_market), via the symbol's market (automation.market_of)."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_default_methods_resolve_from_automation_for_the_symbols_market(self):
        market = self.bt._auto.market_of("BTCUSDT")
        expected = self.bt.lr.htf.engaged_methods_for_market(market)
        self.assertIsNone(self.bt.OPTS["methods"])  # no --methods override -> resolve, do not hardcode
        self.assertEqual(self.bt.resolve_methods("BTCUSDT"), expected)

    def test_methods_cli_override_is_used_verbatim_instead_of_resolving(self):
        self.bt.OPTS["methods"] = ("ict",)
        self.assertEqual(self.bt.resolve_methods("BTCUSDT"), ("ict",))


class LiveIctFillCheckActuallyFilters(unittest.TestCase):
    """Proves fvg_fill is not a no-op on real data: some setups the live scanner finds must never come back to
    fill their limit, so the trade count must be strictly less than the setup count. If they are equal, the fill
    check is not doing anything and the whole backtest would be optimistic by construction.

    Uses BTCUSDT 4H, not 1D: verified empirically (2026-09-13) that every complete ICT setup on BTCUSDT 1D over
    the full stored history is long-side with the sweep bar closing in premium of the dealing range, so pd_ok
    rejects all 6 of them (0 reach the fill check at all) -- 1D cannot demonstrate this property on this dataset.
    4H has 30 pd_ok-passing setups and still runs in a few seconds (8,800 bars)."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_trade_count_is_strictly_less_than_setup_count_on_btcusdt_4h(self):
        sym, tf = "BTCUSDT", "4H"
        c, _ = self.bt.load(sym, tf)
        self.assertIsNotNone(c, f"missing fixture data/history/ohlcv.{sym}.{tf}.json")
        methods = self.bt.resolve_methods(sym)
        seen = set()
        for i in range(len(c)):
            a = self.bt.lr.read_at(c, i, tf, methods)
            if a is None:
                continue
            su = self.bt.lr.ict_scan.setup_candidate(a, self.bt.lr.window(c, i, tf), self.bt.lr.setup_lookback(tf))
            if not su or not su.get("complete") or not su.get("pd_ok"):
                continue
            seen.add((su["side"], su["sweep"]["time"], su["mss"]["time"]))
        setup_count = len(seen)
        res = self.bt.scan(sym, tf)
        trade_count = len(res["trades"]["ICT"])
        with open("/tmp/task4-fill-bite.txt", "w") as f:
            f.write(f"symbol={sym} tf={tf} methods={methods}\nsetups={setup_count}\ntrades={trade_count}\n")
        self.assertGreater(setup_count, 0, f"no ICT setups found at all on {sym} {tf} -- cannot prove the fill check bites")
        self.assertLess(trade_count, setup_count)


class LegacyEngineIsGone(unittest.TestCase):
    """Task 8 (2026-09-13): the evidence gate was met (the legacy-vs-live comparison, deleted 2026-09-13 with the
    engine it compared -- docs/plans/2026-09-13-collapse-to-one-system.md Task 4; git history keeps the numbers -- ICT
    profit factor improved on every timeframe measured, legacy blew the account up twice, live never did), so
    the second implementation -- --rules legacy and OPTS["rules"] -- is dead weight that can silently drift back
    into use. These assertions are what make the removal real rather than a flag nobody sets. The
    ed1c8e9-vs-live comparison LegacyRulesUnchanged used to run here is retired along with the branch it
    exercised; the legacy figures it protected are preserved as a report, not as runnable code
    (measured before the comparison document was deleted; docs/plans/2026-09-13-collapse-to-one-system.md Task 4)."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_rules_flag_is_gone(self):
        self.assertNotIn("rules", self.bt.OPTS)

    def test_the_helpers_other_methods_need_are_still_present(self):
        """COMBINED/PARTIAL/COMBINED-BOOK/WYCKOFF still call these, and ict_setups_live calls fvg_fill.
        Deleting them was in an earlier draft of this plan and would have broken four methods.
        ict_target is NOT in this list (see test_ict_target_engine_is_gone below): its only caller was the
        legacy ICT branch this class already asserts is gone, so unlike the names here it has no remaining
        caller to protect (audit 2026-09-13: grep for "ict_target(" outside its own def returns nothing)."""
        for name in ("all_pivots", "last_pivot", "find_ict", "fvg_fill", "is_displacement",
                     "htf_allows", "htf_position", "vtype"):
            self.assertTrue(hasattr(self.bt, name), f"{name} was removed but is still used")

    def test_the_helpers_the_wyckoff_side_needs_are_kept(self):
        for name in ("vtype", "walk", "scan", "simulate", "bias_allows"):
            self.assertTrue(hasattr(self.bt, name), f"{name} was removed but is still used")

    def test_ict_target_engine_is_gone(self):
        """The six-way ICT target-model switch (range/std2/std25/std4/erl_next/irl) was dead: its only caller
        was the legacy ICT branch removed alongside LegacyEngineIsGone above, and the live ICT path
        (ict_setups_live -> live_rules.ict_scan.setup_candidate) takes its target from su["target"], never
        from OPTS["ict_target"] (audit 2026-09-13, docs/plans/2026-09-13-unify-backtest-with-live-rules.md)."""
        self.assertFalse(hasattr(self.bt, "ict_target"), "ict_target() should have been deleted -- it has no caller left")
        self.assertNotIn("ict_target", self.bt.OPTS)


class IctTargetComesFromLiveSetupCandidate(unittest.TestCase):
    """After the ict_target() removal, bt.scan's ICT branch (ict_setups_live) is the ONLY source of an ICT
    trade's target: su["target"] from live_rules.ict_scan.setup_candidate. The invariant is that this path
    reads NOTHING from bt.OPTS -- so no OPTS key, present or future, can move an ICT target.

    Rewritten twice on 2026-09-19. It used to vary ict_disp / ict_pd / std_origin, the three knobs that fed
    the deleted target-model switch; all three were removed from OPTS that day (knowledge audit finding 11),
    so setting them now just inserts keys nothing reads -- which is a weaker test, not a passing one. And its
    fixture (BTCUSDT 4H) went to ZERO ICT trades when the fill window was corrected to the live one, which
    would have made the comparison vacuous rather than failing.

    Fixture: XAUUSD 15m, measured 2026-09-19 as the densest surviving ICT series (17 trades over full
    history, against BTCUSDT 15m 15, BTCUSDT 1H 2, and 0 on every 4H series tested).
    """

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_no_opts_key_can_move_an_ict_target(self):
        sym, tf = "XAUUSD", "15m"
        base = dict(self.bt.OPTS)
        try:
            baseline = self.bt.scan(sym, tf, only=("ICT",))["trades"]["ICT"]
            self.assertGreater(len(baseline), 0,
                               f"no ICT trades on {sym} {tf} -- the fixture has gone empty and this check "
                               f"would pass vacuously; pick a series that still has trades")
            # Every OPTS key the ICT path could plausibly be tempted to read, moved off its default at once.
            self.bt.OPTS.update(types=(1,), range_touches=5, htf=True, entry="test", mgmt="none",
                                sloped_gate=True, st_gate=True, phase_b_gate=True, st_min=0.9,
                                phase_d=False, combined_entry="market")
            varied = self.bt.scan(sym, tf, only=("ICT",))["trades"]["ICT"]
            self.assertEqual(baseline, varied,
                             "ICT trades changed when unrelated OPTS changed -- the live ICT path must be "
                             "independent of bt.OPTS; its rules come from scripts/ict-scan.py")
        finally:
            self.bt.OPTS.clear(); self.bt.OPTS.update(base)

    def test_the_dead_switches_are_not_back(self):
        for dead in ("ict_disp", "ict_pd", "std_origin"):
            self.assertNotIn(dead, self.bt.OPTS)


class ScanOnlyFilterMatchesUnfiltered(unittest.TestCase):
    """A `only=` filter must never silently drop a method nobody excluded from the request -- that would make the
    backtest under-report trades, the same class of silent wrongness this whole plan exists to remove. Runs on
    1D (small, fast) so this stays cheap to run on every review pass."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_unfiltered_scan_matches_scan_with_all_six_methods_named_explicitly(self):
        sym, tf = "BTCUSDT", "1D"
        unfiltered = self.bt.scan(sym, tf)
        filtered = self.bt.scan(sym, tf, only=self.bt.RUNNER_METHODS)
        self.assertEqual(set(unfiltered["trades"].keys()), set(filtered["trades"].keys()))
        for m in self.bt.RUNNER_METHODS:
            self.assertEqual(unfiltered["trades"][m], filtered["trades"][m], m)

    def test_a_single_named_method_matches_its_slice_of_the_unfiltered_scan(self):
        sym, tf = "BTCUSDT", "4H"   # 4H has real COMBINED-BOOK/ICT trades (see LiveIctFillCheckActuallyFilters)
        unfiltered = self.bt.scan(sym, tf)
        for m in self.bt.RUNNER_METHODS:
            filtered = self.bt.scan(sym, tf, only=(m,))
            self.assertEqual(filtered["trades"][m], unfiltered["trades"][m], m)


class ScanOnlySkipsUnwantedWork(unittest.TestCase):
    """The point of `only` is to SKIP computing a method, not compute-then-discard: it must never invoke the live
    ICT scanner when nobody asked for ICT trades -- that unconditional call is what made strategy-runner.replay()
    pay the live-scanner cost on every symbol for a COMBINED-BOOK-only parity check, 27x-ing the test suite
    (code-quality review, 2026-09-13)."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_only_combined_book_never_calls_the_live_ict_scanner(self):
        with mock.patch.object(self.bt.lr, "read_at", wraps=self.bt.lr.read_at) as spy:
            self.bt.scan("BTCUSDT", "1D", only=("COMBINED-BOOK",))
        spy.assert_not_called()

    def test_only_ict_does_call_the_live_ict_scanner(self):
        with mock.patch.object(self.bt.lr, "read_at", wraps=self.bt.lr.read_at) as spy:
            self.bt.scan("BTCUSDT", "1D", only=("ICT",))
        spy.assert_called()

    def test_only_filters_unwanted_methods_out_of_the_trades_dict(self):
        res = self.bt.scan("BTCUSDT", "4H", only=("COMBINED-BOOK",))
        self.assertTrue(set(res["trades"].keys()) <= {"COMBINED-BOOK"}, res["trades"].keys())
        self.assertGreater(len(res["trades"]["COMBINED-BOOK"]), 0, "fixture must exercise a real COMBINED-BOOK trade")


if __name__ == "__main__":
    unittest.main()
