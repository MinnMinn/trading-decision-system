"""Fix round 2 of docs/audits/2026-09-24-system-audit.md: ICT detection fidelity (ICT-1, ICT-2, ICT-3, ICT-4,
ICT-5, ICT-6, ICT-8). Each test class below is named after the finding it pins, reproduces the audit's
scenario, and is verified (during development, via scratch scripts diffing against the pre-round-2 revision at
HEAD) to fail on the pre-fix code and pass on the fix. Every fixture is hand-built rather than derived from
`analyze()`'s own natural pivot/sweep/MSS detection wherever that detection is not itself the thing under test,
so each test isolates one finding instead of depending on several interacting mechanisms at once.

Knowledge citations are repeated from the audit/code comments so a reader does not have to cross-reference
docs/audits/2026-09-24-system-audit.md to see why an assertion is a fix and not a preference.
"""
import importlib.util, os, sys, unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_git_revision(ref, name):
    """Loads scripts/`name` as it existed at git ref `ref`, __file__ pinned to the file's CURRENT path so its
    ROOT-relative reads (docs/architecture/analysis-params.json, `import instruments`, etc.) resolve against
    the real repo. Mirrors scripts/tests/test_live_rules.py's load_git_revision -- used here to derive the
    "before" behaviour from the actual pre-round-2 commit rather than a restated claim."""
    import subprocess
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


PRE_ROUND2 = "c1ee513"   # the round-1 merge commit, before round 2's edits -- NOT "HEAD" (dispatcher review
                          # correction: after round 2's own commit, HEAD IS the new code, so "HEAD" pinned
                          # every regression test against itself and silently proved nothing)


def bar(i, o, h, l, cl, v=10.0):
    return {"time": f"2026-01-01T{i:02d}:00:00Z", "open": o, "high": h, "low": l, "close": cl, "volume": v}


def bearish_baseline(n):
    """A candle series with a small, consistently BEARISH body (open > close) so no run of candles is ever
    mistaken for a "bullish contiguous run" by an open==close tie, while H/L still vary slightly per index to
    avoid tie-prone pivots."""
    out = []
    for i in range(n):
        j = i % 4
        out.append(bar(i, 100.5 + j * 0.01, 101.0 + j * 0.01, 99.0 - j * 0.01, 99.5 + j * 0.01))
    return out


class ICT1ClosedThroughIsNeverASweep(unittest.TestCase):
    """A level already broken by a body close must never later be recorded as a liquidity sweep.

    knowledge/ict/core-a.md §4 pattern table: 'Wick trades below the previous low; body closes at or above it |
    MUST NOT: Body close below'. §3.2 R6: a level traded through with body closes is 'a draw that was reached'
    (continuation), not a sweep. R25: a grab is invalidated by a later body close beyond the same level."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self):
        n = 30
        c = bearish_baseline(n)
        c[10] = bar(10, 105.0, 110.0, 104.0, 105.0)   # swing high pivot, level 110.0
        c[15] = bar(15, 109.0, 112.0, 108.0, 111.0)   # body CLOSES through 110.0 -- closed_through, not a sweep
        c[25] = bar(25, 105.0, 115.0, 104.0, 105.0)   # much later: wicks above 110 and closes back below --
                                                       # the bar the pre-fix scan recorded as "swept"
        return c

    def test_pool_is_closed_through_not_swept(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h")
        pool = next(p for p in a["pools"] if p["kind"] == "BSL" and abs(p["level"] - 110.0) < 0.01)
        self.assertEqual(pool["state"], "closed_through")
        self.assertEqual(pool["swept"], -1, "a level closed through by a body close must never be marked swept")
        self.assertEqual(pool["closed_at"], 15)

    def test_closed_through_pool_leaves_unswept_and_the_visible_closed_through_list(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h")
        pool = next(p for p in a["pools"] if p["kind"] == "BSL" and abs(p["level"] - 110.0) < 0.01)
        self.assertNotIn(pool, a["unswept"], "a closed-through level must not act as a pristine dealing-range edge")
        self.assertIn(pool, a["closed_through"], "closed-through levels stay visible (R6: traded through)")

    def test_pre_round2_code_recorded_this_as_swept(self):
        """Regression pin against the actual pre-fix commit, not a restated claim."""
        orig = load_git_revision(PRE_ROUND2, "ict-scan.py")
        a = orig.analyze(self.fixture(), 4, tf="1h")
        pool = next(p for p in a["pools"] if p["kind"] == "BSL" and abs(p["level"] - 110.0) < 0.01)
        self.assertEqual(pool["swept"], 25, "pre-fix behaviour: the later wick+close-back was recorded as the sweep")

    def test_a_genuine_sweep_still_works(self):
        """The fix must not turn every pool into closed_through -- an actual wick-through/close-back sweep,
        with NO intervening body close beyond the level, must still be recorded."""
        n = 20
        c = bearish_baseline(n)
        c[8] = bar(8, 105.0, 110.0, 104.0, 105.0)     # swing high, level 110.0
        c[14] = bar(14, 105.0, 112.0, 104.0, 106.0)   # wick above 110, closes back below -- a real sweep
        a = self.scan.analyze(c, 4, tf="1h")
        pool = next(p for p in a["pools"] if p["kind"] == "BSL" and abs(p["level"] - 110.0) < 0.01)
        self.assertEqual(pool["state"], "swept")
        self.assertEqual(pool["swept"], 14)


class ICT2CausalWindowDropsTheFormingBar(unittest.TestCase):
    """A body close cannot be judged on a candle that has not closed yet (knowledge/ict/core-a.md §2.17, §3.2
    R6/R7; CLAUDE.md §8 availableTime <= decisionTime). `causal_window()` is the function main() now calls
    before analyze()/setup_candidate() ever see the window."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def test_forming_last_bar_is_dropped(self):
        import datetime
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        c = [bar(0, 100, 101, 99, 100)]
        c[0]["time"] = "2026-01-01T00:00:00Z"   # open=now -> available_time = now + 1h > now: still forming
        out = self.scan.causal_window(c, "1H", now)
        self.assertEqual(out, [])

    def test_completed_last_bar_is_kept(self):
        import datetime
        now = datetime.datetime(2026, 1, 1, 2, 0, tzinfo=datetime.timezone.utc)
        c = [bar(0, 100, 101, 99, 100)]
        c[0]["time"] = "2026-01-01T00:00:00Z"   # available_time = 01:00 <= now (02:00): completed
        out = self.scan.causal_window(c, "1H", now)
        self.assertEqual(out, c)

    def test_empty_input_is_returned_unchanged(self):
        import datetime
        self.assertEqual(self.scan.causal_window([], "1H", datetime.datetime.now(datetime.timezone.utc)), [])

    def test_dropping_the_forming_bar_changes_what_analyze_can_see(self):
        """The defect in one demonstration: a forming last candle that closes through a swing high must NOT be
        allowed to produce an MSS/draw event until it has actually closed."""
        import datetime
        n = 13
        c = bearish_baseline(n)
        c[5] = bar(5, 100.0, 105.0, 99.0, 100.0)      # swing high pivot, level 105.0
        c[8] = bar(8, 101.0, 101.0, 98.0, 99.0)       # swing low -- flips bias to -1 (bull-hunting on 105.0)
        # still-forming last candle: open time far in the future relative to `now`, so it can never be "closed"
        # regardless of when this test runs -- and its body closes through the swing high.
        c[12] = {"time": "2099-01-01T00:00:00Z", "open": 104.0, "high": 110.0, "low": 103.0, "close": 108.0, "volume": 10.0}
        now = datetime.datetime.now(datetime.timezone.utc)

        with_forming = self.scan.analyze(c, 4, tf="1H")
        truncated = self.scan.causal_window(c, "1H", now)
        without_forming = self.scan.analyze(truncated, 4, tf="1H")

        self.assertTrue(any(m["i"] == len(c) - 1 for m in with_forming["mss"]),
                        "sanity check: the forming candle's close-through must be visible to analyze() when not dropped")
        self.assertFalse(any(m["i"] == len(c) - 1 for m in without_forming["mss"]),
                         "the still-forming candle's close-through must not be visible once causal_window drops it")


class ICT3PdOkUsesTheEntryPriceNotTheLastClose(unittest.TestCase):
    """knowledge/ict/core-a.md §3.4 R13: 'require entry in the discount (below 0.5)' -- concerns the ENTRY (a
    LIMIT at the FVG near edge), not the latest close. R14/§2.19: PD arrays are framed by the entry too."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture_a_and_c(self):
        c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
        c[2] = bar(2, 112.0, 113.0, 108.0, 112.0)   # sweep bar (fields only matter for the stop=min(L[2:6]) calc)
        a = {
            "pct": 0.80,   # last close sits in PREMIUM of the dealing range
            "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 180.0,
            "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
            "pools": [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old",
                       "state": "swept", "closed_at": None}],
            "unswept": [],
            "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"],
                     "origin": 125.0, "cisd": None, "vol_mult": 1.0}],
            "fvgs_all": [{"type": "bull", "i": 7, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0, "mitigated": False}],
        }
        return a, c

    def test_entry_in_discount_passes_even_though_the_close_is_in_premium(self):
        a, c = self.fixture_a_and_c()
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertIsNotNone(su)
        self.assertTrue(su["complete"], su)
        self.assertEqual(su["entry"], 130.0)
        self.assertAlmostEqual(su["entry_pct"], 0.30, places=4)
        self.assertTrue(a["pct"] >= 0.5, "sanity check: the last close is in premium")
        self.assertTrue(su["pd_ok"],
                        "entry (130, 30% of the 100-200 range) is in the discount -- must pass, even though "
                        "the last close (pct=0.80) is in premium")

    def test_in_discount_display_field_stays_close_based(self):
        """The proposed fix keeps a close-based field for display only."""
        a, c = self.fixture_a_and_c()
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertFalse(su["in_discount"], "in_discount is the close-based display field and must stay close-based")

    def test_pre_round2_code_refused_this_setup(self):
        orig = load_git_revision(PRE_ROUND2, "ict-scan.py")
        a, c = self.fixture_a_and_c()
        su = orig.setup_candidate(a, c, lookback=100)
        self.assertFalse(su["pd_ok"], "pre-fix behaviour: the close-based gate wrongly refused a discount entry")


class ICT4DisplacementOverTheLeg(unittest.TestCase):
    """knowledge/ict/core-a.md §2.16: displacement 'can form in a single candle or in multiple candles'. A
    multi-candle displacement whose smaller, final candle does the breaking must still be recognised as
    displaced -- not scored solely on the breaking candle in isolation."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self):
        c = bearish_baseline(21)
        c[8] = bar(8, 100.0, 105.0, 99.0, 100.0)     # swing high pivot (the level, 105.0)
        c[10] = bar(10, 101.0, 101.0, 98.0, 99.0)    # swing low -- flips bias to -1 (bull-hunting)
        c[11] = bar(11, 100.0, 104.9, 99.0, 104.5)   # strong displacement candle, closes just under the level
        c[12] = bar(12, 104.5, 105.6, 104.4, 105.5)  # small breaking candle -- ALONE fails displacement thresholds
        c[13] = bar(13, 100.0, 106.5, 99.0, 100.0)   # keeps idx12 from registering as its own competing pivot
        return c

    def test_the_breaking_candle_alone_fails_displacement(self):
        """Sanity check pinning the premise: is_disp on candle 12 by itself is False (small body/range)."""
        c = self.fixture()
        H = [x["high"] for x in c]; L = [x["low"] for x in c]; O = [x["open"] for x in c]; C = [x["close"] for x in c]
        rg = H[12] - L[12]
        body_ratio = abs(C[12] - O[12]) / rg
        self.assertLess(rg, 2.4, "the breaking candle's own range must be too small to pass alone")

    def test_leg_displacement_is_recognised(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h")
        m = next(m for m in a["mss"] if m["i"] == 12)
        self.assertTrue(m["disp"], "a multi-candle displacement (candle 11) ending in a small breaking candle "
                                    "(candle 12) must be recognised as displaced")

    def test_pre_round2_code_scored_it_non_displaced(self):
        orig = load_git_revision(PRE_ROUND2, "ict-scan.py")
        a = orig.analyze(self.fixture(), 4, tf="1h")
        m = next(m for m in a["mss"] if m["i"] == 12)
        self.assertFalse(m["disp"], "pre-fix behaviour: only candle 12 alone was checked, and it fails")


class ICT4ContinuesScanningAfterAGrab(unittest.TestCase):
    """A close beyond a swing without displacement is a grab (core-a.md §2.17), not an MSS -- but the scanner
    must keep hunting for a LATER displaced close through the SAME swing, not silently give up until an
    unrelated new pivot happens to form (the exact defect the audit measured: 110/500 rejected candidates on
    BTCUSDT 15m)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self):
        N, PIV = 25, 3
        c = bearish_baseline(N)
        c[10] = bar(10, 100.0, 105.0, 99.0, 100.0)   # swing high (the level)
        c[14] = bar(14, 101.0, 101.0, 98.0, 99.0)    # swing low -- flips bias to -1 (bull-hunting)
        c[22] = bar(22, 104.4, 105.3, 104.0, 105.2)  # GRAB: closes just beyond the level, no displacement
        c[24] = bar(24, 100.0, 111.0, 99.0, 110.0)   # LATER, same swing: genuinely displaced close beyond the level
        # Indices >= N - PIV can never register as a competing swing-high pivot (no right-side neighbours), so
        # the grab and the later displaced close are guaranteed to be evaluated as ordinary bars against
        # `lastH`, never consumed as new pivots that would reset the hunt on their own.
        assert 22 >= N - PIV and 24 >= N - PIV
        return c

    def test_both_the_grab_and_the_later_displaced_close_are_recorded(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h")
        by_i = {m["i"]: m for m in a["mss"]}
        self.assertIn(22, by_i, "the grab must still be visible (display, R25)")
        self.assertFalse(by_i[22]["disp"])
        self.assertIn(24, by_i, "the later displaced close through the SAME swing must be registered")
        self.assertTrue(by_i[24]["disp"])
        self.assertEqual(by_i[22]["level"], by_i[24]["level"], "both must reference the SAME swing level")

    def test_last_displaced_mss_is_the_later_one_not_the_grab(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h")
        self.assertEqual(a["last_displaced_mss"]["i"], 24)

    def test_pre_round2_code_loses_the_later_mss_entirely(self):
        orig = load_git_revision(PRE_ROUND2, "ict-scan.py")
        a = orig.analyze(self.fixture(), 4, tf="1h")
        self.assertEqual([m["i"] for m in a["mss"]], [22],
                         "pre-fix behaviour: bias reset to 0 on the grab, so the later displaced close at 24 "
                         "is never registered at all")


class ICT5BiasReadsOnlyADisplacedMss(unittest.TestCase):
    """knowledge/ict/core-a.md §2.17 / core-b.md §2.2: 'STRUCTURAL FALSIFICATION' means a real MSS
    (displacement); a grab must not be able to set ICT bias on its own."""

    def setUp(self):
        self.htf = load("htf_context.py")

    def facts(self, last_mss=None, last_displaced_mss=None):
        return {"last": 100.0, "last_mss": last_mss, "last_displaced_mss": last_displaced_mss,
                "prev_candle": {"tf": "1h", "pch": 110.0, "pcl": 90.0, "pch_state": "intact", "pcl_state": "intact"}}

    def test_a_grab_alone_does_not_set_bias(self):
        grab = {"type": "bull", "level": 99.0}
        bias, basis = self.htf.ict_bias(self.facts(last_mss=grab, last_displaced_mss=None))
        self.assertEqual(bias, "unknown", "last_mss being a grab (no matching last_displaced_mss) must not set bias")

    def test_a_real_displaced_mss_does_set_bias(self):
        m = {"type": "bull", "level": 99.0}
        bias, basis = self.htf.ict_bias(self.facts(last_mss=m, last_displaced_mss=m))
        self.assertEqual(bias, "long")

    def test_facts_entry_carries_last_displaced_mss(self):
        """ict-scan.facts_entry must actually populate the field ict_bias reads."""
        scan = load("ict-scan.py")
        a = {"last": 100.0, "last_time": "t", "lo": 90.0, "hi": 110.0, "eq": 100.0, "pct": 0.5,
             "last_mss": {"type": "bull", "level": 99.0, "disp": False},
             "last_displaced_mss": None, "nearest_fvg": None, "prev_day": None, "prev_candle": None,
             "unswept": [], "closed_through": [], "events": []}
        entry = scan.facts_entry(a, "CHỜ", None, None, {})
        self.assertIn("last_displaced_mss", entry)
        self.assertIsNone(entry["last_displaced_mss"])


class ICT6FvgTouchIsNotLabelledFilled(unittest.TestCase):
    """knowledge/ict/core-a.md §2.23 IOFED: 'price merely touches the edge and continues' -- a near-edge touch
    is the book's entry model, not a failure/fill. The display text must say so."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self):
        c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
        c[2] = bar(2, 112.0, 113.0, 108.0, 112.0)
        a = {
            "pct": 0.30, "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 130.0,
            "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
            "pools": [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old",
                       "state": "swept", "closed_at": None}],
            "unswept": [],
            "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"],
                     "origin": 125.0, "cisd": None, "vol_mult": 1.0}],
            "fvgs_all": [{"type": "bull", "i": 7, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0, "mitigated": True}],
        }
        return a, c

    def test_touched_fvg_is_not_labelled_filled(self):
        a, c = self.fixture()
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertTrue(su["fvg"]["mitigated"])
        html = self.scan.facts_table("BTCUSDT", a, None, su)
        self.assertNotIn("đã lấp", html, "a near-edge touch (IOFED) must not be labelled 'filled'")
        self.assertIn("đã chạm", html, "a near-edge touch must be labelled 'touched'")

    def test_pre_round2_code_labelled_it_filled(self):
        orig = load_git_revision(PRE_ROUND2, "ict-scan.py")
        a, c = self.fixture()
        su = orig.setup_candidate(a, c, lookback=100)
        html = orig.facts_table("BTCUSDT", a, None, su)
        self.assertIn("đã lấp", html, "pre-fix behaviour: a touch was labelled 'filled'")


class ICT8FvgFillReportsStopInvalidation(unittest.TestCase):
    """knowledge/ict/core-a.md §3.6 R22 / core-b R21: a setup is invalid once its stop level is traded. For a
    long, stop < edge always, so any bar reaching the stop has, in that same bar, already reached the edge --
    fvg_fill must report that instead of silently treating it as 'never triggered'."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def test_same_bar_edge_and_stop_is_filled_and_stopped(self):
        n = 10
        H = [110.0] * n; L = [110.0] * n
        L[3] = 99.0   # reaches both the edge (105) and the stop (100) on the same bar
        out = self.bt.fvg_fill("long", 0, 105.0, 104.0, 100.0, H, L, 8, n)
        self.assertEqual(out, (3, "filled_and_stopped"))

    def test_edge_only_is_plain_filled(self):
        n = 10
        H = [110.0] * n; L = [110.0] * n
        L[3] = 104.5   # reaches the edge (105) but not the stop (100)
        out = self.bt.fvg_fill("long", 0, 105.0, 104.0, 100.0, H, L, 8, n)
        self.assertEqual(out, (3, "filled"))

    def test_never_triggers_is_none(self):
        n = 10
        H = [110.0] * n; L = [110.0] * n
        out = self.bt.fvg_fill("long", 0, 105.0, 104.0, 100.0, H, L, 8, n)
        self.assertIsNone(out)

    def test_short_side_mirrors_the_long_side(self):
        n = 10
        H = [90.0] * n; L = [90.0] * n
        H[3] = 111.0   # reaches both the edge (105) and the stop (110) on the same bar, for a short
        out = self.bt.fvg_fill("short", 0, 105.0, 106.0, 110.0, H, L, 8, n)
        self.assertEqual(out, (3, "filled_and_stopped"))

    def test_pre_round2_code_silently_dropped_the_same_bar_case(self):
        orig = load_git_revision(PRE_ROUND2, "backtest-methods.py")
        n = 10
        H = [110.0] * n; L = [110.0] * n
        L[3] = 99.0
        out = orig.fvg_fill("long", 0, 105.0, 104.0, 100.0, H, L, 8, n)
        self.assertIsNone(out, "pre-fix behaviour: checking the stop first returned None, dropping a real -1R loss")


class ICT8BacktestFillWindowAnchoredOnMss(unittest.TestCase):
    """PAR-7/ICT-8: the backtest's ICT fill window must be anchored on the setup's own MSS bar (matching the
    live runner's own expiry, strategy-runner.ict_live_setups: bars_left = mss_i + K - (n-1)), not on the bar
    the setup happens to become detectable. Otherwise the backtest can book a fill live would already have
    refused as expired."""

    def setUp(self):
        self.bt = load("backtest-methods.py")

    def scenario(self, bt):
        n, tf = 40, "15m"
        K = bt.P[tf]["K"]
        mss_i, detect_i, fill_bar = 5, 15, 25   # fill_bar is inside the OLD i+K window (16..31) but OUTSIDE
                                                 # the correct mss_i+K window (6..21)
        H = [200.0] * n; L = [200.0] * n; C = [200.0] * n; O = [200.0] * n
        Tm = [f"2026-01-01T{i:02d}:00:00Z" for i in range(n)]
        L[fill_bar] = 100.0
        c = [{"time": Tm[i], "open": O[i], "high": H[i], "low": L[i], "close": C[i], "volume": 10.0} for i in range(n)]
        entry, stop, target = 101.0, 50.0, 200.0
        su = {"side": "long", "complete": True, "pd_ok": True,
              "sweep": {"pool": "SSL", "level": 90.0, "time": Tm[mss_i - 1]},
              "mss": {"level": 95.0, "time": Tm[mss_i], "vol_mult": 1.0, "displacement": True, "cisd": None},
              "entry": entry, "stop": stop, "target": target, "R": 2.0,
              "entry_models": {"iofed": entry, "ce": entry - 1, "fill": entry - 2}}

        def fake_read_at(candles, i, tf_, methods, opts=None):
            # B1/Batch-1a: ict_setups_live() now calls lr.read_at(..., opts=fx_opts) -- accept and ignore the
            # extra keyword so this pre-existing mock keeps matching the real signature.
            return {} if i >= detect_i else None

        with mock.patch.object(bt.lr, "read_at", side_effect=fake_read_at), \
             mock.patch.object(bt.lr.ict_scan, "setup_candidate", return_value=su), \
             mock.patch.object(bt.lr, "bias_at", return_value=("long", None)):
            return bt.ict_setups_live("TESTSYM", tf, c, Tm, bt.P[tf]["H"], H, L, C, ("ict",))

    def test_a_fill_past_the_mss_anchored_window_is_refused(self):
        out = self.scenario(self.bt)
        self.assertEqual(out, [], "a fill outside the mss_i+K window must not be booked, even if the setup "
                                   "was only detectable later")

    def test_pre_round2_code_booked_the_expired_fill(self):
        orig = load_git_revision(PRE_ROUND2, "backtest-methods.py")
        out = self.scenario(orig)
        self.assertEqual(len(out), 1, "pre-fix behaviour: the i+K window (anchored on the detection bar) "
                                       "reached the fill live would already have expired")


if __name__ == "__main__":
    unittest.main()
