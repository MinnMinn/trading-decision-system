"""Fix round 3a of docs/audits/2026-09-24-system-audit.md: mechanical Wyckoff rule fidelity (WY-1, WY-2, WY-3,
WY-4, WY-5) plus P7.4 from docs/audits/2026-09-24-wyckoff-label-review.md (wyckoff_bias integrity).

Every "old behaviour" assertion is pinned to PRE_ROUND3 = "cd96591" (the round-2 merge commit), never to HEAD --
after this round's own commit, HEAD is the NEW code, and pinning against HEAD would prove nothing (the same
mistake round 2's dispatcher review caught in test_audit_round2_ict.py).

Fixtures are hand-built OHLCV series tuned so wyckoff_rules.swings()/detect_accumulations() find the exact
structure each finding describes; every tuning choice (which bar gets which volume, which leg is long/short
relative to the lookback average) is explained inline so a reader does not have to re-derive it.
"""
import importlib.util, os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import wyckoff_rules as W          # noqa: E402  -- current (round-3a) engine
import htf_context as HC           # noqa: E402

PRE_ROUND3 = "cd96591"  # the round-2 merge commit -- NOT "HEAD" (see module docstring)


def load_git_revision(ref, name):
    """Loads scripts/`name` as it existed at git ref `ref`, __file__ pinned to the file's CURRENT path so its
    ROOT-relative reads (docs/architecture/analysis-params.json, etc.) resolve against the real repo. Mirrors
    scripts/tests/test_audit_round2_ict.py's load_git_revision."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


def leg(start, end, n, vol=10.0):
    """n bars ramping linearly from `start` to `end` (monotonic close-to-close), each with a small wick so
    high/low bracket open/close. Used to build swing pivots at exact, predictable bar indices for
    wyckoff_rules.swings()(k=3): every leg is long enough that its endpoint is a genuine local extreme."""
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
    """Downtrend -> SC(80) -> 3x CHoBEV -> AR(110.05) -> ST(84.95), CHoCH just completed. No Phase-B bars yet
    -- every fixture below appends its own Phase-B sequence. tr_lo=79.95, tr_hi=110.05, tr=30.1."""
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


def base_accumulation():
    """base_through_choch() plus two confirmed Phase-B swings, all held below tr_hi=110.05. Shared by WY-2,
    WY-4 and WY-5; WY-1 mirrors it for a distribution and WY-3 builds its own Phase-B (a Phase-B UA)."""
    bars = base_through_choch()
    bars += leg(106, 90, 6, vol=10.0)   # Phase-B swing 1 (low)
    bars += leg(90, 100, 6, vol=10.0)   # Phase-B swing 2 (high), still below tr_hi=110.05
    bars += leg(100, 92, 6, vol=10.0)   # Phase-B swing 3 (low) -- b_swings comfortably >= min_phase_b_swings=2
    return bars


def cols(bars):
    O = [b[0] for b in bars]; H = [b[1] for b in bars]; L = [b[2] for b in bars]
    C = [b[3] for b in bars]; V = [b[4] for b in bars]
    return O, H, L, C, V


class WY1UpthrustTableIsSideAware(unittest.TestCase):
    """docs/audits/2026-09-24-system-audit.md WY-1: WYCKOFF-BOOK sorted Upthrusts/UTADs by the Spring volume
    table (Bang 2.1, WMT p049). The Upthrust table (Bang 2.2, WMT p064,
    knowledge/wyckoff/modern-tools.md:66-72) is a DIFFERENT ladder with NO low-volume type. `vol_type()` in
    wyckoff_rules.py is now the one owner (moved from backtest-methods.vtype(), which has no other caller)."""

    def test_spring_ladder_is_ascending_long(self):
        lo = W.VOL["low_max_ratio"]; hi = W.VOL["high_min_ratio"]
        self.assertEqual(W.vol_type(lo - 0.1, "long"), 1)       # Bang 2.1: "Low"
        self.assertEqual(W.vol_type((lo + hi) / 2, "long"), 2)  # "Moderate"
        self.assertEqual(W.vol_type(hi + 0.1, "long"), 3)       # "High -- Shake Out"

    def test_utad_is_type_two_not_type_three(self):
        hi = W.VOL["high_min_ratio"]
        self.assertEqual(W.vol_type(hi + 0.5, "short"), 2, "Bang 2.2: type 2 (UTAD) is 'very high at the extreme'")

    def test_no_low_volume_upthrust_is_refused(self):
        self.assertIsNone(W.vol_type(W.VOL["upthrust_min_ratio"] - 0.01, "short"))
        self.assertIsNone(W.vol_type(0.1, "short"))

    def test_increase_at_the_touch_is_type_one(self):
        self.assertEqual(W.vol_type(W.VOL["upthrust_min_ratio"], "short"), 1)
        self.assertEqual(W.vol_type(W.VOL["high_min_ratio"], "short"), 1)

    def test_backtest_methods_vtype_is_the_same_function_one_owner(self):
        """WY-1's fix critique: 'move the vtype logic into wyckoff_rules so it has one owner.' Assert there is
        exactly one implementation, not two that could drift again."""
        bt = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location("bt_one_owner", os.path.join(ROOT, "scripts", "backtest-methods.py")))
        importlib.util.spec_from_file_location("bt_one_owner", os.path.join(ROOT, "scripts", "backtest-methods.py")).loader.exec_module(bt)
        self.assertIs(bt.vtype, W.vol_type)

    def test_a_half_volume_distribution_break_never_produces_a_fire(self):
        """Integration-level: detect_distributions() must type a below-upthrust_min_ratio break bar as
        vol_type=None (refused), not as Spring type 1 -- so it can never satisfy
        `r["vol_type"] in OPTS["types"]` in backtest-methods._fires_from and fire the spring leg."""
        bars = base_accumulation()
        bars += leg(92, 95, 4)                            # descend a little further, still above tr_lo
        bars += [(95.0, 96.0, 78.0, 82.0, 5.0)]            # spring/break bar: same-bar reclaim, LOW volume
        O, H, L, C, V = cols(bars)
        # Mirror the fixture into detect_distributions' input convention: detect_distributions(O,H,L,C,V)
        # computes inv(O), inv(L), inv(H), inv(C) internally and calls detect_accumulations on THOSE, so
        # feeding it O'=-O, H'=-L, L'=-H, C'=-C reconstructs this exact accumulation-shaped series inside.
        O2 = [-x for x in O]; H2 = [-x for x in L]; L2 = [-x for x in H]; C2 = [-x for x in C]
        recs = W.detect_distributions(O2, H2, L2, C2, V)
        self.assertEqual(len(recs), 1, "the mirrored structure must still be found (price action unchanged)")
        r = recs[0]
        self.assertAlmostEqual(r["vol_ratio"], 0.5, places=2)
        self.assertIsNone(r["vol_type"], "ratio 0.5 < upthrust_min_ratio: not any of the book's three Upthrust "
                                          "types, must be refused rather than relabelled Spring type 1")

    def test_a_utad_short_can_enter_at_the_reclaim_without_waiting_on_the_optional_test(self):
        """WY-1 fix critique gap (1): the reclaim-vs-test leg choice at backtest-methods._fires_from is Spring
        semantics and cannot be reused unchanged for a short. Upthrust type 2 (UTAD)'s 'UTAD Test' retest is
        explicitly optional ('not always present', Bang 2.2, WMT p064) -- pre-fix, vol_type==2 fell through to
        the `r["test"]` branch unconditionally (no `side` check at all), so a UTAD short with no Test bar could
        never fire. Post-fix it enters at the reclaim."""
        old_bt = load_git_revision(PRE_ROUND3, "backtest-methods.py")
        spec = importlib.util.spec_from_file_location("bt_new_wy1", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        new_bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(new_bt)

        C = [100.0, 100.0, 100.0, 100.0, 95.0]; Tm = ["t0", "t1", "t2", "t3", "t4"]
        r = dict(sloped=False, st_pct=0.5, tr_hi=110.0, tr_lo=80.0, spring=0, sos=None, path="spring",
                 shakeout=False, abandon=False, sot_too_strong=False, vol_type=2, reclaim=4, rec_ratio=1.0,
                 spring_low=115.0, test=None, bu=None, st_sign="neutral", phase_b_sign="neutral", ceiling=110.0)

        self.assertEqual(old_bt._fires_from("short", [r], C, Tm), [],
                          f"pre-fix ({PRE_ROUND3}): a UTAD (type 2) short with no Test bar must not fire "
                          "(sanity-checking the OLD behaviour, not the fix)")
        fired = new_bt._fires_from("short", [r], C, Tm)
        self.assertEqual(len(fired), 1, "post-fix: UTAD type 2 enters at the reclaim without an optional Test")
        self.assertEqual(fired[0]["entry"], 95.0)


class WY2SpringReclaimCanFireOnTheLastBar(unittest.TestCase):
    """docs/audits/2026-09-24-system-audit.md WY-2: the Phase-C break search's loop bound (`n - COMMIT`) was
    meant only for the LPS[C] commitment look-ahead, but it also silently made every Spring within the last
    COMMIT(=2) bars of a window invisible -- including a same-bar reclaim exactly on the window's LAST bar,
    which is the only bar wyckoff_fires()/scan() ever reads as a live fire. WA p80, Bang 2.1: Type 1 Spring
    confirmation IS the reclaim close itself."""

    def fixture(self):
        bars = base_accumulation()
        bars += leg(92, 95, 4)                              # descend toward the TR low, still above it
        bars += [(95.0, 96.0, 78.0, 82.0, 5.0)]              # SAME-BAR reclaim: dips to 78 (< tr_lo=79.95),
                                                              # closes 82 (> tr_lo) -- and it is the LAST bar.
        return cols(bars)

    def test_pre_fix_the_same_bar_reclaim_is_invisible(self):
        old = load_git_revision(PRE_ROUND3, "wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        recs = old.detect_accumulations(O, H, L, C, V)
        self.assertEqual(recs, [], f"pre-fix ({PRE_ROUND3}): the break search stops at n-COMMIT-1, two bars "
                                    "short of the window's last bar, so this Spring is never even detected")

    def test_post_fix_the_reclaim_fires_on_the_last_bar(self):
        O, H, L, C, V = self.fixture()
        recs = W.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        last = len(C) - 1
        self.assertEqual(r["spring"], last)
        self.assertEqual(r["reclaim"], last, "type-1 'enter at the reclaim' (WA p80) must be reachable on the "
                                              "window's last bar -- the only bar a live read ever fires on")
        self.assertFalse(r["shakeout"])
        self.assertEqual(r["vol_type"], 1)  # ratio 0.5 -> low volume -> Spring type 1 (Bang 2.1)


class WY3PhaseBCeilingGatesSOS(unittest.TestCase):
    """docs/audits/2026-09-24-system-audit.md WY-3: SOS and the TR top were measured against the AR high
    (tr_hi) only, never updated through Phase B. A close above AR but below a Phase-B UA high is a UA/inside
    range read (WA p85: 'SOS = vuot qua nhung diem cao nhat trong Trading Range'), not an SOS. wyckoff_rules
    now tracks `ceiling` = the highest CONFIRMED Phase-B swing high, and gates the LPS[C]/spring-path SOS test,
    the BU zone and the Phase-D target on it; `tr_hi` stays AR-only for the doi nhan thirds / st_pct."""

    def fixture(self):
        bars = base_through_choch()          # this fixture builds its own Phase-B sequence, culminating in a
                                              # confirmed UA above AR, instead of base_accumulation()'s default
        bars += leg(106, 90, 6, vol=20.0)
        bars += leg(90, 100, 6, vol=20.0)
        bars += leg(100, 88, 6, vol=20.0)
        # UA ascent: LOW-effort (vol well below the 20.0 baseline just built, so it never satisfies the SOS
        # effort test) climb to 118, well above tr_hi=110.05 -- a genuine Phase-B swing high by price action.
        bars += leg(88, 118, 10, vol=5.0)
        # Reversal, also low-effort, so the decline itself is never mistaken for an SOS bar. Gives the 118
        # peak the 3 bars-each-side it needs to confirm as a swing pivot (wyckoff_rules.swings(), k=3).
        bars += leg(118, 95, 8, vol=5.0)
        # The FAKE SOS: a separate, higher-effort rally that closes above tr_hi (110.05) but stays BELOW the
        # now-confirmed ceiling (118, from the UA above). Pre-fix this satisfies `C[b] > tr_hi` and fires an
        # LPS[C] "SOS". Post-fix it must not, because C[b] is not > ceiling(118).
        bars += leg(95, 114, 4, vol=40.0)
        bars += leg(114, 108, 6, vol=10.0)   # pull back inside; nothing else should fire either
        return cols(bars)

    def test_pre_fix_a_mid_range_close_is_mislabelled_sos(self):
        old = load_git_revision(PRE_ROUND3, "wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        recs = old.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1, f"pre-fix ({PRE_ROUND3}): the fake rally closing above the AR-only "
                                        "tr_hi is read as a Phase-C SOS")
        r = recs[0]
        self.assertEqual(r["path"], "lps_c")
        self.assertLess(r["tr_hi"], 118.0, "the mislabelled SOS closed below the Phase-B UA high (118)")

    def test_post_fix_the_same_close_is_refused(self):
        O, H, L, C, V = self.fixture()
        recs = W.detect_accumulations(O, H, L, C, V)
        self.assertEqual(recs, [], "post-fix: the fake rally is below the Phase-B ceiling (118) and must not "
                                    "be read as SOS")


class WY4BULPSStopUsesTheWholePullback(unittest.TestCase):
    """docs/audits/2026-09-24-system-audit.md WY-4: `pull = q` was overwritten by every qualifying pullback
    bar, so bu.low = min(L[pull:entry+1]) started at the LAST qualifying bar and excluded an earlier, deeper
    one. Fix (per the fix critique's timing-neutral formula, which does not also change entry timing):
    bu.low = min(L[sos+1 : entry+1]) -- the whole pullback since the breakout, not just its tail."""

    def fixture(self):
        bars = base_accumulation()
        bars += [(92.0, 116.0, 91.5, 115.0, 25.0)]     # breakout bar (sos_bar): wide spread, high volume
        bars += [(115.0, 117.0, 114.0, 116.0, 20.0)]   # follow-through (COMMIT hold)
        bars += [(112.0, 112.5, 100.0, 111.0, 10.0)]   # P1: DEEP qualifying pullback, low=100.0
        bars += [(111.0, 111.5, 104.0, 110.8, 10.0)]   # P2: shallower qualifying pullback, low=104.0
        bars += [(114.0, 118.0, 113.5, 117.0, 10.0)]   # entry: up-close, low kept OUT of the pullback zone so
                                                        # it is never itself re-qualified as a new pullback bar
        return cols(bars)

    def test_pre_fix_the_stop_sits_above_the_true_pullback_low(self):
        old = load_git_revision(PRE_ROUND3, "wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        recs = old.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertIsNotNone(r["bu"], f"pre-fix ({PRE_ROUND3}) must still form a BU (this test isolates WY-4, "
                                       "not WY-5)")
        self.assertEqual(r["bu"]["low"], 104.0, "pre-fix: pull was overwritten to P2, excluding P1's deeper low")

    def test_post_fix_the_stop_reaches_the_deeper_pullback_bar(self):
        O, H, L, C, V = self.fixture()
        recs = W.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertIsNotNone(r["bu"])
        self.assertEqual(r["bu"]["low"], 100.0, "post-fix: the stop covers the whole pullback since the "
                                                 "breakout, including the deeper P1 bar")


class WY5BULPSVolumeComparesAgainstTheBreakoutBar(unittest.TestCase):
    """docs/audits/2026-09-24-system-audit.md WY-5: the 'lower volume than the SOS' pullback filter compared
    against the LAST confirmation/follow-through bar (`sos`/`lpsc_sos`, always `breakout_bar + COMMIT - 1`),
    not the breakout bar itself that actually passed the V>=avg effort test (WA p83-84: the LPS's volume
    should fall relative to the SOS's effort -- the breakout, not an arbitrary later bar)."""

    def fixture(self):
        bars = base_accumulation()
        bars += [(92.0, 116.0, 91.5, 115.0, 30.0)]     # breakout bar (sos_bar): HIGH volume (30)
        bars += [(115.0, 117.0, 114.0, 116.0, 8.0)]    # follow-through: LOW volume (8) -- only holds the close
        bars += [(112.0, 112.5, 102.0, 111.0, 15.0)]   # P: volume 15, between 8 (follow-through) and 30 (breakout)
        bars += [(114.0, 118.0, 113.5, 117.0, 10.0)]   # entry: up-close, low outside the pullback zone
        return cols(bars)

    def test_pre_fix_the_genuine_pullback_is_rejected_no_trade_at_all(self):
        old = load_git_revision(PRE_ROUND3, "wyckoff_rules.py")
        O, H, L, C, V = self.fixture()
        recs = old.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertIsNone(r["bu"], f"pre-fix ({PRE_ROUND3}): V[P]=15 is not < V[follow-through]=8, so the only "
                                    "qualifying pullback bar is rejected and no Phase-D trade fires at all")

    def test_post_fix_the_pullback_is_accepted_against_the_breakout_bars_volume(self):
        O, H, L, C, V = self.fixture()
        recs = W.detect_accumulations(O, H, L, C, V)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertIsNotNone(r["bu"], "post-fix: V[P]=15 < V[breakout]=30, so the pullback is accepted")
        self.assertEqual(r["bu"]["low"], 102.0)


class P74WyckoffBiasIgnoresAnInvalidatedStructure(unittest.TestCase):
    """docs/audits/2026-09-24-wyckoff-label-review.md P7.4: wyckoff_bias() must not keep returning a direction
    from a structure whose Trading Range border has since been closed beyond -- the exact scenario measured in
    the review (4H accumulation, TR low 4,285.91, last close 4,261.60, below that TR low, yet the code
    returned 'long')."""

    def test_a_closed_below_accumulation_border_withholds_bias(self):
        wy = {"structure": "tích lũy", "phase": "D", "trading_range": {"high": 4350.0, "low": 4285.91}}
        bias, basis = HC.wyckoff_bias(wy, {"last": 4261.60})
        self.assertEqual(bias, "unknown")
        self.assertEqual(basis[0][1], "bias.wy.invalidated")
        text = HC.basis_text(basis, "en")
        self.assertIn("4,285.91", text); self.assertIn("4,261.60", text)

    def test_a_closed_above_distribution_border_withholds_bias(self):
        wy = {"structure": "phân phối", "phase": "C", "trading_range": {"high": 100.0, "low": 80.0}}
        bias, basis = HC.wyckoff_bias(wy, {"last": 105.0})
        self.assertEqual(bias, "unknown")
        self.assertEqual(basis[0][1], "bias.wy.invalidated")

    def test_an_intact_structure_still_returns_its_direction(self):
        wy = {"structure": "tích lũy", "phase": "D", "trading_range": {"high": 4350.0, "low": 4285.91}}
        self.assertEqual(HC.wyckoff_bias(wy, {"last": 4300.0})[0], "long")
        wy2 = {"structure": "phân phối", "phase": "C", "trading_range": {"high": 100.0, "low": 80.0}}
        self.assertEqual(HC.wyckoff_bias(wy2, {"last": 95.0})[0], "short")

    def test_missing_trading_range_still_returns_the_pre_p74_direction(self):
        """No border to check against (e.g. an older narrative with no trading_range) must not newly refuse --
        P7.4 only withholds bias when a border IS known and HAS been closed beyond."""
        wy = {"structure": "tích lũy", "phase": "D"}
        self.assertEqual(HC.wyckoff_bias(wy, {"last": 100.0})[0], "long")


if __name__ == "__main__":
    unittest.main()
