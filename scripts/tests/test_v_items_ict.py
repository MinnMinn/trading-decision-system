"""Batch 2(a) -- the ICT V (variant) items of docs/plans/2026-09-28-methodology-improvement-plan.md §3, one OPTS key
per item under the shared contract of docs/plans/2026-09-29-execution-plan.md: each key holds one value of the set
DECLARED in scripts/ict-scan.py `V_ICT` (= docs/architecture/v-grid-ict.json), the FIRST (baseline) value is the
default and is v1 behaviour, and the live runner never sets any of them.

Every test class names the knowledge/ source of the item it exercises (rule: every item's test cites its source).
Each class proves (1) the default is v1 -- against the actual pre-batch commit BASE where the fixture is
reachable through a pure function -- and (2) that each non-baseline value changes behaviour on a hand-built fixture.

B4 (HTF level engaged before the LTF MSS) is declared implemented=false in the grid; a test pins that no key was
registered for it. B-MGMT is the EXISTING `mgmt` knob (no new key).
"""
import importlib.util, json, os, subprocess, sys, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# The commit this batch branched from: "before any Batch 2(a) V key existed".
BASE = "dcb3124"
GRID_PATH = os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json")


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_git_revision(ref, name):
    """scripts/`name` as it existed at git ref `ref` (mirrors test_ict_fidelity.py's helper)."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    spec = importlib.util.spec_from_loader(f"{name.replace('-', '_').replace('.py', '')}_{ref}", loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


SCAN = load("ict-scan.py")
BT = load("backtest-methods.py")
V = SCAN.V_ICT


def bar(i, o, h, l, c, v=10.0):
    return {"time": f"2026-01-01T{i:02d}:00:00Z", "open": o, "high": h, "low": l, "close": c, "volume": v}


# ---------------------------------------------------------------------------------------------------------------
# setup_candidate() fixtures (the pattern of test_ict_fidelity.py): a hand-built analysis `a` and window `c`.
# ---------------------------------------------------------------------------------------------------------------
def long_fixture():
    """Long: SSL 110 swept at bar 2 (wick low 108), bullish MSS at bar 5, FVG 125-130 (CE 127.5), leg origin 125 /
    extreme 105 (leg 20 -> -2 sigma = 165, -2.25 = 170, -2.5 = 175), one unswept BSL at 160 above the entry."""
    c = [bar(i, 150.0, 151.0, 149.0, 150.0) for i in range(10)]
    c[2] = bar(2, 112.0, 113.0, 108.0, 112.0)
    a = {
        "pct": 0.30, "lo": 100.0, "hi": 200.0, "eq": 150.0, "last": 130.0,
        "window_lo": 95.0, "window_hi": 205.0, "dr_source": "pools",
        "pools": [{"kind": "SSL", "level": 110.0, "from": 1, "swept": 2, "type": "old", "state": "swept", "closed_at": None}],
        "unswept": [{"kind": "BSL", "level": 160.0, "from": 0, "swept": -1, "type": "old", "state": "intact", "closed_at": None}],
        "mss": [{"type": "bull", "i": 5, "level": 120.0, "disp": True, "ext": 105.0, "ext_time": c[2]["time"], "ext_i": 2,
                 "origin": 125.0, "cisd": None, "vol_mult": 1.0, "leg_lo": 3, "leg_hi": 5}],
        "fvgs_all": [{"type": "bull", "i": 4, "lo": 125.0, "hi": 130.0, "ce": 127.5, "size": 5.0, "mitigated": False}],
    }
    return a, c


def mirror(a, c):
    """The exact short mirror of long_fixture(): every price p -> 300 - p, highs/lows swapped."""
    m = lambda p: 300.0 - p
    c2 = [dict(x, open=m(x["open"]), close=m(x["close"]), high=m(x["low"]), low=m(x["high"])) for x in c]
    a2 = dict(a, pct=1 - a["pct"], lo=m(a["hi"]), hi=m(a["lo"]), last=m(a["last"]),
              window_lo=m(a["window_hi"]), window_hi=m(a["window_lo"]))
    a2["pools"] = [dict(p, kind="BSL", level=m(p["level"])) for p in a["pools"]]
    a2["unswept"] = [dict(p, kind="SSL", level=m(p["level"])) for p in a["unswept"]]
    a2["mss"] = [dict(x, type="bear", level=m(x["level"]), ext=m(x["ext"]), origin=m(x["origin"])) for x in a["mss"]]
    a2["fvgs_all"] = [dict(f, type="bear", lo=m(f["hi"]), hi=m(f["lo"]), ce=m(f["ce"])) for f in a["fvgs_all"]]
    return a2, c2


def sc(a, c, **opts):
    return SCAN.setup_candidate(a, c, lookback=100, opts=opts or None)


def true_range_mean(c, end, period=14):
    """Independent ATR: simple mean of the true range over the `period` bars ending at `end`."""
    trs = []
    for j in range(max(0, end - period + 1), end + 1):
        tr = c[j]["high"] - c[j]["low"]
        if j > 0:
            tr = max(tr, abs(c[j]["high"] - c[j - 1]["close"]), abs(c[j]["low"] - c[j - 1]["close"]))
        trs.append(tr)
    return sum(trs) / len(trs)


class DeclaredValueSets(unittest.TestCase):
    """The code-side declaration V_ICT, its validation, and its defaults."""

    def test_baseline_is_the_first_value_and_the_default(self):
        for k, vals in V.items():
            self.assertEqual(SCAN.V_ICT_DEFAULTS[k], vals[0])
            self.assertEqual(BT.OPTS[k], vals[0], k)
            self.assertEqual(BT._OPTS_BASE[k], vals[0], k)

    def test_validation_accepts_every_declared_value_and_refuses_anything_else(self):
        for k, vals in V.items():
            for v in vals:
                SCAN.check_v_opts({k: v})
            for bad in (True, False, None, "", "bogus"):
                with self.assertRaises(ValueError, msg=f"{k}={bad!r}"):
                    SCAN.check_v_opts({k: bad})

    def test_joint_exit_factor_is_24_value_sets_and_lookback_by_k_is_6(self):
        self.assertEqual(len(V["fx_b_exit"]), 3 * 4 * 2)
        self.assertEqual(len(set(V["fx_b_exit"])), 24)
        self.assertEqual(V["fx_b_exit"][0], "-2.0|H|floor")
        self.assertEqual(len(V["fx_b_lb"]), 3 * 2)
        self.assertEqual(V["fx_b_lb"][0], "12|K")

    def test_engine_refuses_an_undeclared_value_instead_of_silently_running_the_baseline(self):
        with mock.patch.dict(BT.OPTS, {"fx_b_ex": True}):
            with self.assertRaises(ValueError):
                BT.ict_setups_live("XAUUSD", "1H", [], [], 72, [], [], [], ("ict",))


class GridFileAndNCount(unittest.TestCase):
    """docs/architecture/v-grid-ict.json is the machine-readable grid another agent reads; N is asserted here."""

    @classmethod
    def setUpClass(cls):
        with open(GRID_PATH, encoding="utf-8") as fh:
            cls.grid = json.load(fh)
        cls.items = {i["id"]: i for i in cls.grid["items"]}

    def test_shape(self):
        self.assertEqual(self.grid["method"], "ICT")
        for it in self.grid["items"]:
            for f in ("id", "key", "existing_opts_key", "values", "joint_group", "source", "implemented"):
                self.assertIn(f, it, it["id"])
            self.assertIsInstance(it["implemented"], bool)
            self.assertEqual(len(it["values"]), len(set(it["values"])), it["id"])
            if not it["implemented"]:
                self.assertTrue(it.get("reason"), f"{it['id']} is implemented=false and must say why")
        self.assertNotIn("B-DISP", self.items, "B-DISP is sensitivity-only: not a V key, not in N")

    def test_every_implemented_fx_key_value_set_equals_the_code_declaration(self):
        for it in self.grid["items"]:
            if it["key"].startswith("fx_") and it["implemented"]:
                self.assertEqual(tuple(it["values"]), V[it["key"]], it["id"])
        self.assertEqual({i["key"] for i in self.grid["items"] if i["key"].startswith("fx_") and i["implemented"]}, set(V))

    def test_b_mgmt_maps_onto_the_existing_knob_and_adds_no_fx_key(self):
        it = self.items["B-MGMT"]
        self.assertEqual(it["existing_opts_key"], "mgmt")
        self.assertEqual(it["values"], ["none", "be"])
        self.assertIn("mgmt", BT.OPTS)
        self.assertFalse(any(k.startswith("fx_") and "mgmt" in k for k in BT.OPTS))

    def test_b4_is_declared_unimplemented_and_no_key_was_registered_for_it(self):
        it = self.items["B4"]
        self.assertFalse(it["implemented"])
        self.assertNotIn(it["key"], BT.OPTS)
        self.assertNotIn(it["key"], V)

    def test_n_is_41(self):
        """N = 1 baseline + non-baseline values + 1 combined. Each item is ONE factor: the joint exit factor
        B-EXIT is one item of 24 value sets (23 non-baseline), B-LB one item of 6 (5 non-baseline)."""
        non_baseline = {i["id"]: len(i["values"]) - 1 for i in self.grid["items"]}
        self.assertEqual(non_baseline["B-EXIT"], 23)
        self.assertEqual(non_baseline["B-LB"], 5)
        self.assertEqual(sum(non_baseline.values()), 39)
        self.assertEqual(1 + sum(non_baseline.values()) + 1, 41)
        self.assertEqual(self.grid["n"], 41)
        self.assertEqual(set(non_baseline), {"B-EX", "B-PD", "B-POOL", "B-BUF", "B-EXIT", "B-LB", "B6", "B3", "B4", "B-MGMT", "B7"})


class RegistrationInAllPlaces(unittest.TestCase):
    """Shared contract rules 2-3: _OPTS_BASE/OPTS, _SCAN_RELEVANT_KEYS, config_opts, the config snapshot."""

    def test_backtest_methods(self):
        self.assertEqual(set(BT.FX_ICT_V_KEYS), set(V))
        for k in V:
            self.assertIn(k, BT._OPTS_BASE)
            self.assertIn(k, BT.OPTS)

    def test_stability_report_scan_relevant_keys_and_config_opts(self):
        sr = load("stability-report.py")
        overlay = sr.config_opts(sr.CONFIGS["A"], ict_target="range")
        for k, vals in V.items():
            self.assertIn(k, sr._SCAN_RELEVANT_KEYS)
            self.assertEqual(overlay[k], vals[0], f"config_opts must state {k}'s v1 default")

    def test_scan_cache_key_separates_two_values(self):
        sr = load("stability-report.py")
        base = sr.config_opts(sr.CONFIGS["A"], ict_target="range")
        k0 = sr._scan_cache_key("XAUUSD", "1H", base, ("ict",))
        for k, vals in V.items():
            k1 = sr._scan_cache_key("XAUUSD", "1H", dict(base, **{k: vals[-1]}), ("ict",))
            self.assertNotEqual(k0, k1, f"{k}: two values must never share a scan-cache entry")

    def test_config_snapshot_records_every_key(self):
        import snapshot
        fields = snapshot.backtest_config_snapshot(BT, timeframes=["1H"], methods={"ICT"}, market="crypto")["fields"]
        cc = fields["custom_constraints"]
        for k, vals in V.items():
            self.assertEqual(cc.get(k), vals[0], k)

    def test_every_key_has_a_reader_on_the_scan_or_simulate_path(self):
        bt_src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        scan_src = open(os.path.join(ROOT, "scripts", "ict-scan.py"), encoding="utf-8").read()
        readers = {"fx_b_ex": 'opts.get("fx_b_ex"', "fx_b_pd": 'opts.get("fx_b_pd"', "fx_b_pool": 'opts.get("fx_b_pool"',
                   "fx_b_buf": 'opts.get("fx_b_buf"', "fx_b_exit": 'OPTS["fx_b_exit"]', "fx_b_lb": 'OPTS["fx_b_lb"]',
                   "fx_b6": 'OPTS["fx_b6"]', "fx_b3": 'OPTS["fx_b3"]', "fx_b7": 'OPTS["fx_b7"]'}
        self.assertEqual(set(readers), set(V))
        for k, needle in readers.items():
            self.assertIn(needle, scan_src if needle.startswith("opts.") else bt_src, k)
        self.assertIn('opts.get("fx_b_exit"', scan_src)     # the target-sigma half of the joint key

    def test_live_runner_never_references_any_fx_key(self):
        """scripts/strategy-runner.py stays on v1 unconditionally (plan §1.6): no fx_ key of any kind, and no opts=
        handed to the live seam."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("fx_", src)
        for k in list(V) + ["fx_b4_htf_level"]:
            self.assertNotIn(k, src)

    def test_untouched_engine_hands_analyze_and_setup_candidate_exactly_the_pre_batch_overlay(self):
        """Default overlay carries no V key at all (a baseline value is what an absent key already means), so the
        F-item wiring test in test_ict_fidelity.py keeps seeing an all-False overlay."""
        seen = []
        with mock.patch.object(BT.lr, "read_at", lambda c, i, tf, m, opts=None: seen.append(opts) or {}), \
             mock.patch.object(BT.lr.ict_scan, "setup_candidate", lambda a, w, lb, opts=None: seen.append(opts)),\
             mock.patch.object(BT.lr, "window", lambda c, i, tf: c[: i + 1]), \
             mock.patch.object(BT.lr, "setup_lookback", lambda tf: 10):
            c = [{"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}] * 3
            BT.ict_setups_live("XAUUSD", "15m", c, ["2026-01-05T00:00:00Z", "2026-01-05T00:15:00Z", "2026-01-05T00:30:00Z"],
                               BT.P["15m"]["H"], [1.0] * 3, [1.0] * 3, [1.0] * 3, ("ict",))
        self.assertTrue(seen)
        for opts in seen:
            self.assertEqual(set(opts) & set(V), set())


class BEX_EntryModel(unittest.TestCase):
    """B-EX -- knowledge/ict/core-a.md §2.23 (R19): 'choose one of three fills -- touch of the near edge (IOFED),
    the 0.5 (Consequent Encroachment), or the far edge (FVG Fill)'."""

    def test_default_equals_v1_and_the_actual_pre_batch_code(self):
        a, c = long_fixture()
        old = load_git_revision(BASE, "ict-scan.py").setup_candidate(a, c, lookback=100)
        self.assertEqual(sc(a, c), old)
        self.assertEqual(sc(a, c, fx_b_ex="iofed"), old)
        a2, c2 = mirror(a, c)
        self.assertEqual(sc(a2, c2, fx_b_ex="iofed"), load_git_revision(BASE, "ict-scan.py").setup_candidate(a2, c2, lookback=100))

    def test_each_model_moves_the_entry_long(self):
        a, c = long_fixture()
        self.assertEqual([sc(a, c, fx_b_ex=v)["entry"] for v in V["fx_b_ex"]], [130.0, 127.5, 125.0])

    def test_each_model_moves_the_entry_short(self):
        a, c = mirror(*long_fixture())
        self.assertEqual([sc(a, c, fx_b_ex=v)["entry"] for v in V["fx_b_ex"]], [170.0, 172.5, 175.0])

    def test_planned_r_follows_the_entry(self):
        a, c = long_fixture()
        r = [sc(a, c, fx_b_ex=v)["R"] for v in V["fx_b_ex"]]
        self.assertEqual(r, [round((165 - e) / (e - 108), 2) for e in (130.0, 127.5, 125.0)])


class BPD_DealingRangeFraming(unittest.TestCase):
    """B-PD -- knowledge/ict/core-a.md §2.18-2.19, R13, R15: R15 frames the range on the nearest BSL/SSL pair (v1);
    R13's diagram frames it from the swept extreme (stop side) to the opposing pool (target side)."""

    def test_default_equals_v1_and_the_actual_pre_batch_code(self):
        a, c = long_fixture()
        self.assertEqual(sc(a, c, fx_b_pd="r15"), load_git_revision(BASE, "ict-scan.py").setup_candidate(a, c, lookback=100))

    def test_r13_can_refuse_what_r15_accepts(self):
        a, c = long_fixture()
        a["unswept"][0]["level"] = 135.0          # opposing pool close above the entry: R13 range 108..135, entry at 0.81
        self.assertTrue(sc(a, c)["pd_ok"])                                   # R15: (130-100)/100 = 0.30, discount
        self.assertFalse(sc(a, c, fx_b_pd="r13")["pd_ok"])                   # R13: (130-108)/27 = 0.81, premium

    def test_r13_can_accept_what_r15_refuses(self):
        a, c = long_fixture()
        a["lo"], a["hi"] = 120.0, 140.0           # R15 range 120..140: entry 130 = 0.5 exactly = equilibrium, not discount
        self.assertFalse(sc(a, c)["pd_ok"])
        self.assertTrue(sc(a, c, fx_b_pd="r13")["pd_ok"])                    # R13: 108..160, (130-108)/52 = 0.42

    def test_r13_keeps_the_r15_edge_when_there_is_no_opposing_pool(self):
        a, c = long_fixture()
        a["unswept"] = []
        a["lo"], a["hi"] = 100.0, 200.0
        r13 = sc(a, c, fx_b_pd="r13")
        self.assertEqual(r13["entry_pct"], round((130 - 108) / (200 - 108), 4))

    def test_r13_short_mirror(self):
        a, c = mirror(*long_fixture())
        a["unswept"][0]["level"] = 165.0          # mirror of the long case above
        self.assertTrue(sc(a, c)["pd_ok"])
        self.assertFalse(sc(a, c, fx_b_pd="r13")["pd_ok"])


class BBUF_StopBuffer(unittest.TestCase):
    """B-BUF -- knowledge/ict/core-a.md R22 says the stop sits 'below' the level and gives no size; the buffer is
    the plan's declared 0 / 0.1 ATR / 0.25 ATR beyond the wick (ATR period 14 is project-defined)."""

    def test_default_equals_v1_and_the_actual_pre_batch_code(self):
        a, c = long_fixture()
        self.assertEqual(sc(a, c, fx_b_buf="0"), load_git_revision(BASE, "ict-scan.py").setup_candidate(a, c, lookback=100))
        self.assertEqual(sc(a, c)["stop"], 108.0)

    def test_long_stop_moves_below_the_wick_by_the_atr_multiple(self):
        a, c = long_fixture()
        atr = true_range_mean(c, 5)
        self.assertAlmostEqual(sc(a, c, fx_b_buf="0.1atr")["stop"], 108.0 - 0.1 * atr)
        self.assertAlmostEqual(sc(a, c, fx_b_buf="0.25atr")["stop"], 108.0 - 0.25 * atr)
        self.assertLess(sc(a, c, fx_b_buf="0.25atr")["stop"], sc(a, c, fx_b_buf="0.1atr")["stop"])

    def test_short_stop_moves_above_the_wick(self):
        a, c = mirror(*long_fixture())
        atr = true_range_mean(c, 5)
        self.assertEqual(sc(a, c)["stop"], 192.0)
        self.assertAlmostEqual(sc(a, c, fx_b_buf="0.1atr")["stop"], 192.0 + 0.1 * atr)

    def test_atr_reads_only_bars_up_to_the_mss_bar(self):
        a, c = long_fixture()
        base = sc(a, c, fx_b_buf="0.25atr")["stop"]
        c[8] = bar(8, 150.0, 400.0, 1.0, 150.0)      # a huge bar AFTER the MSS bar must not move the buffer
        self.assertEqual(sc(a, c, fx_b_buf="0.25atr")["stop"], base)


class BEXIT_Target(unittest.TestCase):
    """B-EXIT (target part) -- knowledge/ict/models.md §2.1.5 / core-b.md §2.12: a target point inside the -2..-2.5
    sigma projection zone."""

    def test_default_equals_v1_and_the_actual_pre_batch_code(self):
        a, c = long_fixture()
        old = load_git_revision(BASE, "ict-scan.py")
        self.assertEqual(sc(a, c, fx_b_exit="-2.0|H|floor"), old.setup_candidate(a, c, lookback=100))
        a2, c2 = mirror(a, c)
        self.assertEqual(sc(a2, c2, fx_b_exit="-2.0|H|floor"), old.setup_candidate(a2, c2, lookback=100))

    def test_target_moves_with_the_sigma_multiple_long(self):
        a, c = long_fixture()
        self.assertEqual([sc(a, c, fx_b_exit=f"{t}|H|floor")["target"] for t in ("-2.0", "-2.25", "-2.5")], [165.0, 170.0, 175.0])

    def test_target_moves_with_the_sigma_multiple_short(self):
        a, c = mirror(*long_fixture())
        self.assertEqual([sc(a, c, fx_b_exit=f"{t}|H|floor")["target"] for t in ("-2.0", "-2.25", "-2.5")], [135.0, 130.0, 125.0])

    def test_time_stop_and_floor_parts_do_not_touch_the_setup(self):
        a, c = long_fixture()
        self.assertEqual(sc(a, c, fx_b_exit="-2.0|2H|no_floor"), sc(a, c))

    def test_no_projection_falls_back_to_the_range_edge_whatever_the_multiple(self):
        a, c = long_fixture()
        a["mss"][0]["origin"] = a["mss"][0]["ext"]          # zero-length leg: nothing to project from
        self.assertEqual(sc(a, c, fx_b_exit="-2.5|H|floor")["target"], sc(a, c)["target"])


class BPOOL_ReferencePools(unittest.TestCase):
    """B-POOL -- knowledge/ict/core-a.md §2.8 (PDH/PDL) and §2.9 (session highs and lows are liquidity levels)."""

    @staticmethod
    def hourly(days, spikes=None, start="2026-01-05T00:00:00Z", lows=None):
        """`days` x 24 hourly UTC bars from a Monday, flat around 100; spikes = {index: (high, close)}."""
        import datetime
        t0 = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
        out = []
        for i in range(days * 24):
            t = (t0 + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            h, cl = (spikes or {}).get(i, (100.5, 100.0))
            out.append({"time": t, "open": 100.0, "high": h, "low": (lows or {}).get(i, 99.5), "close": cl, "volume": 10.0})
        return out

    def pdh_fixture(self):
        # Day 2 (bars 24-47) tops out at its LAST bar (47, high 111) -- not a pivot, because bar 48's higher high (112)
        # sits inside its 3-bar window -- and bar 48 (day 3) wicks through 111 and closes back under it: a PDH sweep.
        # The mirror for the low: day 2's lowest wick is its last bar (97), bar 48 wicks to 96 and closes back above.
        return self.hourly(4, spikes={47: (111.0, 100.0), 48: (112.0, 100.0)}, lows={47: 97.0, 48: 96.0})

    def test_default_off_equals_v1_and_the_actual_pre_batch_code(self):
        c = self.pdh_fixture()
        old = load_git_revision(BASE, "ict-scan.py").analyze(c, 4, tf="1h", methods=("ict",))
        self.assertEqual(SCAN.analyze(c, 4, tf="1h", methods=("ict",)), old)
        self.assertEqual(SCAN.analyze(c, 4, tf="1h", methods=("ict",), opts={"fx_b_pool": "off"}), old)

    def test_on_adds_pdh_and_pdl_pools_that_can_be_swept(self):
        c = self.pdh_fixture()
        off = SCAN.analyze(c, 4, tf="1h", methods=("ict",))
        on = SCAN.analyze(c, 4, tf="1h", methods=("ict",), opts={"fx_b_pool": "on"})
        self.assertFalse([p for p in off["pools"] if p["type"] in ("pdh", "pdl")])
        pdh = [p for p in on["pools"] if p["type"] == "pdh"]
        self.assertTrue(pdh)
        self.assertTrue(any(p["level"] == 111.0 and p["swept"] == 48 for p in pdh), "PDH 111 swept by bar 48's wick")
        self.assertTrue([p for p in on["pools"] if p["type"] == "pdl"])
        self.assertGreater(len(on["pools"]), len(off["pools"]))

    def test_the_still_forming_day_and_the_first_partial_day_are_not_pools(self):
        c = self.hourly(2, spikes={5: (120.0, 100.0), 30: (130.0, 100.0)})   # day 1 = first (partial), day 2 = forming
        on = SCAN.analyze(c, 4, tf="1h", methods=("ict",), opts={"fx_b_pool": "on"})
        self.assertFalse([p for p in on["pools"] if p["type"] in ("pdh", "pdl")])

    def test_on_adds_completed_session_highs_and_lows_only(self):
        import sessions as S
        c = self.hourly(4, spikes={2: (108.0, 100.0), 9: (109.0, 100.0)})      # bar 2 = 02:00Z in asia, bar 9 = 09:00Z in london (winter)
        self.assertIn("asia", S.active(c[2]["time"]))
        self.assertIn("london", S.active(c[9]["time"]))
        # window = days 1-3 so the asia/london windows of day 2+ are complete inside it
        on = SCAN.analyze(c[:72], 4, tf="1h", methods=("ict",), opts={"fx_b_pool": "on"})
        self.assertTrue([p for p in on["pools"] if p["type"] in ("session_high", "session_low")])
        # PIT: a window that ENDS inside the london run has no pool from that unfinished run
        cut = c[:34]                                        # last bar = day 2 10:00Z, still inside london (08-11Z)
        self.assertIn("london", S.active(cut[-1]["time"]))
        part = SCAN.analyze(cut, 4, tf="1h", methods=("ict",), opts={"fx_b_pool": "on"})
        self.assertFalse([p for p in part["pools"] if p["type"].startswith("session_") and p["to"] == len(cut) - 1])
        self.assertFalse([p for p in part["pools"] if p["type"].startswith("session_") and p["from"] >= 32],
                         "the unfinished london run of day 2 must not have produced a pool")

    def test_off_never_imports_or_reads_the_session_registry_path(self):
        c = self.hourly(3)
        SCAN._SESS_ACTIVE.clear()
        SCAN.analyze(c, 4, tf="1h", methods=("ict",))
        self.assertEqual(SCAN._SESS_ACTIVE, {})


class EngineHarness(unittest.TestCase):
    """ict_setups_live() driven by a stubbed live scanner (the pattern of test_ict_fidelity.IctSetupsLiveWiring): the
    scanner returns ONE hand-built long setup at bar `detect_i`; the bars decide fill, expiry, target and stop."""

    def build(self, tf, n, fill_bar, fill_hour=14, step_h=1, target_bar=None, above=(120.0, 110.0, 115.0), side=(100.0, 90.0, 130.0)):
        import datetime
        entry, stop, target = side
        t_fill = datetime.datetime(2026, 1, 5, fill_hour, 0, 0)          # a Monday
        t0 = t_fill - datetime.timedelta(hours=step_h * fill_bar)
        Tm = [(t0 + datetime.timedelta(hours=step_h * i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(n)]
        c = []
        for i in range(n):
            h, l, cl = above if i < fill_bar else (110.0, 101.0, 105.0)
            if i == fill_bar:
                h, l, cl = 110.0, 99.0, 104.0                            # the limit at 100 fills here
            if i == target_bar:
                h = 131.0                                                # the target (130) trades here
            c.append({"time": Tm[i], "open": cl, "high": h, "low": l, "close": cl, "volume": 1.0})
        return Tm, c

    def run_engine(self, sym, tf, Tm, c, overrides=None, detect_i=6, mss_i=5, bias=("long", "x"), gate=None,
                   lookback_stub=lambda tf: 12, entry=100.0, stop=90.0, target=130.0):
        su = {"complete": True, "pd_ok": True, "side": "long", "sweep": {"time": Tm[2]}, "mss": {"time": Tm[mss_i]},
              "entry": entry, "stop": stop, "target": target, "entry_models": {"fill": 95.0}, "R": 3.0}
        got = {"lookback": []}

        def fake_setup(a, w, lookback, opts=None):
            got["lookback"].append(lookback)
            return su if len(w) == detect_i + 1 else None

        patches = [mock.patch.object(BT.lr, "read_at", lambda cc, i, t, m, opts=None: {}),
                   mock.patch.object(BT.lr.ict_scan, "setup_candidate", fake_setup),
                   mock.patch.object(BT.lr, "window", lambda cc, i, t: cc[: i + 1]),
                   mock.patch.object(BT.lr, "setup_lookback", lookback_stub),
                   mock.patch.object(BT.lr, "bias_at", lambda *a_, **k_: bias),
                   mock.patch.dict(BT.OPTS, overrides or {})]
        if gate is not None:
            patches.append(mock.patch.object(BT, "htf_bias_gate", gate))
        for p in patches:
            p.start()
        try:
            H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
            out = BT.ict_setups_live(sym, tf, c, Tm, BT.P[tf]["H"], H, L, C, ("ict",))
        finally:
            for p in reversed(patches):
                p.stop()
        return out, got


class BLB_LookbackAndExpiry(EngineHarness):
    """B-LB -- project parameters (plan §3): setup lookback {12, 8, 16} x K-bar expiry {K, 2K}. 12 is the live default
    (`live_rules.setup_lookback`), so it is the baseline; 8 / 16 scale the live default by 8/12 and 16/12."""

    def test_lookback_reaches_setup_candidate_as_declared(self):
        Tm, c = self.build("1H", 40, 10)
        for tok, want in (("12", 12), ("8", 8), ("16", 16)):
            _, got = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b_lb": f"{tok}|K"})
            self.assertEqual(set(got["lookback"]), {want}, tok)

    def test_lookback_scales_the_live_default_where_that_is_not_12(self):
        Tm, c = self.build("1H", 40, 10)
        seen = [set(self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b_lb": f"{t}|K"}, lookback_stub=lambda tf: 24)[1]["lookback"])
                for t in ("12", "8", "16")]
        self.assertEqual(seen, [{24}, {16}, {32}])

    def test_2k_accepts_a_setup_detected_after_k_bars_but_before_2k(self):
        # 1H: K=12. MSS at bar 5, first detectable at bar 18 = mss + 13 > mss + K: v1 refuses (ICT-8/PAR-7 expiry);
        # 2K (24 bars) still holds the order, which fills at bar 22.
        Tm, c = self.build("1H", 60, 22)
        v1, _ = self.run_engine("XAUUSD", "1H", Tm, c, detect_i=18)
        k2, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b_lb": "12|2K"}, detect_i=18)
        self.assertEqual(v1, [])
        self.assertEqual(len(k2), 1)
        self.assertEqual(k2[0]["entry_time"], Tm[22])

    def test_default_takes_the_ordinary_setup(self):
        Tm, c = self.build("1H", 40, 10)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["entry_time"], Tm[10])


class B6_CancelWhenTargetTradesFirst(EngineHarness):
    """B6 -- knowledge/ict/core-b.md §3.1 R3 (fidelity N3): a project rule on the invalidation idea: a pending limit
    is cancelled when the target has traded before the limit fills."""

    def test_default_still_fills_after_the_target_traded(self):
        Tm, c = self.build("1H", 40, 10, target_bar=7)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c)
        self.assertEqual(len(out), 1)

    def test_yes_cancels_it(self):
        Tm, c = self.build("1H", 40, 10, target_bar=7)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b6": "yes"})
        self.assertEqual(out, [])

    def test_yes_leaves_a_setup_whose_target_did_not_trade_first(self):
        Tm, c = self.build("1H", 40, 10)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b6": "yes"})
        self.assertEqual(len(out), 1)

    def test_a_target_that_trades_only_after_the_fill_is_not_a_cancellation(self):
        Tm, c = self.build("1H", 40, 10, target_bar=14)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b6": "yes"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["outcome"], "win")


class B7_KillzoneOnly(EngineHarness):
    """B7 -- knowledge/ict/core-a.md R1 / §2.1 (killzones); windows are the DST-aware session registry
    (docs/architecture/sessions.json). Indices only: metals (XAUUSD) get none."""

    def test_precondition_hours(self):
        import sessions as S
        self.assertTrue(S.active("2026-01-05T14:00:00Z"))       # 09:00 New York: NY AM
        self.assertFalse(S.active("2026-01-05T06:00:00Z"))      # off hours

    def test_default_takes_an_index_entry_at_any_hour(self):
        Tm, c = self.build("1H", 40, 10, fill_hour=6)
        out, _ = self.run_engine("US500", "1H", Tm, c)
        self.assertEqual(len(out), 1)

    def test_killzone_drops_an_index_entry_outside_every_window(self):
        Tm, c = self.build("1H", 40, 10, fill_hour=6)
        out, _ = self.run_engine("US500", "1H", Tm, c, {"fx_b7": "killzone"})
        self.assertEqual(out, [])

    def test_killzone_keeps_an_index_entry_inside_a_window(self):
        Tm, c = self.build("1H", 40, 10, fill_hour=14)
        out, _ = self.run_engine("US500", "1H", Tm, c, {"fx_b7": "killzone"})
        self.assertEqual(len(out), 1)

    def test_metals_are_never_restricted(self):
        Tm, c = self.build("1H", 40, 10, fill_hour=6)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b7": "killzone"})
        self.assertEqual(len(out), 1)

    def test_dst_follows_the_new_york_clock(self):
        import sessions as S
        # 13:30 New York opens NY PM: 18:30Z in January (EST) but 17:30Z in July (EDT)
        self.assertTrue(S.active("2026-01-05T18:30:00Z"))
        self.assertTrue(S.active("2026-07-06T17:30:00Z"))
        self.assertFalse(S.active("2026-07-06T18:30:00Z") and S.active("2026-07-06T17:00:00Z"))


class B3_BiasTimeframe(EngineHarness):
    """B3 -- knowledge/ict/models.md §2.8 (TFA p5 pairing table): the bias is read on the paired higher timeframe
    instead of the entry timeframe."""

    def test_pairing_table_is_the_deck_s_in_entry_to_bias_form(self):
        # Weekly->H4, Daily->H1, H4->M15, H1->M5, M30->M3, M15->M1 (bias -> entry); entry 15m<-4H, 5m<-1H, 1m<-15m, 1H<-1D
        self.assertEqual(BT.TFA_P5_BIAS_TF, {"1m": "15m", "5m": "1H", "15m": "4H", "1H": "1D"})

    def test_default_reads_the_entry_timeframe_bias_and_never_the_pairing(self):
        calls = []
        Tm, c = self.build("1H", 40, 10)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, bias=("short", "x"), gate=lambda *a, **k: calls.append((a, k)) or True)
        self.assertEqual(out, [])              # entry-TF bias disagrees with the long side
        self.assertEqual(calls, [])

    def test_tfa_p5_uses_the_paired_tier_instead_of_the_entry_tier(self):
        calls = []
        Tm, c = self.build("1H", 40, 10)
        gate = lambda sym, tf, side, dt, methods, h=None: calls.append((tf, side, h)) or True
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b3": "tfa_p5"}, bias=("short", "x"), gate=gate)
        self.assertEqual(len(out), 1, "entry-TF bias (short) is ignored under tfa_p5; the paired 1D tier says yes")
        self.assertTrue(calls and all(k == ("1H", "long", "1D") for k in calls))

    def test_tfa_p5_refuses_when_the_paired_tier_disagrees(self):
        Tm, c = self.build("1H", 40, 10)
        out, _ = self.run_engine("XAUUSD", "1H", Tm, c, {"fx_b3": "tfa_p5"}, bias=("long", "x"), gate=lambda *a, **k: False)
        self.assertEqual(out, [])

    def test_tfa_p5_refuses_an_entry_timeframe_the_table_does_not_pair(self):
        called = []
        Tm, c = self.build("30m", 40, 10)
        out, _ = self.run_engine("XAUUSD", "30m", Tm, c, {"fx_b3": "tfa_p5"}, gate=lambda *a, **k: called.append(1) or True)
        self.assertEqual(out, [])
        self.assertEqual(called, [], "no pairing -> structurally unable to judge -> refuse; never a silent fallback")

    def test_htf_bias_gate_reads_the_explicit_tier_and_its_default_is_unchanged(self):
        import inspect
        self.assertIsNone(inspect.signature(BT.htf_bias_gate).parameters["h"].default)
        daily = [{"time": "2026-01-01T00:00:00Z", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                 {"time": "2026-01-02T00:00:00Z", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]
        loaded = []

        def fake_load(sym, tf):
            loaded.append(tf)
            return daily, "x"
        with mock.patch.object(BT, "load", fake_load), mock.patch.object(BT.lr, "bias_at", lambda *a, **k: ("long", "b")):
            self.assertIs(BT.htf_bias_gate("S", "1H", "long", "2026-01-05T10:00:00Z", ("ict",), h="1D"), True)
            self.assertEqual(loaded, ["1D"])
            loaded.clear()
            BT.htf_bias_gate("S", "1H", "long", "2026-01-05T10:00:00Z", ("ict",))      # default: the next rung (2H exists? no -> 4H)
            self.assertEqual(loaded, [BT.HTF_OF["1H"]])


class BEXIT_TimeStopAndFloor(EngineHarness):
    """B-EXIT (time-stop and 2R parts) -- time stop H: project (no time exit in the source); 2R:
    knowledge/ict/models.md §3.1 rule 23 ('2R is the minimum requirement before taking profit')."""

    def exits(self, tok):
        Tm, c = self.build("4H", 110, 10, step_h=4)
        out, _ = self.run_engine("XAUUSD", "4H", Tm, c, {"fx_b_exit": f"-2.0|{tok}|floor"})
        self.assertEqual(len(out), 1)
        return out[0]

    def test_time_stop_bar_moves_with_the_multiple(self):
        h = BT.P["4H"]["H"]                                    # 30 bars; the trade starts at bar 11
        r = {tok: self.exits(tok) for tok in ("H", "1.5H", "2H", "none")}
        self.assertEqual(r["H"]["exit"], 11 + h - 1)
        self.assertEqual(r["1.5H"]["exit"], 11 + int(round(1.5 * h)) - 1)
        self.assertEqual(r["2H"]["exit"], 11 + 2 * h - 1)
        self.assertEqual(r["none"]["exit"], 109, "no time exit: the trade runs to the end of history")
        self.assertEqual({v["outcome"] for v in r.values()}, {"timeout"})

    def test_default_is_the_v1_horizon(self):
        Tm, c = self.build("4H", 110, 10, step_h=4)
        out, _ = self.run_engine("XAUUSD", "4H", Tm, c)
        self.assertEqual(out[0]["exit"], 11 + BT.P["4H"]["H"] - 1)

    def trade(self, event):
        return dict(symbol="US500", tf="1H", side="long", time="2026-01-05T10:00:00Z", event=event, entry=100.0,
                    entry_time="2026-01-05T10:00:00Z", stop=99.0, target=101.0, exit_time="2026-01-05T12:00:00Z",
                    vol_type=None, outcome="win", R=1.0, R_planned=1.0, exit=3, mfe=1.0, mae=0.0, bars_held=2)

    def taken(self, trade, tok):
        with mock.patch.dict(BT.OPTS, {"fx_b_exit": f"-2.0|H|{tok}"}):
            return BT.simulate([trade], 0.0)[2]

    def test_floor_refuses_a_planned_r_below_the_floor_and_no_floor_admits_it(self):
        self.assertLess(1.0, BT.OPTS["min_rr"])
        t = self.trade("US500-long-ict-a-b")
        self.assertEqual(self.taken(t, "floor"), [])
        self.assertEqual(len(self.taken(t, "no_floor")), 1)

    def test_no_floor_is_ict_only(self):
        t = self.trade("US500-long-book-2026-01-05")
        self.assertEqual(self.taken(t, "no_floor"), [], "a Wyckoff trade keeps its floor whatever fx_b_exit says")


class BMGMT_ExistingKnob(unittest.TestCase):
    """B-MGMT -- WMT p272 (as used by config B): the EXISTING OPTS['mgmt'] knob, none | be. No new key."""

    def walk(self, mgmt):
        H = [0, 111.0, 101.0]; L = [0, 101.0, 89.0]; C = [0, 105.0, 95.0]
        with mock.patch.dict(BT.OPTS, {"mgmt": mgmt}):
            return BT.walk("long", 100.0, 90.0, 130.0, H, L, C, 1, 10)

    def test_none_takes_the_full_stop(self):
        self.assertEqual((self.walk("none")["outcome"], self.walk("none")["R"]), ("loss", -1.0))

    def test_be_moves_the_stop_to_entry_at_plus_one_r(self):
        w = self.walk("be")
        self.assertEqual((w["outcome"], w["R"]), ("breakeven", 0.0))

    def test_default_is_none(self):
        self.assertEqual(BT._OPTS_BASE["mgmt"], "none")


if __name__ == "__main__":
    unittest.main()
