"""Fix round 4a of docs/audits/2026-09-24-system-audit.md: backtest integrity and backtest/live parity
(INT-2, INT-3, INT-4/PAR-2, INT-6/PAR-3, INT-7, INT-8/PAR-7 verification, PAR-4/DEC-4, PAR-8 verification,
WY-3 follow-up, OPTS isolation).

Every "old behaviour" assertion is pinned to PRE_ROUND4A = "cd78200" (the round-3b merge commit that was HEAD
when this round started), never to HEAD -- after this round's own commit, HEAD is the NEW code, and pinning
against HEAD would prove nothing (the same correction round 2's and round 3's own test files already apply).

Several round-4a findings live entirely inside scripts/backtest-methods.py's own control flow (simulate()'s
equity bookkeeping, scan()'s OPTS handling, ict_setups_live()'s trade-record shape) and are tested here by
loading ONLY backtest-methods.py at the pinned revision and MOCKING every call it makes into
scripts/live_rules.py / scripts/ict-scan.py (bt.lr.read_at, bt.lr.ict_scan.setup_candidate, bt.lr.bias_at) --
exactly the pattern scripts/tests/test_audit_round2_ict.py's ICT8BacktestFillWindowAnchoredOnMss already
established. This sidesteps the "loading one sibling module alone silently mixes versions" trap: the mocks
replace live_rules/ict-scan's actual computation, so their on-disk revision is irrelevant to what is being
tested. The one finding that DOES depend on wyckoff_rules.py's own detection logic (the WY-3 follow-up) loads
wyckoff_rules.py alone, exactly as scripts/tests/test_audit_round3_wyckoff.py already does for WY-1/2/4/5 --
wyckoff_rules.py has no internal cross-imports to live_rules/ict-scan/backtest-methods, so a single-module
load cannot mix versions there either.
"""
import importlib.util, os, subprocess, sys, unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PRE_ROUND4A = "cd78200"  # the round-3b merge commit -- NOT "HEAD" (see module docstring)
PRE_ROUND4A_FIX1 = "a746ffc"  # the round-4a commit THIS review found issues in -- the INT-2 tie and the
                              # post-ruin drain (below) were introduced BY round 4a's own INT-2 fix, so their
                              # "pre-fix" state does not exist at cd78200 at all (the heap/pending mechanism
                              # itself is new); it exists only at a746ffc, before this review's own fix round.


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_git_revision(ref, name):
    """Loads scripts/`name` as it existed at git ref `ref`, __file__ pinned to the file's CURRENT path so its
    ROOT-relative reads (docs/architecture/analysis-params.json, etc.) resolve against the real repo. Mirrors
    scripts/tests/test_audit_round2_ict.py's load_git_revision.

    `import wyckoff_rules as W` and the `bt.lr` dynamic load inside the pinned module resolve to whatever is
    ALREADY on disk / already cached in sys.modules -- see the module docstring for why every test here that
    uses this loader either does not depend on that (INT-2, INT-4/PAR-2, PAR-4/DEC-4, OPTS isolation all pass
    plain trade dicts straight to `simulate()`/`scan()` machinery that does not consult wyckoff_rules/live_rules
    at all) or mocks `bt.lr.*` directly (INT-7)."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


def cols(bars):
    O = [b[0] for b in bars]; H = [b[1] for b in bars]; L = [b[2] for b in bars]
    C = [b[3] for b in bars]; V = [b[4] for b in bars]
    return O, H, L, C, V


def leg(start, end, n, vol=10.0):
    """n bars ramping linearly from `start` to `end`, each with a small wick -- mirrors
    scripts/tests/test_audit_round3_wyckoff.py's helper of the same name/shape exactly, so the fixtures below
    build swing pivots at the same predictable bar indices wyckoff_rules.swings()(k=3) expects."""
    out = []
    for i in range(n):
        t = (i + 1) / n
        c = start + (end - start) * t
        o = start + (end - start) * (i / n)
        h = max(o, c) + 0.05
        l = min(o, c) - 0.05
        out.append((o, h, l, c, vol))
    return out


def base_through_choch():
    """Downtrend -> SC(80) -> 3x CHoBEV -> AR(110.05) -> ST(84.95), CHoCH just completed. tr_lo=79.95,
    tr_hi=110.05, tr=30.1. Identical to scripts/tests/test_audit_round3_wyckoff.py's fixture of the same name."""
    bars = []
    bars += leg(104, 102, 5)
    bars += leg(102, 99, 5)
    bars += leg(99, 101, 5)
    bars += leg(101, 97, 5)
    bars += leg(97, 100, 5)
    bars += leg(100, 90, 5)
    bars += leg(90, 96, 5)
    bars += leg(96, 80, 5)           # SC = 80
    bars += leg(80, 110, 6)          # AR = 110.05 (chobev1)
    bars += leg(110, 85, 6)          # ST low = 84.95
    bars += leg(85, 108, 6)          # chobev2 high
    bars += leg(108, 88, 6)          # low
    bars += leg(88, 106, 6)          # chobev3 high -> CHoCH completes
    return bars


class WY3RanAwayGuardUsesPhaseBCeiling(unittest.TestCase):
    """WY-3 follow-up (docs/audits/2026-09-24-system-audit.md fix critique): the 'ran away' guard
    (`H[b] > tr_hi + tr`) still used the AR-only tr_hi even after WY-3's own fix introduced `ceiling` (the
    running Phase-B UA high) for the SOS/BU/target tests. A Phase-B excursion that is itself a legitimate (if
    large) UA -- WA p88-89's own worked examples run a UA well past the AR before the eventual SOS breaks the
    UA itself, not the AR -- was discarded here even though the SOS test right above it would have judged the
    exact same excursion by the Phase-B ceiling, not the AR.

    Fixture: base_through_choch() (tr_lo=79.95, tr_hi=110.05, tr=30.1, old threshold tr_hi+tr=140.15) plus a
    FIRST, low-effort Phase-B UA that climbs to 125 and confirms as a swing high (raising `ceiling` to 125, new
    threshold ceiling+tr=155.1), then a SECOND low-effort push to 150 -- above the OLD threshold (140.15) but
    below the NEW one (155.1) -- then a genuine high-volume/high-spread SOS breakout well above both.
    """

    def fixture(self):
        bars = base_through_choch()
        # Three ordinary, higher-effort Phase-B legs (vol=20) -- confirms b_swings >= min_phase_b_swings=2
        # AND establishes a rolling-average baseline high enough that the two low-effort excursions below
        # (vol=5, vol=3) stay clearly BELOW average for the LPS[C] SOS volume test's whole duration, letting
        # the ran-away check actually run instead (mirrors scripts/tests/test_audit_round3_wyckoff.py's own
        # WY3PhaseBCeilingGatesSOS fixture shape).
        bars += leg(106, 90, 6, vol=20.0)
        bars += leg(90, 100, 6, vol=20.0)
        bars += leg(100, 88, 6, vol=20.0)
        bars += leg(88, 125, 8, vol=5.0)       # first UA ascent, low-effort so it is never itself an SOS
        bars += leg(125, 95, 8, vol=5.0)       # reversal: confirms the 125 peak as a swing high, raising
                                               # `ceiling` to 125 before the second push below
        bars += leg(95, 150, 8, vol=3.0)       # second push: low-effort, ABOVE the OLD threshold
                                               # (tr_hi+tr=140.15) but BELOW the NEW one (ceiling+tr=155.1)
        bars += leg(150, 130, 5, vol=3.0)      # low-effort pullback, keeps the LPS[C] SOS volume test failing
        bars += [(130.0, 205.0, 129.0, 200.0, 40.0)]   # genuine SOS: wide spread + high volume, closes well
                                                        # above both 125 and 150
        bars += [(200.0, 202.0, 199.0, 201.0, 35.0)]   # COMMIT=2 follow-through bar, also closes above ceiling
        return cols(bars)

    def test_pre_fix_the_second_push_is_misread_as_ran_away_and_the_whole_structure_is_discarded(self):
        old = load_git_revision(PRE_ROUND4A, "wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        recs = old.detect_accumulations(O, H, L, C, V)
        self.assertEqual(recs, [], "pre-fix: the AR-only tr_hi+tr threshold trips 'ran away' on the second "
                                    "push (150 > 140.15) before the loop ever reaches the genuine SOS breakout, "
                                    "discarding a structure that WY-3's own SOS test would otherwise accept")

    def test_post_fix_the_structure_survives_to_its_genuine_sos(self):
        W = load("wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        # WY-3 is a property of the Phase-B ceiling, pinned on v1 detection (the fixture's CHoCH sits above the SC-AR
        # box, which W8 -- ON by default since owner 2026-10-05 -- rejects before the walk this test is about).
        recs = W.detect_accumulations(O, H, L, C, V, P=dict(W.PARAMS, fx_w8_choch_in_box=False))
        self.assertEqual(len(recs), 1, "post-fix: the second push (150) stays under ceiling(125)+tr=155.1, so "
                                        "the loop continues to the genuine SOS breakout above 200")
        r = recs[0]
        self.assertEqual(r["path"], "lps_c")
        self.assertGreaterEqual(r["ceiling"], 125.0)


class OPTSIsolationBetweenScanCalls(unittest.TestCase):
    """OPTS isolation (docs/audits/2026-09-24-system-audit.md round-4a finding): OPTS is a mutable module-level
    dict every scan-path function reads as a free variable. Before this fix, a caller that mutated OPTS (a
    config sweep, `scan_for_trader`'s own per-method tightening, or simply an earlier caller in the same
    process) left that mutation as the STARTING point for the next, otherwise-unrelated `scan()` call -- this
    is exactly what produced round 3's false '0 trades' measurement. Reproduced directly: turn on
    `sloped_gate` (which the code's own comments document as cutting WYCKOFF-BOOK structure counts sharply --
    'BTCUSDT 15m, last 20 000 bars: WYCKOFF-BOOK 23 -> 5 structures'), call scan() once so the mutation is left
    on the module global, then call scan() again for an ordinary run."""

    #: Matches the exact example the code's own comments already document ("BTCUSDT 15m, last 20 000 bars:
    #: WYCKOFF-BOOK 23 -> 5 structures") -- large enough for `sloped_gate` to reliably change the count, small
    #: enough (vs. the full ~105 000-bar history) to keep this test file fast.
    BARS = 20000

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")
        cls.bt.limit_bars(cls.BARS)
        c, _ = cls.bt.load("BTCUSDT", "15m")
        if not c:
            raise unittest.SkipTest("no BTCUSDT 15m history on this machine")

    def test_pre_fix_a_stale_mutation_leaks_into_the_next_call(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        old.limit_bars(self.BARS)
        c, _ = old.load("BTCUSDT", "15m")
        if not c:
            self.skipTest("no BTCUSDT 15m history on this machine")
        baseline = old.scan("BTCUSDT", "15m", only=("WYCKOFF-BOOK",))
        n_baseline = len(baseline["trades"]["WYCKOFF-BOOK"])
        old.OPTS["sloped_gate"] = True    # an earlier caller's mutation that never restored OPTS afterward
        leaked = old.scan("BTCUSDT", "15m", only=("WYCKOFF-BOOK",))
        n_leaked = len(leaked["trades"]["WYCKOFF-BOOK"])
        self.assertNotEqual(n_leaked, n_baseline, "pre-fix: the stale sloped_gate=True must silently leak into "
                                                   "a second, otherwise-unrelated scan() call -- there is no "
                                                   "way to ask this scan() for a clean baseline")

    def test_post_fix_opts_param_is_isolated_from_a_stale_mutation(self):
        bt = self.bt
        bt.reset_opts()
        baseline = bt.scan("BTCUSDT", "15m", only=("WYCKOFF-BOOK",), opts={})
        n_baseline = len(baseline["trades"]["WYCKOFF-BOOK"])
        bt.OPTS["sloped_gate"] = True     # an earlier caller's leftover mutation, left dangling on purpose
        try:
            isolated = bt.scan("BTCUSDT", "15m", only=("WYCKOFF-BOOK",), opts={})
        finally:
            bt.reset_opts()
        n_isolated = len(isolated["trades"]["WYCKOFF-BOOK"])
        self.assertEqual(n_isolated, n_baseline, "post-fix: scan(..., opts={}) must ignore the dangling "
                                                  "module-level mutation and run against the canonical baseline")

    def test_reset_opts_restores_the_canonical_baseline(self):
        bt = self.bt
        bt.OPTS["htf"] = True
        bt.OPTS["sides"] = ("long",)
        bt.reset_opts()
        self.assertEqual(bt.OPTS, bt._OPTS_BASE)

    def test_scan_for_trader_isolates_each_methods_own_opts(self):
        """scan_for_trader used to reassign the bare module global around each method's own scan() call and
        restore it by hand in a `finally` -- functionally an inline copy of the exact save/restore dance
        scan()'s own `opts=` parameter now owns. If a per-method tightened OPTS ever leaked into the NEXT
        method's own scan() call within the same scan_for_trader() run, WYCKOFF-BOOK and ICT would silently
        stop being independent -- CLAUDE.md §17 forbids exactly that."""
        bt = self.bt
        bt.reset_opts()
        # WYCKOFF-BOOK only -- ICT's live-scanner path (one ict-scan.analyze() per bar) is exercised by the
        # dedicated INT6PAR3/INT7 tests below via mocking; excluding it here keeps this OPTS-plumbing test fast.
        # "tung" is the one trader id docs/architecture/trader-constraints.json declares.
        result = bt.scan_for_trader("BTCUSDT", "15m", "tung", only=("WYCKOFF-BOOK",))
        self.assertIsNotNone(result)
        self.assertEqual(bt.OPTS, bt._OPTS_BASE, "OPTS must be back at the canonical baseline once "
                                                 "scan_for_trader() returns, not left at the LAST method's own "
                                                 "tightened dict")


def _ict_fixture(mss_i=5, detect_i=6, fill_bar=8, n=40, tf="15m"):
    """A minimal ICT-shaped fixture that drives `ict_setups_live` through mocked `bt.lr.*` calls -- the SAME
    mocking pattern scripts/tests/test_audit_round2_ict.py's ICT8BacktestFillWindowAnchoredOnMss already
    established, reused here so the sibling-module version of live_rules/ict-scan.py is irrelevant to what is
    under test (see this module's own docstring)."""
    H = [200.0] * n; L = [200.0] * n; C = [200.0] * n; O = [200.0] * n
    # Round-4a fix round 1 (code review of a746ffc): wrap hours across days -- htf_bias_gate's call sites now
    # parse this bar's own time via normalized.available_time (datetime.fromisoformat), which raises for an
    # hour >= 24; the old `f"...T{i:02d}:00:00Z"` (valid only for i < 24) silently worked before because
    # available_time() was never actually called on these bars (the pre-review call sites passed Tm[i]
    # unparsed).
    Tm = [f"2026-01-{1 + i // 24:02d}T{i % 24:02d}:00:00Z" for i in range(n)]
    L[fill_bar] = 100.0
    c = [{"time": Tm[i], "open": O[i], "high": H[i], "low": L[i], "close": C[i], "volume": 10.0} for i in range(n)]
    entry, stop, target = 101.0, 50.0, 200.0
    su = {"side": "long", "complete": True, "pd_ok": True,
          "sweep": {"pool": "SSL", "level": 90.0, "time": Tm[mss_i - 1]},
          "mss": {"level": 95.0, "time": Tm[mss_i], "vol_mult": 1.0, "displacement": True, "cisd": None},
          "entry": entry, "stop": stop, "target": target, "R": 2.0,
          "entry_models": {"iofed": entry, "ce": entry - 1, "fill": entry - 2}}
    return H, L, C, O, Tm, c, su


class INT7ICTTradesCarryAnEventId(unittest.TestCase):
    """INT-7 (docs/audits/2026-09-24-system-audit.md): ICT trade records carried no `event` id, so
    simulate()'s one-position-per-symbol rule (`t["entry_time"] < until and t.get("event") != ev`, both sides
    None -> False) never blocked an overlapping ICT trade on the same symbol."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def scenario(self, bt, mss_i=5, detect_i=6, fill_bar=8):
        n, tf = 40, "15m"
        H, L, C, O, Tm, c, su = _ict_fixture(mss_i=mss_i, detect_i=detect_i, fill_bar=fill_bar, n=n)

        def fake_read_at(candles, i, tf_, methods, opts=None):
            return {} if i >= detect_i else None

        with mock.patch.object(bt.lr, "read_at", side_effect=fake_read_at), \
             mock.patch.object(bt.lr.ict_scan, "setup_candidate", return_value=su), \
             mock.patch.object(bt.lr, "bias_at", return_value=("long", None)):
            return bt.ict_setups_live("TESTSYM", tf, c, Tm, bt.P[tf]["H"], H, L, C, ("ict",))

    def test_pre_fix_the_trade_carries_no_event_id(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        out = self.scenario(old)
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].get("event"), "pre-fix: ICT trades carry no event id at all")

    def test_post_fix_the_trade_carries_a_stable_event_id(self):
        out = self.scenario(self.bt)
        self.assertEqual(len(out), 1)
        self.assertIsNotNone(out[0].get("event"), "post-fix: an ICT trade must carry an event id")

    def test_post_fix_two_different_setups_get_two_different_ids(self):
        out1 = self.scenario(self.bt, mss_i=5, detect_i=6, fill_bar=8)
        out2 = self.scenario(self.bt, mss_i=15, detect_i=16, fill_bar=18)
        self.assertNotEqual(out1[0]["event"], out2[0]["event"], "two setups with different sweep/MSS times "
                                                                 "must never collide onto the same event id")

    def test_the_missing_event_id_let_an_overlapping_trade_through(self):
        """The actual mechanism this causes downstream: simulate()'s one-position-per-symbol rule compares
        `t.get("event")`. Two ICT-shaped trades with no event id (None != None -> False) are read as the SAME
        event and BOTH are taken, even though the second opens while the first is still open."""
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        t1 = dict(symbol="BTCUSDT", side="long", entry=100.0, stop=99.0, target=110.0, R=1.0, R_planned=10.0,
                 entry_time="2026-01-01T00:00:00Z", exit_time="2026-01-05T00:00:00Z")
        t2 = dict(symbol="BTCUSDT", side="long", entry=100.0, stop=99.0, target=110.0, R=-1.0, R_planned=10.0,
                 entry_time="2026-01-02T00:00:00Z", exit_time="2026-01-02T01:00:00Z")
        _eq, _curve, taken = old.simulate([t1, t2], 0.00001)
        self.assertEqual(len(taken), 2, "pre-fix: two overlapping no-event trades were BOTH taken")

    def test_the_fix_still_lets_simulate_block_the_overlap(self):
        t1 = dict(symbol="BTCUSDT", side="long", event="BTCUSDT-long-ict-A-B", entry=100.0, stop=99.0,
                 target=110.0, R=1.0, R_planned=10.0, entry_time="2026-01-01T00:00:00Z",
                 exit_time="2026-01-05T00:00:00Z")
        t2 = dict(symbol="BTCUSDT", side="long", event="BTCUSDT-long-ict-C-D", entry=100.0, stop=99.0,
                 target=110.0, R=-1.0, R_planned=10.0, entry_time="2026-01-02T00:00:00Z",
                 exit_time="2026-01-02T01:00:00Z")
        _eq, _curve, taken = self.bt.simulate([t1, t2], 0.00001)
        self.assertEqual(len(taken), 1, "post-fix: the second, DIFFERENT-event trade overlapping the first "
                                        "must still be skipped by the one-position-per-symbol rule")


class INT2EventDrivenEquity(unittest.TestCase):
    """INT-2 (docs/audits/2026-09-24-system-audit.md): simulate() used to book each trade's P&L at ENTRY, in
    entry order, so a LATER trade -- possibly on a different symbol, since the account is shared across
    symbols -- was sized from an EARLIER trade's outcome that had not happened yet. Fixed: every admitted trade
    is queued and its P&L is booked at its own EXIT time, in EXIT order; sizing/account checks use only equity
    already REALISED by a trade's own entry_time.

    Scenario (mirrors the audit's own repro): A (ETHUSDT) enters first and exits LAST, a huge +50R win. B
    (SOLUSDT) enters SECOND, while A is still open, and exits FIRST, a -1R loss. B's entry_time is before A's
    exit_time, so B must be sized on equity that does NOT yet include A's future win.
    """

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def scenario(self):
        a = dict(symbol="ETHUSDT", side="long", entry=100.0, stop=99.0, target=5100.0, R=50.0, R_planned=99.0,
                 entry_time="2026-01-01T00:00:00Z", exit_time="2026-01-05T00:00:00Z", event="a")
        b = dict(symbol="SOLUSDT", side="long", entry=100.0, stop=99.0, target=101.0, R=-1.0, R_planned=99.0,
                 entry_time="2026-01-01T01:00:00Z", exit_time="2026-01-01T02:00:00Z", event="b")
        return [a, b]

    def test_pre_fix_b_is_sized_off_as_not_yet_realised_win(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        trades = self.scenario()
        _eq, _curve, taken = old.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["symbol"] == "SOLUSDT")
        baseline = -(old.START * old.RISK)
        self.assertLess(b_taken["pnl"], baseline * 1.3,
                        "pre-fix: B was sized off equity already inflated by A's not-yet-realised +50R win "
                        "(A is processed first in entry-time order and its pnl is added to equity immediately)")

    def test_post_fix_b_is_sized_off_only_realised_equity(self):
        trades = self.scenario()
        _eq, _curve, taken = self.bt.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["symbol"] == "SOLUSDT")
        expected = -(self.bt.START * self.bt.RISK)
        self.assertAlmostEqual(b_taken["pnl"], expected, delta=abs(expected) * 0.05,
                               msg="post-fix: B must be sized off the STARTING equity -- A has not exited yet "
                                   "as of B's own entry_time")

    def test_pre_fix_max_dd_never_sees_the_real_drawdown(self):
        """The audit's own evidence: 'The curve is [...], but true equity at 02:00 was 9900. max_dd returns
        0.0 where the real drawdown was 1%.' Because equity values are appended in ENTRY order but the curve
        is later sorted by EXIT time, the entry-order-cumulative values happen to already be monotonically
        non-decreasing once re-ordered by exit time in this scenario, so max_dd sees no drawdown at all."""
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        trades = self.scenario()
        _eq, curve, _taken = old.simulate(trades, 0.00001)
        dd = old.max_dd(curve)
        self.assertEqual(dd, 0.0, "pre-fix: the entry-order-booked curve hides B's real, realised drawdown")

    def test_post_fix_max_dd_sees_the_real_drawdown(self):
        trades = self.scenario()
        _eq, curve, _taken = self.bt.simulate(trades, 0.00001)
        dd = self.bt.max_dd(curve)
        self.assertGreater(dd, 0.0, "post-fix: B's real loss, booked at its own exit time, must show up as a "
                                    "real drawdown on the curve")

    def test_post_fix_curve_points_are_in_exit_order(self):
        trades = self.scenario()
        _eq, curve, _taken = self.bt.simulate(trades, 0.00001)
        times = [t for t, _ in curve]
        self.assertEqual(times, sorted(times))
        self.assertEqual(times[0], "2026-01-01T02:00:00Z", "B (the earlier EXIT) must be the first curve point")


class INT4FeeEntryExitSplit(unittest.TestCase):
    """INT-4/PAR-2 (docs/audits/2026-09-24-system-audit.md): configs B/C (stability-report.py) and the flat
    scalar `fee_pct` inside simulate() priced BOTH the entry and the exit leg at the SAME rate, even though
    every exit on this venue is a taker STOP_MARKET/TAKE_PROFIT_MARKET regardless of how the entry was placed.
    Fixed: `entry_order_type` prices the entry leg by the method's own real order type; the exit leg is ALWAYS
    taker, via risk_model.cost_r -- the SAME function strategy-runner.rr_reason() already uses live."""

    def setUp(self):
        self.bt = load("backtest-methods.py")
        import risk_model as RM
        self.RM = RM

    def trade(self, dist_pct=0.002):
        entry = 100.0
        stop = entry * (1 - dist_pct)
        return dict(symbol="BTCUSDT", side="long", entry=entry, stop=stop, target=entry + 10 * (entry - stop),
                   R=10.0, R_planned=10.0, entry_time="2026-01-01T00:00:00Z", exit_time="2026-01-01T01:00:00Z",
                   event="e")

    def test_pre_fix_both_legs_are_priced_at_the_same_rate(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        maker = self.RM.costs("futures", "maker")["fee_pct_per_side"]
        taker = self.RM.costs("futures", "taker")["fee_pct_per_side"]
        self.assertNotEqual(maker, taker, "the fixture assumes maker != taker on this venue")
        t = self.trade()
        _eq, _curve, taken = old.simulate([dict(t)], maker)
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        expected_pre_fix = round(t["R"] - 2 * maker / dist, 3)
        self.assertEqual(taken[0]["net_R"], expected_pre_fix,
                         "pre-fix: simulate() takes ONE scalar fee_pct, charged 2x/dist on both sides")

    def test_post_fix_the_exit_leg_always_pays_taker(self):
        maker = self.RM.costs("futures", "maker")["fee_pct_per_side"]
        taker = self.RM.costs("futures", "taker")["fee_pct_per_side"]
        t = self.trade()
        _eq, _curve, taken = self.bt.simulate([dict(t)], maker, entry_order_type="maker")
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        expected_post_fix = round(t["R"] - (maker + taker) / dist, 3)
        self.assertEqual(taken[0]["net_R"], expected_post_fix,
                         "post-fix: the entry leg pays maker, the exit leg ALWAYS pays taker")
        legacy_convention = round(t["R"] - 2 * maker / dist, 3)
        self.assertLess(taken[0]["net_R"], legacy_convention,
                        "post-fix must charge MORE than the old maker-both-sides convention, since taker > "
                        "maker on this venue")

    def test_a_market_entry_method_pays_taker_on_both_legs(self):
        taker = self.RM.costs("futures", "taker")["fee_pct_per_side"]
        t = self.trade()
        _eq, _curve, taken = self.bt.simulate([dict(t)], taker, entry_order_type="taker")
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        expected = round(t["R"] - 2 * taker / dist, 3)
        self.assertEqual(taken[0]["net_R"], expected, "a WYCKOFF-BOOK-shaped (market-entry) trade pays taker "
                                                       "on both legs, matching the flat scalar formula exactly")

    def test_stability_report_derives_entry_type_from_the_method_not_the_config_letter(self):
        SR = load("stability-report.py")
        b_cfg = SR.CONFIGS["B"]
        self.assertEqual(SR.entry_order_type_for(b_cfg, "ICT"), "maker",
                         "ICT rests a limit -- config B/C must still price it maker")
        self.assertEqual(SR.entry_order_type_for(b_cfg, "WYCKOFF-BOOK"), "taker",
                         "WYCKOFF-BOOK enters at market -- config B/C must NOT price it maker just because "
                         "the config letter says 'maker'")
        a_cfg = SR.CONFIGS["A"]
        self.assertEqual(SR.entry_order_type_for(a_cfg, "ICT"), "taker",
                         "config A prices every method taker/taker on purpose, regardless of method")


class PAR4LiveParitySizing(unittest.TestCase):
    """PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): the backtest's own sizing had no notional cap, no
    2-consecutive-loss halving, and did not include the round-trip fee inside the risk budget -- all three of
    which strategy-runner.size()/mt5_lots() apply live. `live_parity_sizing=True` makes simulate() apply the
    SAME formula via the shared `_risk_scale`."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def tight_stop_trade(self, i, dist_pct=0.001):
        """A very tight stop on BTCUSDT (crypto/futures, which HAS a notional cap) -- tight enough that
        risk_usd/stop_distance would demand a notional far beyond NOTIONAL_CAP_PCT * leverage * equity."""
        entry = 100.0
        stop = entry * (1 - dist_pct)
        return dict(symbol="BTCUSDT", side="long", entry=entry, stop=stop, target=entry + 20 * (entry - stop),
                   R=20.0, R_planned=20.0, entry_time=f"2026-01-0{1 + i}T00:00:00Z",
                   exit_time=f"2026-01-0{1 + i}T01:00:00Z", event=f"e{i}")

    def test_pre_fix_live_parity_sizing_does_not_exist(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        t = self.tight_stop_trade(0)
        with self.assertRaises(TypeError):
            old.simulate([t], 0.0, live_parity_sizing=True)

    def test_post_fix_the_notional_cap_scales_a_tight_stop_down(self):
        t = self.tight_stop_trade(0)
        scale = self.bt._risk_scale("BTCUSDT", t["entry"], t["stop"], self.bt.START, 1.0, "taker", "taker")
        self.assertLess(scale, 1.0, "a 0.1% stop on futures must trigger the notional cap and scale the risk "
                                    "DOWN, exactly as strategy-runner.size() would")
        _eq, _curve, taken = self.bt.simulate([t], 0.0, entry_order_type="taker", live_parity_sizing=True)
        expected = self.bt.START * self.bt.RISK * scale * taken[0]["net_R"]
        self.assertAlmostEqual(taken[0]["pnl"], expected, delta=abs(expected) * 0.001)

    def test_post_fix_a_wide_stop_is_not_capped(self):
        t = self.tight_stop_trade(0, dist_pct=0.30)   # a 30% stop -- nowhere near the notional cap
        scale = self.bt._risk_scale("BTCUSDT", t["entry"], t["stop"], self.bt.START, 1.0, "taker", "taker")
        self.assertAlmostEqual(scale, 1.0, places=3, msg="a wide stop must not be scaled down at all")

    def test_post_fix_the_loss_throttle_halves_size_after_two_losses(self):
        """CFD/MT5 has NO notional cap (mt5_lots only rounds to the broker's lot step), so an XAUUSD loss
        streak isolates the loss-throttle half of `_risk_scale` from the notional-cap half."""
        losers = [dict(symbol="XAUUSD", side="long", entry=100.0, stop=99.0, target=101.0, R=-1.0,
                       R_planned=10.0, entry_time=f"2026-02-{1 + i:02d}T00:00:00Z",
                       exit_time=f"2026-02-{1 + i:02d}T01:00:00Z", event=f"loss{i}") for i in range(4)]
        _eq, _curve, taken = self.bt.simulate(losers, 0.0, entry_order_type="taker", live_parity_sizing=True)
        self.assertEqual(len(taken), 4)
        # Divide out the EQUITY REALISED as of each trade's own turn (sequential, non-overlapping trades, so
        # `taken` is already in the same order equity compounded through) -- not the fixed starting `START`,
        # which would silently fold INT-2's own compounding into what is meant to isolate ONLY the loss
        # throttle.
        equity = self.bt.START
        implied_sizes = []
        for t in taken:
            implied_sizes.append(t["pnl"] / (equity * self.bt.RISK * t["net_R"]))
            equity += t["pnl"]
        self.assertAlmostEqual(implied_sizes[0], 1.0, places=2, msg="1st loss: no throttle yet")
        self.assertAlmostEqual(implied_sizes[1], 1.0, places=2, msg="2nd loss: still no throttle (< 2 PRIOR "
                                                                     "consecutive losses)")
        self.assertAlmostEqual(implied_sizes[2], 0.5, places=2, msg="3rd trade: 2 prior consecutive losses -- "
                                                                     "halved, matching strategy-runner's own "
                                                                     "risk_mult = 0.5 if consec_losses >= 2")
        self.assertAlmostEqual(implied_sizes[3], 0.5, places=2, msg="4th trade: still halved")


class INT6PAR3UnifiedHtfGate(unittest.TestCase):
    """INT-6/PAR-3 (docs/audits/2026-09-24-system-audit.md): the backtest's higher-timeframe gate differed
    completely from live -- ICT had NONE at all, and WYCKOFF-BOOK/COMBINED-BOOK used the legacy rolling-
    percentile proxy (`htf_allows`/`htf_position`) keyed on the Spring/SOS time, not the entry decision time.
    Fixed: `htf_bias_gate` is the SAME `bias_allows(lr.bias_at(...))` function strategy-runner.htf_pass() calls
    live, keyed on the LTF decision bar's own close time, shared by BOTH scan() branches."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_pre_fix_there_is_no_shared_htf_gate_function_at_all(self):
        old = load_git_revision(PRE_ROUND4A, "backtest-methods.py")
        self.assertFalse(hasattr(old, "htf_bias_gate"), "pre-fix: no shared htf gate function exists yet")

    def test_post_fix_htf_bias_gate_agrees_only_on_an_explicit_true(self):
        bt = self.bt
        fake_htf_candles = [{"time": f"2026-01-01T{i:02d}:00:00Z"} for i in range(5)]
        key = ("BTCUSDT", "1H", 5, fake_htf_candles[0]["time"], fake_htf_candles[-1]["time"])
        bt._HTF_TIMES[key] = [f"2026-01-01T{i + 1:02d}:00:00Z" for i in range(5)]   # each bar's close = open+1h
        try:
            with mock.patch.object(bt, "load", return_value=(fake_htf_candles, "x")), \
                 mock.patch.object(bt.lr, "bias_at", return_value=("long", None)):
                self.assertTrue(bt.htf_bias_gate("BTCUSDT", "15m", "long", "2026-01-01T05:00:00Z", ("wyckoff",)))
                self.assertFalse(bt.htf_bias_gate("BTCUSDT", "15m", "short", "2026-01-01T05:00:00Z", ("wyckoff",)))
        finally:
            bt._HTF_TIMES.pop(key, None)

    def test_post_fix_htf_bias_gate_returns_none_when_it_cannot_judge(self):
        bt = self.bt
        with mock.patch.object(bt, "load", return_value=(None, None)):
            self.assertIsNone(bt.htf_bias_gate("BTCUSDT", "15m", "long", "2026-01-01T05:00:00Z", ("wyckoff",)))

    def test_post_fix_ict_setups_live_consults_the_htf_gate_when_asked(self):
        bt = self.bt
        H, L, C, O, Tm, c, su = _ict_fixture()

        def fake_read_at(candles, i, tf_, methods, opts=None):
            return {} if i >= 6 else None

        bt.OPTS["htf"] = True
        try:
            with mock.patch.object(bt.lr, "read_at", side_effect=fake_read_at), \
                 mock.patch.object(bt.lr.ict_scan, "setup_candidate", return_value=su), \
                 mock.patch.object(bt.lr, "bias_at", return_value=("long", None)), \
                 mock.patch.object(bt, "htf_bias_gate", return_value=False) as gate:
                out = bt.ict_setups_live("TESTSYM", "15m", c, Tm, bt.P["15m"]["H"], H, L, C, ("ict",))
            self.assertTrue(gate.called, "the ICT path must consult the shared htf gate when OPTS['htf'] is True")
            self.assertEqual(out, [], "a False htf gate must refuse the setup entirely")
        finally:
            bt.reset_opts()

    def test_post_fix_ict_setups_live_ignores_the_gate_when_htf_is_off(self):
        bt = self.bt
        H, L, C, O, Tm, c, su = _ict_fixture()

        def fake_read_at(candles, i, tf_, methods, opts=None):
            return {} if i >= 6 else None

        bt.reset_opts()
        with mock.patch.object(bt.lr, "read_at", side_effect=fake_read_at), \
             mock.patch.object(bt.lr.ict_scan, "setup_candidate", return_value=su), \
             mock.patch.object(bt.lr, "bias_at", return_value=("long", None)), \
             mock.patch.object(bt, "htf_bias_gate", return_value=False) as gate:
            out = bt.ict_setups_live("TESTSYM", "15m", c, Tm, bt.P["15m"]["H"], H, L, C, ("ict",))
        self.assertFalse(gate.called, "OPTS['htf']=False (the default) must not even consult the gate")
        self.assertEqual(len(out), 1, "the setup must still fire when the htf filter is off")

    def test_the_wyckoff_branch_calls_the_same_shared_gate_function(self):
        # Round-4a fix round 1 (code review of a746ffc), BLOCKING #2: both call sites now pass
        # `_N.available_time(bar, tf)` (the bar's CLOSE) rather than `Tm[...]` (its OPEN) as decision_time --
        # see PAR3HtfGateBoundaryMatchesLive for the full behavioural regression.
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn('htf_bias_gate(sym, tf, side,\n', src,
                     "the WYCKOFF-BOOK/COMBINED-BOOK per-fire block must call the SAME htf_bias_gate the ICT "
                     "branch calls -- not the legacy htf_allows/htf_position pair (kept below only for their "
                     "own standalone regression tests)")
        self.assertIn('_N.available_time(c[last], tf)', src,
                     "the WYCKOFF-BOOK/COMBINED-BOOK call site must key the gate on bar `last`'s own CLOSE, "
                     "not its OPEN (Tm[last])")
        self.assertIn('htf_bias_gate(sym, tf, su["side"],\n', src)
        self.assertIn('_N.available_time(c[i], tf)', src,
                     "the ICT call site must key the gate on bar `i`'s own CLOSE, not its OPEN (Tm[i])")

    def test_config_c_rows_are_no_longer_identical_between_methods_by_construction(self):
        """The observable symptom the audit measured: ICT config-B and config-C rows were byte-identical
        because the ICT branch never read OPTS['htf'] at all. Locked in at the source level: OPTS['htf'] must
        now gate the ICT branch too."""
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        ict_section = src[src.index("def ict_setups_live"):]
        self.assertIn('OPTS["htf"]', ict_section, "ict_setups_live must consult OPTS['htf']")


class INT3CombinedBookNoHindsightEntry(unittest.TestCase):
    """INT-3 (docs/audits/2026-09-24-system-audit.md): COMBINED-BOOK entered at the MSS close whenever
    fvg_fill(...) returned None (price never retraced to the FVG edge within the window) -- a decision that
    can only be made by looking K bars into the future to see whether the retrace happened. Fixed: an unfilled
    limit is not a trade, matching ICT's own live-limit semantics (ict_setups_live already treats a None fill
    this way). runnable=false so this can never reach the pilot selection either way; fixed per CLAUDE.md §37
    regardless."""

    def test_pre_fix_a_none_fill_still_produced_a_market_entry_at_the_mss_close(self):
        old_src = subprocess.check_output(["git", "show", f"{PRE_ROUND4A}:scripts/backtest-methods.py"],
                                          cwd=ROOT, text=True)
        self.assertIn('e_bar, e_px = (fill[0], edge) if fill is not None else (mss, C[mss])', old_src,
                      "pre-fix: a None fill (price never returned) still produced a trade, entered at the "
                      "MSS close -- a decision knowable only by having scanned mss+1..mss+K, i.e. the future")

    def test_post_fix_the_hindsight_fallback_is_gone(self):
        new_src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertNotIn("(mss, C[mss])", new_src, "post-fix: the hindsight market-close fallback must be gone")
        combined_section = new_src[new_src.index('"COMBINED-BOOK" in want and r["reclaim"] is not None'):
                                   new_src.index('# ---------- ICT only ----------')]
        self.assertIn("if fill is None:", combined_section)
        self.assertIn("continue", combined_section)

    def test_post_fix_combined_book_also_books_the_same_bar_stop_loss(self):
        """The ICT-8 fvg_fill() contract (a bar that reaches both the edge and the stop returns
        'filled_and_stopped', not None) must be honoured on the COMBINED-BOOK leg too -- before this fix the
        outcome tag was read from `fill` but never actually consulted (\"the outcome tag is unused here\")."""
        new_src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        combined_section = new_src[new_src.index('"COMBINED-BOOK" in want and r["reclaim"] is not None'):
                                   new_src.index('# ---------- ICT only ----------')]
        self.assertIn('outcome == "filled_and_stopped"', combined_section)

    def test_fvg_fill_itself_is_unchanged_and_still_reports_the_stop_invalidation(self):
        """Sanity anchor: this fix is entirely in the CALLER's decision, not in fvg_fill() itself (ICT-8's own
        fix, already covered by scripts/tests/test_audit_round2_ict.py). A long whose bar reaches both the
        edge and the stop must still come back as 'filled_and_stopped', never None."""
        bt = load("backtest-methods.py")
        H = [100.0, 100.0, 100.0]; L = [100.0, 100.0, 90.0]
        out = bt.fvg_fill("long", 0, 99.0, 101.0, 95.0, H, L, 5, 3)
        self.assertIsNotNone(out)
        self.assertEqual(out[1], "filled_and_stopped")


class PAR8CfdRankingExcludesUnexecutedTimeframes(unittest.TestCase):
    """PAR-8 (docs/audits/2026-09-24-system-audit.md): CFD 30m/2H/5m backtests read Yahoo GC=F/SI=F futures
    history, while live trades MT5 CFD bars (15m/1H/4H, aggregated from the MT5 export). Verified ALREADY
    fixed as of PRE_ROUND4A (commit 8ab4e1d, before this round started): rank-setups.py's CFD_TFS narrows
    ranking to the three timeframes the live system actually trades. Locked in here as a regression guard --
    no code change was needed for this finding in round 4a, only this test."""

    def test_cfd_tfs_matches_the_live_execution_timeframes(self):
        RS = load("rank-setups.py")
        self.assertEqual(RS.CFD_TFS, {"15m", "1H", "4H"})

    def test_a_cfd_30m_row_is_excluded_from_ranking(self):
        RS = load("rank-setups.py")
        rows = [
            {"tf": "30m", "method": "WYCKOFF-BOOK", "n": 999, "ruin": None, "q_pos": 100, "q_worst": 0,
             "stab": 99},
            {"tf": "1H", "method": "WYCKOFF-BOOK", "n": 50, "ruin": None, "q_pos": 60, "q_worst": -1, "stab": 1},
        ]
        eligible = [r for r in rows if r["method"] in RS.RUNNABLE and ("cfd" == "crypto" or r["tf"] in RS.CFD_TFS)]
        self.assertEqual([r["tf"] for r in eligible], ["1H"], "a CFD 30m row (Yahoo futures proxy) must never "
                                                              "be eligible for the pilot selection")

    def test_this_was_already_fixed_before_round_4a_started(self):
        pre = subprocess.check_output(["git", "show", f"{PRE_ROUND4A}:scripts/rank-setups.py"],
                                      cwd=ROOT, text=True)
        self.assertIn('CFD_TFS = {"15m", "1H", "4H"}', pre)


class INT2SameTimestampTieIsConservative(unittest.TestCase):
    """Round-4a fix round 1 (code review of a746ffc), BLOCKING #1: `_flush_through`'s bound comparison was
    `pending[0][0] <= bound` -- a NON-STRICT tie -- so an exit whose exit_time EQUALS a new trade's own
    entry_time was realised BEFORE that trade was sized, even though same-timestamp events cannot be
    ordered (the same reasoning ICT-8 already applies to a same-bar fill+stop). Reviewer repro: A exits
    +50R at 01:00, B enters at 01:00 -- B was sized against equity already inflated by A's same-instant
    win (-150.30 instead of -100.0). Fixed: `_flush_through` now uses STRICT `<`, so a same-timestamp exit
    is treated as NOT YET realised as of the new entry -- the conservative reading, since OHLC/timestamp
    granularity cannot prove otherwise."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def same_symbol_scenario(self):
        a = dict(symbol="ETHUSDT", side="long", entry=100.0, stop=99.0, target=5100.0, R=50.0, R_planned=99.0,
                 entry_time="2026-01-01T00:00:00Z", exit_time="2026-01-01T01:00:00Z", event="a")
        b = dict(symbol="ETHUSDT", side="long", entry=100.0, stop=99.0, target=101.0, R=-1.0, R_planned=99.0,
                 entry_time="2026-01-01T01:00:00Z", exit_time="2026-01-01T02:00:00Z", event="b")
        return [a, b]

    def cross_symbol_scenario(self):
        a = dict(symbol="ETHUSDT", side="long", entry=100.0, stop=99.0, target=5100.0, R=50.0, R_planned=99.0,
                 entry_time="2026-01-01T00:00:00Z", exit_time="2026-01-01T01:00:00Z", event="a")
        b = dict(symbol="SOLUSDT", side="long", entry=100.0, stop=99.0, target=101.0, R=-1.0, R_planned=99.0,
                 entry_time="2026-01-01T01:00:00Z", exit_time="2026-01-01T02:00:00Z", event="b")
        return [a, b]

    def test_pre_this_fix_the_tie_inflates_bs_sizing_same_symbol(self):
        old = load_git_revision(PRE_ROUND4A_FIX1, "backtest-methods.py")
        trades = self.same_symbol_scenario()
        _eq, _curve, taken = old.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["net_R"] < 0)
        baseline = -(old.START * old.RISK)
        self.assertLess(b_taken["pnl"], baseline * 1.2,
                        "pre-this-fix: the same-timestamp tie let A's +50R realise before B was sized")

    def test_pre_this_fix_the_tie_inflates_bs_sizing_cross_symbol(self):
        old = load_git_revision(PRE_ROUND4A_FIX1, "backtest-methods.py")
        trades = self.cross_symbol_scenario()
        _eq, _curve, taken = old.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["symbol"] == "SOLUSDT")
        baseline = -(old.START * old.RISK)
        self.assertLess(b_taken["pnl"], baseline * 1.2,
                        "pre-this-fix: the same-timestamp tie let A's +50R realise before B was sized "
                        "(cross-symbol -- the account is shared across symbols)")

    def test_post_fix_the_tie_does_not_inflate_bs_sizing_same_symbol(self):
        trades = self.same_symbol_scenario()
        _eq, _curve, taken = self.bt.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["net_R"] < 0)
        expected = -(self.bt.START * self.bt.RISK)
        self.assertAlmostEqual(b_taken["pnl"], expected, delta=abs(expected) * 0.05,
                               msg="post-fix: a same-timestamp exit must NOT be treated as already realised")

    def test_post_fix_the_tie_does_not_inflate_bs_sizing_cross_symbol(self):
        trades = self.cross_symbol_scenario()
        _eq, _curve, taken = self.bt.simulate(trades, 0.00001)
        b_taken = next(t for t in taken if t["symbol"] == "SOLUSDT")
        expected = -(self.bt.START * self.bt.RISK)
        self.assertAlmostEqual(b_taken["pnl"], expected, delta=abs(expected) * 0.05,
                               msg="post-fix: a same-timestamp exit on a DIFFERENT symbol must also not be "
                                   "treated as already realised")


class PAR3HtfGateBoundaryMatchesLive(unittest.TestCase):
    """Round-4a fix round 1 (code review of a746ffc), BLOCKING #2: both `htf_bias_gate` call sites passed
    `Tm[...]` (the LTF bar's OPEN, normalized.py:118) as `decision_time`, but `_HTF_TIMES` is built from
    `normalized.available_time` (the CLOSE) -- an apples-to-oranges bisect that silently selected an HTF
    bar one rung too early for any LTF bar whose OPEN falls inside an HTF bar still forming (measured:
    551/2000 BTCUSDT boundary bars differed from live). The reviewer's own boundary case: the 15m bar
    opening at :45 past the hour is the LAST 15m bar before the hourly close -- its OPEN is comfortably
    inside the still-forming HTF hour, but its CLOSE (available_time) is exactly the hourly close. Fixed:
    both call sites now pass `normalized.available_time(bar, tf)`. This drives the backtest gate AND live's
    own `strategy-runner.htf_pass()` (on the SAME causal HTF prefix a live tick would have seen) on real
    :45 15m bars and asserts they agree."""

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")
        cls.sr = load("strategy-runner.py")
        c15, _ = cls.bt.load("BTCUSDT", "15m")
        c1h, _ = cls.bt.load("BTCUSDT", "1H")
        if not c15 or not c1h:
            raise unittest.SkipTest("no BTCUSDT 15m/1H history on this machine")
        cls.c15, cls.c1h = c15, c1h
        cls.methods = cls.bt.resolve_methods("BTCUSDT")

    def _boundary_bars(self, n=15):
        """Indices of :45 15m bars (the last 15m bar before an hourly close), far enough into the series
        that a full live scan window and an HTF prefix both exist."""
        out = []
        for i, x in enumerate(self.c15):
            if i < 500:
                continue
            if x["time"][14:16] == "45":
                out.append(i)
            if len(out) >= n:
                break
        return out

    def _htf_prefix_as_of(self, decision_time):
        """The causal HTF candles a live tick at `decision_time` would have seen -- every 1H bar whose OWN
        close (available_time) is <= decision_time -- mirrors strategy-runner.fetch_candles/drop_forming's
        causal window."""
        return [x for x in self.c1h
               if self.bt._N.available_time(x, "1H").isoformat().replace("+00:00", "Z") <= decision_time]

    def test_backtest_gate_agrees_with_live_htf_pass_on_boundary_bars(self):
        bt, sr = self.bt, self.sr
        boundary = self._boundary_bars()
        self.assertGreater(len(boundary), 0, "fixture must contain at least one :45 15m boundary bar")
        checked = 0
        mismatches = []
        for i in boundary:
            decision_time = bt._N.available_time(self.c15[i], "15m").isoformat().replace("+00:00", "Z")
            htf_prefix = self._htf_prefix_as_of(decision_time)
            if not htf_prefix:
                continue
            for side in ("long", "short"):
                checked += 1
                backtest_gate = bt.htf_bias_gate("BTCUSDT", "15m", side, decision_time, self.methods)
                live_gate = sr.htf_pass("BTCUSDT", side, htf_prefix, "1H")
                if backtest_gate != live_gate:
                    mismatches.append((self.c15[i]["time"], side, backtest_gate, live_gate))
        self.assertGreater(checked, 0, "fixture must yield at least one comparable boundary case")
        self.assertEqual(mismatches, [], f"backtest htf_bias_gate disagreed with live htf_pass on "
                                         f"{len(mismatches)}/{checked} boundary case(s): {mismatches[:5]}")

    def test_pre_this_fix_the_open_time_reading_actually_differs_on_these_bars(self):
        """Pins the defect this fix closes: on the SAME boundary bars, keying the gate on the bar's OPEN
        time (the pre-this-fix call-site argument) disagrees with keying it on the bar's CLOSE (this fix)
        for at least one real case -- otherwise this suite would not be exercising the boundary at all."""
        bt = self.bt
        boundary = self._boundary_bars()
        disagreements = 0
        for i in boundary:
            open_time = self.c15[i]["time"]
            close_time = bt._N.available_time(self.c15[i], "15m").isoformat().replace("+00:00", "Z")
            for side in ("long", "short"):
                using_open = bt.htf_bias_gate("BTCUSDT", "15m", side, open_time, self.methods)
                using_close = bt.htf_bias_gate("BTCUSDT", "15m", side, close_time, self.methods)
                if using_open != using_close:
                    disagreements += 1
        self.assertGreater(disagreements, 0, "the boundary fixture must contain at least one case where "
                                             "the open-time reading and the close-time reading disagree -- "
                                             "otherwise this test cannot demonstrate the pre-fix defect")
        # The call sites themselves are pinned by INT6PAR3UnifiedHtfGate's own sibling test
        # (test_the_wyckoff_branch_calls_the_same_shared_gate_function) -- not duplicated here.


class PostRuinTradesDoNotInflateOrDeflateTheReportedResult(unittest.TestCase):
    """Round-4a fix round 1 (code review of a746ffc), should-fix #4: a failed/ruined account does not keep
    trading, so an already-admitted-but-not-yet-realised trade's FUTURE P&L must not be folded into the
    reported final equity/curve/taken. Before this fix, `simulate()` drained every still-pending trade into
    `equity`/`curve`/`taken` even after a `stopped` break, so the reported result could look better (or
    worse) than the equity the account actually failed at."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def scenario(self):
        # A: opens first and stays open a LONG time (exits well after the ruin below) -- a big win, so if
        # it were (wrongly) drained post-ruin the reported final equity would look much healthier than the
        # equity the account actually failed at.
        a = dict(symbol="ETHUSDT", side="long", entry=100.0, stop=99.0, target=1000.0, R=20.0, R_planned=99.0,
                 entry_time="2026-01-01T00:00:00Z", exit_time="2026-06-01T00:00:00Z", event="a")
        # B: a catastrophic loss (-95R) that realises BEFORE C is admitted, dropping equity under RUIN_FRAC.
        b = dict(symbol="SOLUSDT", side="long", entry=100.0, stop=99.0, target=101.0, R=-95.0, R_planned=99.0,
                 entry_time="2026-01-01T01:00:00Z", exit_time="2026-01-01T02:00:00Z", event="b")
        # C: entry AFTER B's exit (so B is realised first) -- its own admission is what discovers the ruin.
        c = dict(symbol="SOLUSDT", side="long", entry=100.0, stop=99.0, target=101.0, R=-1.0, R_planned=99.0,
                 entry_time="2026-01-01T03:00:00Z", exit_time="2026-01-01T04:00:00Z", event="c")
        return [a, b, c]

    def test_final_equity_is_pinned_at_the_ruin_point(self):
        bt = self.bt
        eq, curve, taken = bt.simulate(self.scenario(), 0.00001)
        self.assertIsNotNone(bt.SIM_LAST["ruin"], "the scenario must actually ruin the account")
        self.assertLess(eq, bt.START * bt.RUIN_FRAC * 1.5,
                        "the reported final equity must reflect the ruin point, not A's future +20R win")

    def test_the_still_open_trade_is_excluded_from_taken(self):
        bt = self.bt
        _eq, _curve, taken = bt.simulate(self.scenario(), 0.00001)
        self.assertNotIn("ETHUSDT", {t["symbol"] for t in taken},
                         "A (still open when the account failed) must not appear in the reported `taken`")

    def test_the_still_open_trade_is_recorded_as_a_separate_diagnostic(self):
        bt = self.bt
        bt.simulate(self.scenario(), 0.00001)
        self.assertIn("ETHUSDT", {t["symbol"] for t in bt.SIM_LAST["post_ruin"]},
                     "the still-open trade must be visible as a diagnostic, just not folded into the "
                     "returned equity/curve/taken")

    def test_pre_this_fix_the_still_open_trade_was_drained_into_the_result(self):
        old = load_git_revision(PRE_ROUND4A_FIX1, "backtest-methods.py")
        _eq, _curve, taken = old.simulate(self.scenario(), 0.00001)
        self.assertIn("ETHUSDT", {t["symbol"] for t in taken},
                     "pre-this-fix: the still-open A was drained into `taken` after the account had "
                     "already failed")


class SizingProfileMatchesLiveForVenue(unittest.TestCase):
    """Round-4a fix round 1 (code review of a746ffc), nit #5: `_SIZING_PROFILE`'s ids are a hand-copied
    restatement of what `account_profile.for_venue(venue, "demo")` resolves live. Pinned here so a rename
    or a second demo profile on either venue fails this test instead of silently mis-sizing a backtest."""

    def test_sizing_profile_matches_for_venue_for_the_demo_environment(self):
        bt = load("backtest-methods.py")
        import account_profile as AP
        self.assertEqual(bt._SIZING_PROFILE["crypto"], AP.for_venue("futures", "demo")["id"])
        self.assertEqual(bt._SIZING_PROFILE["cfd"], AP.for_venue("mt5", "demo")["id"])


if __name__ == "__main__":
    unittest.main()
