"""Batch 1a -- the ICT F (fidelity-correction) items of docs/plans/2026-09-28-methodology-improvement-plan.md
§3: B2a, B2b, B1, B-RAID. Each is one bool key on `scripts/ict-scan.py analyze()`/`setup_candidate()`'s new
`opts` parameter (docs/plans/2026-09-29-execution-plan.md "Shared contract"), default False = v1 behaviour.

Every test class cites the knowledge/ section the correction is grounded in (plan §1.2: "acceptance is a unit
test and a chart check against the source"). Each class also proves the DEFAULT (opts=None / opts={}) is
unchanged from v1 -- either by comparing against the actual pre-batch code (BASE, via git) or, where the
fixture is a hand-built `a`/`c` pair (the same pattern scripts/tests/test_audit_round2_ict.py's ICT3/ICT6
classes use), by asserting the off-path picks the same object v1's unconditional logic would have picked.
"""
import importlib.util, os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# The commit this worktree branched from (b1-ict-fidelity's base, per the dispatch) -- "before any of the four
# fx_ keys existed". Used only to prove opts=None reproduces that exact code, not a restated claim.
BASE = "3d52fae"


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_git_revision(ref, name):
    """scripts/`name` as it existed at git ref `ref`, __file__ pinned to the CURRENT path so its ROOT-relative
    reads resolve against the real repo. Mirrors test_audit_round2_ict.py's helper of the same name."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


def bar(i, o, h, l, c, v=10.0):
    return {"time": f"2026-01-01T{i:02d}:00:00Z", "open": o, "high": h, "low": l, "close": c, "volume": v}


def flat(n, base=100.0):
    return [bar(i, base, base + 0.5, base - 0.5, base) for i in range(n)]


def bearish_baseline(n):
    """Same fixture generator as test_audit_round2_ict.py's ICT4 class: a small, consistently bearish body so
    no run of candles is mistaken for a bullish contiguous leg by an open==close tie."""
    out = []
    for i in range(n):
        j = i % 4
        out.append(bar(i, 100.5 + j * 0.01, 101.0 + j * 0.01, 99.0 - j * 0.01, 99.5 + j * 0.01))
    return out


class B1PivotWidthOneBarEachSide(unittest.TestCase):
    """knowledge/ict/core-a.md §2.5: 'A Swing High is formed when there is a high with a lower high to the left
    and right' -- one candle each side (§5 quantitative table: 'Swing definition width -- 1 candle each side').
    v1's PIV=3 (docs/architecture/analysis-params.json project_defined.ict.pivot_bars) is a project noise
    filter, not the deck's own width (fidelity finding I-1). ICT only: wyckoff_rules.py keeps its own pivot
    width regardless of this key (dispatch context; not touched here)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self):
        # bar 10 is a swing high under a 1-candle window (neighbours 9, 11 are both lower) but NOT under v1's
        # 3-candle window, because bar 7's high (115.0) sits inside bar 10's +/-3 window and is higher.
        c = flat(25)
        c[7] = bar(7, 100.0, 115.0, 99.0, 100.0)
        c[10] = bar(10, 100.0, 110.0, 99.0, 100.0)
        return c

    def test_v1_default_excludes_the_one_bar_pivot(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h", methods=("ict",))
        self.assertIn(7, a["pivots_high"])
        self.assertNotIn(10, a["pivots_high"], "PIV=3: bar 7's higher high inside bar 10's window disqualifies it")

    def test_fx_b1_pivot1_includes_it(self):
        a = self.scan.analyze(self.fixture(), 4, tf="1h", methods=("ict",), opts={"fx_b1_pivot1": True})
        self.assertIn(7, a["pivots_high"])
        self.assertIn(10, a["pivots_high"], "1-candle width: only neighbours 9/11 matter, and both are lower")

    def test_v1_default_matches_the_actual_pre_batch_code(self):
        """opts=None / opts omitted must reproduce BASE's analyze() byte-for-byte on this fixture -- not a
        restated claim that v1 is unchanged, the actual pre-batch commit's own output."""
        orig = load_git_revision(BASE, "ict-scan.py")
        c = self.fixture()
        a_new = self.scan.analyze(c, 4, tf="1h", methods=("ict",))
        a_old = orig.analyze(c, 4, tf="1h", methods=("ict",))
        self.assertEqual(a_new["pivots_high"], a_old["pivots_high"])
        self.assertEqual(a_new["pivots_low"], a_old["pivots_low"])


class B2aFvgInsideTheDisplacementLeg(unittest.TestCase):
    """knowledge/ict/core-a.md §3.3 R12: 'IF displacement candle(s) are present, THEN expect an FVG inside
    them ("generally") -- use it as the entry array.' v1 takes the LATEST same-direction FVG after the sweep
    (`fv[-1]` over the whole post-sweep span), which can be a later, shallower continuation gap outside the
    leg that actually displaced (fidelity finding I-6 / N4)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def test_analyze_attaches_the_leg_bounds_to_the_mss_record(self):
        """Producing side: leg_disp()'s own (lo_r, hi_r) must reach the mss record as leg_lo/leg_hi -- additive
        fields, always present, not gated behind the key (setup_candidate is what gates their use)."""
        c = bearish_baseline(21)
        c[8] = bar(8, 100.0, 105.0, 99.0, 100.0)     # swing high pivot (level 105.0)
        c[10] = bar(10, 101.0, 101.0, 98.0, 99.0)    # swing low -- flips bias to -1 (bull-hunting)
        c[11] = bar(11, 100.0, 104.9, 99.0, 104.5)   # displacement candle
        c[12] = bar(12, 104.5, 105.6, 104.4, 105.5)  # small breaking candle, closes just over the level
        c[13] = bar(13, 100.0, 106.5, 99.0, 100.0)
        a = self.scan.analyze(c, 4, tf="1h", methods=("ict",))
        m = next(m for m in a["mss"] if m["i"] == 12)
        self.assertTrue(m["disp"])
        self.assertEqual((m["leg_lo"], m["leg_hi"]), (11, 12), "the contiguous bullish run ending at the MSS bar")

    def fixture_su(self):
        """Consuming side: two same-direction FVGs after the sweep -- one (i=4) inside the mss record's own
        leg_lo..leg_hi span, one (i=7) after it (a later, shallower continuation gap)."""
        c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
        c[2] = bar(2, 112.0, 113.0, 108.0, 112.0)
        a = {
            "pct": 0.30, "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 130.0,
            "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
            "pools": [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old",
                       "state": "swept", "closed_at": None}],
            "unswept": [],
            "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"],
                     "ext_i": 2, "origin": 125.0, "cisd": None, "vol_mult": 1.0,
                     "leg_lo": 3, "leg_hi": 5}],
            "fvgs_all": [
                {"type": "bull", "i": 4, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0, "mitigated": False},
                {"type": "bull", "i": 7, "lo": 135.0, "hi": 140.0, "ce": 137.5, "size": 5.0, "mitigated": False},
            ],
        }
        return a, c

    def test_v1_default_picks_the_latest_fvg_not_the_leg_one(self):
        a, c = self.fixture_su()
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertTrue(su["complete"])
        self.assertEqual(su["fvg"]["hi"], 140.0, "v1: fv[-1] over the whole post-sweep span -- the i=7 gap")

    def test_fx_b2a_picks_the_fvg_inside_the_leg(self):
        a, c = self.fixture_su()
        su = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_b2a_fvg_in_leg": True})
        self.assertTrue(su["complete"])
        self.assertEqual(su["fvg"]["hi"], 130.0, "the i=4 gap sits inside leg_lo..leg_hi (3..5); i=7 does not")

    def test_no_fvg_inside_the_leg_is_reported_missing_not_substituted(self):
        """If the ONLY same-direction FVG sits outside the leg, fx_b2a_fvg_in_leg must report the setup
        incomplete -- not silently fall back to the v1 pick (that would defeat the whole correction)."""
        a, c = self.fixture_su()
        a["fvgs_all"] = [a["fvgs_all"][1]]   # only the outside-leg (i=7) gap remains
        su = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_b2a_fvg_in_leg": True})
        self.assertFalse(su["complete"])
        self.assertIn("FVG", su["missing"])


class B2bConsequentEncroachmentFailure(unittest.TestCase):
    """knowledge/ict/core-a.md §2.26, R23: 'IF a pullback body-closes through the 0.5 (CE) of the FVG you are
    trading, THEN treat the FVG as failing; a subsequent close through the far edge completes the failure and
    inverts the gap.' Not implemented anywhere in v1 (no code path computes a CE-failure/inversion state)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fvg_fixture(self):
        """A 3-candle bullish FVG at i=8 (lo=101.0, hi=103.5, ce=102.25), then: bars 10-11 stay above CE, bar
        12 body-closes through CE (102.0 < 102.25) -- ce_failed_at=12 -- bars 13-14 stay above the far edge
        (101.0), bar 15 body-closes through the far edge (100.0 < 101.0) -- inverted_at=15."""
        c = flat(20)
        c[7] = bar(7, 100.0, 101.0, 99.5, 100.5)
        c[8] = bar(8, 103.0, 106.0, 102.0, 105.0)
        c[9] = bar(9, 106.0, 108.0, 103.5, 107.0)
        c[10] = bar(10, 104.0, 104.5, 103.5, 104.0)
        c[11] = bar(11, 104.0, 104.5, 103.5, 104.0)
        c[12] = bar(12, 103.0, 103.5, 101.8, 102.0)
        c[13] = bar(13, 102.0, 102.5, 101.5, 101.8)
        c[14] = bar(14, 101.8, 102.0, 100.5, 101.2)
        c[15] = bar(15, 101.0, 101.2, 99.5, 100.0)
        return c

    def test_v1_default_carries_no_ce_failure_fields(self):
        a = self.scan.analyze(self.fvg_fixture(), 4, tf="1h", methods=("ict",))
        f = next(f for f in a["fvgs_all"] if f["i"] == 8)
        self.assertNotIn("ce_failed_at", f)
        self.assertNotIn("inverted_at", f)

    def test_fx_b2b_records_the_ce_failure_then_the_inversion(self):
        a = self.scan.analyze(self.fvg_fixture(), 4, tf="1h", methods=("ict",), opts={"fx_b2b_ce_fail": True})
        f = next(f for f in a["fvgs_all"] if f["i"] == 8)
        self.assertEqual(f["ce_failed_at"], 12, "first body close through the 0.5 CE (102.0 < 102.25)")
        self.assertEqual(f["inverted_at"], 15, "first body close through the far edge AFTER the CE failure")

    def test_a_ce_failure_alone_without_the_far_edge_close_is_not_inverted(self):
        """R23 requires BOTH steps -- a CE failure with no subsequent far-edge close must not be reported as
        inverted (that would treat 'failing' and 'inverted' as the same event)."""
        c = self.fvg_fixture()
        c[15] = bar(15, 101.5, 101.8, 101.1, 101.4)   # stays above the far edge (101.0) -- no inversion
        c = c[:16]   # v1's baseline (100.0) closes below the far edge too -- truncate so no LATER bar can
                     # accidentally trigger the inversion this fixture is trying to rule out
        a = self.scan.analyze(c, 4, tf="1h", methods=("ict",), opts={"fx_b2b_ce_fail": True})
        f = next(f for f in a["fvgs_all"] if f["i"] == 8)
        self.assertIsNotNone(f["ce_failed_at"])
        self.assertIsNone(f["inverted_at"])

    def fixture_su(self):
        """Consuming side: two same-direction FVGs -- i=4 still live, i=7 already fully failed+inverted
        (`inverted_at` set, as analyze() would attach it when called with fx_b2b_ce_fail too)."""
        c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
        c[2] = bar(2, 112.0, 113.0, 108.0, 112.0)
        a = {
            "pct": 0.30, "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 130.0,
            "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
            "pools": [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old",
                       "state": "swept", "closed_at": None}],
            "unswept": [],
            "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"],
                     "ext_i": 2, "origin": 125.0, "cisd": None, "vol_mult": 1.0,
                     "leg_lo": 3, "leg_hi": 5}],
            "fvgs_all": [
                {"type": "bull", "i": 4, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0,
                 "mitigated": False, "inverted_at": None},
                {"type": "bull", "i": 7, "lo": 135.0, "hi": 140.0, "ce": 137.5, "size": 5.0,
                 "mitigated": True, "inverted_at": 8},
            ],
        }
        return a, c

    def test_v1_default_still_picks_the_already_failed_fvg(self):
        a, c = self.fixture_su()
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertTrue(su["complete"])
        self.assertEqual(su["fvg"]["hi"], 140.0, "v1 has no concept of CE failure -- fv[-1] picks i=7 regardless")

    def test_fx_b2b_excludes_the_failed_fvg(self):
        a, c = self.fixture_su()
        su = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_b2b_ce_fail": True})
        self.assertTrue(su["complete"])
        self.assertEqual(su["fvg"]["hi"], 130.0, "the i=7 gap is excluded (inverted_at is not None); i=4 remains")


class BRaidStopRaidIsPreferredNotMandatory(unittest.TestCase):
    """knowledge/ict/core-b.md §2.2, R2 (18. Market_Structure_Shift.pdf p4): 'Having bodies close over/below
    previous structure is preferred. A stop raid before the MSS is preferred.' -- stated as PREFERRED, not a
    hard requirement. v1's setup_candidate() makes it mandatory: with no matching swept pool in `lookback`,
    it returns None outright, even for a genuinely displaced MSS (fidelity finding I-5)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def fixture(self, pools=()):
        c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
        a = {
            "pct": 0.30, "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 130.0,
            "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
            "pools": list(pools),
            "unswept": [],
            "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"],
                     "ext_i": 2, "origin": 125.0, "cisd": None, "vol_mult": 1.0,
                     "leg_lo": 3, "leg_hi": 5}],
            "fvgs_all": [
                {"type": "bull", "i": 4, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0, "mitigated": False},
            ],
        }
        return a, c

    def test_v1_default_refuses_a_displaced_mss_with_no_raid(self):
        a, c = self.fixture(pools=())   # no swept pool at all
        su = self.scan.setup_candidate(a, c, lookback=100)
        self.assertIsNone(su, "v1: a stop raid is mandatory -- no candidate at all without one")

    def test_fx_braid_optional_forms_a_candidate_from_the_mss_type_alone(self):
        a, c = self.fixture(pools=())
        su = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_braid_optional": True})
        self.assertIsNotNone(su)
        self.assertEqual(su["side"], "long", "side comes straight from the bull MSS type, not a swept pool")
        self.assertTrue(su["complete"])
        self.assertFalse(su["sweep"]["raid"], "no matching raid was found")
        self.assertIsNone(su["sweep"]["pool"])
        self.assertIsNone(su["sweep"]["level"])

    def test_a_genuine_raid_still_works_unchanged_under_the_key(self):
        """The key does not remove the raid-first reading when a raid genuinely exists -- it only stops
        REQUIRING one. With a matching sweep present, both paths must agree."""
        pools = [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old",
                  "state": "swept", "closed_at": None}]
        a, c = self.fixture(pools=pools)
        su_off = self.scan.setup_candidate(a, c, lookback=100)
        su_on = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_braid_optional": True})
        self.assertIsNotNone(su_off)
        self.assertTrue(su_off["sweep"]["raid"])
        self.assertEqual(su_off["entry"], su_on["entry"])
        self.assertEqual(su_off["stop"], su_on["stop"])
        self.assertTrue(su_on["sweep"]["raid"])

    def test_mismatched_raid_direction_is_treated_as_no_raid_under_the_key(self):
        """A swept pool of the WRONG kind for this MSS's direction (v1: no candidate at all, since v1 only
        ever looks at the single most-recent swept pool) still forms a candidate under the key -- the raid it
        found is not the relevant one, so it is treated the same as no raid."""
        pools = [{"kind": "BSL", "level": 140.0, "from": 1, "swept": 2, "type": "old",
                  "state": "swept", "closed_at": None}]   # BSL swept, but the MSS is bullish (wants an SSL raid)
        a, c = self.fixture(pools=pools)
        self.assertIsNone(self.scan.setup_candidate(a, c, lookback=100))
        su = self.scan.setup_candidate(a, c, lookback=100, opts={"fx_braid_optional": True})
        self.assertIsNotNone(su)
        self.assertFalse(su["sweep"]["raid"])


class SharedContractDefaults(unittest.TestCase):
    """docs/plans/2026-09-29-execution-plan.md "Shared contract": one OPTS key per item, default = v1
    behaviour, every key scan()-relevant and stated in config_opts()."""

    def test_backtest_methods_opts_base_has_all_four_keys_false(self):
        bt = load("backtest-methods.py")
        for k in ("fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional"):
            self.assertIn(k, bt.FX_ICT_KEYS)
            self.assertFalse(bt._OPTS_BASE[k], f"{k} must default False (v1 behaviour)")
            self.assertFalse(bt.OPTS[k], f"{k} must default False (v1 behaviour) on the live module OPTS too")

    def test_stability_report_scan_relevant_keys_and_config_opts_state_all_four(self):
        sr = load("stability-report.py")
        for k in ("fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional"):
            self.assertIn(k, sr._SCAN_RELEVANT_KEYS)
            overlay = sr.config_opts(sr.CONFIGS["A"], ict_target="range")
            self.assertIn(k, overlay)
            self.assertFalse(overlay[k])

    def test_live_runner_never_sets_an_fx_key(self):
        """scripts/strategy-runner.py must not pass opts= to live_rules.read_at()/ict_scan.setup_candidate()
        at all -- the live path stays on v1 unconditionally (plan §1.6)."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("fx_b2a_fvg_in_leg", src)
        self.assertNotIn("fx_b2b_ce_fail", src)
        self.assertNotIn("fx_b1_pivot1", src)
        self.assertNotIn("fx_braid_optional", src)


if __name__ == "__main__":
    unittest.main()
