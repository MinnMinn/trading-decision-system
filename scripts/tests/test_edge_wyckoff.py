"""scripts/research/edge_wyckoff.py on SYNTHETIC and HAND-BUILT bars only (no real history, no outcome on market data).
Pre-registration: docs/plans/2026-10-04-wyckoff-retest-preregistration.md (§10 item 5: these tests pass before sealing).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_wyckoff
"""
import ast
import contextlib
import datetime
import importlib.util
import io
import json
import math
import os
import random
import statistics
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
spec = importlib.util.spec_from_file_location("edge_wyckoff", os.path.join(ROOT, "scripts", "research", "edge_wyckoff.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
import instruments as I  # noqa: E402
import pit  # noqa: E402
import real_costs as RC  # noqa: E402
import wyckoff_rules as W  # noqa: E402

EC, H7 = M.EC, M.H7
BT = M.engine()
UTC = datetime.timezone.utc
PREREG = "docs/plans/2026-10-04-wyckoff-retest-preregistration.md"
SEALED = {"path": PREREG, "sha256": "0" * 64, "seal_date": "2026-10-05", "seal_instant": "2026-10-05T00:00:00Z"}


# ------------------------------------------------------------------------------------------------ synthetic bars
def leg(start, end, n, vol=10.0):
    """n bars ramping linearly start -> end, a 0.05 wick each side (the shape of test_wyckoff_fidelity's helper).
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = []
    for i in range(n):
        c = start + (end - start) * (i + 1) / n
        o = start + (end - start) * i / n
        out.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c, vol))
    return out


def rising(n, a=100.0, b=104.0):
    """A rising zigzag from a to b (higher highs and lows: never a downtrend, so never an SC).
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out, p = [], a
    for i in range(n):
        q = a + (b - a) * (i + 1) / n + (0.3 if i % 2 else -0.3)
        out.append((p, max(p, q) + 0.1, min(p, q) - 0.1, q, 10.0))
        p = q
    return out


def base():
    """Downtrend -> SC (79.95) -> AR (110.05) -> ST (84.95) -> three CHoBEV up-swings -> three Phase-B swings ending at 92
    (88 bars; test_wyckoff_fidelity.base_accumulation's shape). Phase-B highs 108 / 106 / 100 sit in the upper third:
    the cause gate passes; Phase-B lows drift 85 -> 90: not sloped.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    b = leg(104, 102, 5) + leg(102, 99, 5) + leg(99, 101, 5) + leg(101, 97, 5)
    b += leg(97, 100, 5) + leg(100, 90, 5) + leg(90, 96, 5) + leg(96, 80, 5)
    b += leg(80, 110, 6) + leg(110, 85, 6) + leg(85, 108, 6) + leg(108, 88, 6) + leg(88, 106, 6)
    return b + leg(106, 90, 6) + leg(90, 100, 6) + leg(100, 92, 6)


def phase_d():
    """SOS (wide, close above the 110.05 ceiling), its commitment close, a pullback into the BU zone, the BU up-close.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return [(108, 114, 107.5, 113.5, 30.0), (113.5, 114.5, 112, 114, 10.0), (114, 114.2, 111, 111.5, 5.0),
            (111.5, 115, 113.2, 114.8, 10.0)] + leg(114.8, 118, 5)


def scenario(kind="spring"):
    """One accumulation. spring: the break bar (low 78) closes back inside at once (r = s, SPRING), Test next bar.
    shakeout: two closes below the border, reclaim at s+2 (2 > (2+1)/2: SHAKEOUT), Test at r+1. cancelled: a SHAKEOUT
    whose bar after the reclaim makes a lower low (77.0 < 77.5).
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    b = base() + leg(92, 82, 4)
    if kind == "spring":
        b += [(82, 82.5, 78, 81, 20.0)] + leg(81, 86, 3, vol=5.0)
    elif kind == "shakeout":
        b += [(82, 82.5, 78, 79.0, 20.0), (79.0, 79.6, 77.5, 79.2, 20.0), (79.2, 81.2, 79.0, 80.9, 10.0),
              (80.9, 82.4, 80.2, 82.2, 5.0)] + leg(82.2, 86, 2)
    elif kind == "cancelled":
        b += [(82, 82.5, 78, 79.0, 20.0), (79.0, 79.6, 77.5, 79.2, 20.0), (79.2, 81.2, 79.0, 80.9, 10.0),
              (80.9, 81.0, 77.0, 78.5, 5.0), (78.5, 84, 78.4, 83.8, 5.0)] + leg(83.8, 86, 2)
    return b + leg(86, 108, 6) + phase_d()


def candles(bars, start="2023-12-01T00:00:00Z", minutes=240):
    t0 = M._utc(start)
    return [{"time": M._iso(t0 + datetime.timedelta(minutes=minutes * i)), "open": o, "high": h, "low": lo, "close": c,
             "volume": v} for i, (o, h, lo, c, v) in enumerate(bars)]


def walk_bars(n, seed, p=100.0, vol=10.0):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        q = p * math.exp(rnd.gauss(0, 0.004))
        out.append((p, max(p, q) * (1 + abs(rnd.gauss(0, 0.002))), min(p, q) * (1 - abs(rnd.gauss(0, 0.002))), q,
                    vol * (1 + rnd.random())))
        p = q
    return out


def series(bars, sym="XAUUSD", tf="4H", start="2023-12-01T00:00:00Z", minutes=240, zone=UTC, venue="ftmo"):
    c = candles(bars, start, minutes)
    return M.Series(sym, tf, c, zone, M._utc(c[0]["time"]).date(), venue=venue)


def resample(c4h):
    """1D bars from 4H bars (UTC days; the synthetic HTF companion).
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    for c in c4h:
        d = c["time"][:10] + "T00:00:00Z"
        o = out.get(d)
        if o is None:
            out[d] = dict(c, time=d)
        else:
            o.update(high=max(o["high"], c["high"]), low=min(o["low"], c["low"]), close=c["close"],
                     volume=o["volume"] + c["volume"])
    return list(out.values())


def book(sym_seed, n_bars=726):
    """Dec 2023 -> Mar 2024 4H bars: a 300-bar rising prefix, then scenarios (spring / shakeout / cancelled) joined by
    falls and rising zigzags, then a random walk to n_bars; prices offset by the symbol so series differ.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    bars = rising(300)
    for kind in ("shakeout", "spring", "spring", "cancelled", "spring"):
        bars += scenario(kind) + leg(118, 101, 6) + rising(30, 100.5, 104.0)
        if len(bars) > n_bars:
            break
    bars += walk_bars(max(0, n_bars - len(bars)), sym_seed, bars[-1][3])
    off = 1.0 + 0.01 * (sym_seed % 7)
    return [(o * off, h * off, lo * off, c * off, v) for (o, h, lo, c, v) in bars[:n_bars]]


class FakeLoader:
    """(candles, provenance) for any symbol: 4H synthetic books and their 1D companions; records what it served.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self):
        self.calls, self._c = [], {}

    def __call__(self, sym, tf):
        self.calls.append((sym, tf))
        if sym not in self._c:
            self._c[sym] = candles(book(sum(map(ord, sym))))
        c4 = self._c[sym]
        if tf == "4H":
            return c4, {"path": "synthetic", "bars": len(c4)}
        if tf == "1D":
            return resample(c4), {"path": "synthetic", "bars": len(c4) // 6}
        return [], {"path": None}


def fake_cost_r(entry, stop, t_in, t_out, sym, side, profile, stat="median"):
    """A deterministic cost_r stand-in: spread 0.02R (0.03R at p90) plus swap 0.01R per call.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    assert profile == M.COST_PROFILE
    spread = 0.02 if stat == "median" else 0.03
    return {"total_R": spread + 0.01, "swap_R": 0.01, "spread_R": spread, "commission_R": 0.0}


def boom(*a, **k):
    raise AssertionError("data was loaded before the read order / registration was checked")


@contextlib.contextmanager
def fresh(*patches):
    """A fresh 'process' for one read (the one-read-per-process guard reset) with the given mock patches.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    M._PROCESS["used"] = None
    with contextlib.ExitStack() as st:
        for p in patches:
            st.enter_context(p)
        st.enter_context(contextlib.redirect_stdout(io.StringIO()))
        yield
    M._PROCESS["used"] = None


# ------------------------------------------------------------------------------------------------ registration
class Registration(unittest.TestCase):
    def test_det_po_and_the_engine_numbers_are_the_engines_own(self):
        self.assertEqual(M.BASE_CFG, dict(window=300, pivot=3, reclaim=12, test_bars=12, cap_mult=1, price_only=True,
                                          fx_w123=False, volume="raw"))
        self.assertEqual(M.BASE_CFG["window"], BT.WYCKOFF_WINDOW)
        self.assertEqual(M.BASE_CFG["reclaim"], W.PARAMS["test_window"])            # "PARAMS.test_window reused" (§3.1)
        self.assertEqual(M.BASE_CFG["pivot"], W.PARAMS["pivot"])
        self.assertEqual(M.TEST_ZONE, W.PARAMS["test_zone_tr"])
        self.assertEqual({tf: BT.P[tf]["H"] for tf in M.TIMEFRAMES}, {"15m": 96, "1H": 72, "4H": 30})
        self.assertEqual({tf: BT.P[tf]["sob"] for tf in M.TIMEFRAMES}, {"15m": 6, "1H": 4, "4H": 3})
        self.assertEqual(BT.STOP_BUFFER_PCT, 0.0005)
        self.assertEqual({tf: M.htf_of(tf) for tf in M.TIMEFRAMES}, {"15m": "1H", "1H": "4H", "4H": "1D"})
        P = M.det_params(M.BASE_CFG)
        self.assertTrue(P["price_only"] and P["spring_max_bars_outside"] == 12)
        self.assertFalse(any(P[k] for k in ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring",
                                            "fx_w5_vp_abandon")))
        self.assertIsNone(P["fx_w4a_linger_closes"])
        self.assertFalse(M.det_params(M.BASE_CFG, "V")["price_only"])               # family V: the engine's volume reading
        self.assertEqual({k: v for k, v in W.PARAMS.items() if k not in ("price_only", "spring_max_bars_outside")},
                         {k: v for k, v in P.items() if k not in ("price_only", "spring_max_bars_outside")})

    def test_perturbations_change_one_thing_each(self):
        self.assertEqual(list(M.PERTURBATIONS), ["P1", "P2", "P3", "P4", "P5", "P6"])
        want = {"P1": {"fx_w123": True}, "P2": {"price_only": False, "volume": "hour_norm"}, "P3": {"window": 600},
                "P4": {"pivot": 4}, "P5": {"reclaim": 24}, "P6": {"cap_mult": 2}}
        for p, d in M.PERTURBATIONS.items():
            self.assertEqual({k: v for k, v in d.items() if k != "change"}, want[p])
        P1 = M.det_params(dict(M.BASE_CFG, fx_w123=True))
        self.assertTrue(P1["fx_w1_tr_low_st"] and P1["fx_w2_st_below_sc"] and P1["fx_w3_mSOW_spring"])
        self.assertFalse(P1["fx_w5_vp_abandon"])

    def test_decision_numbers_are_the_signed_ones(self):
        self.assertEqual((M.DELTA, M.COUNT_GATE, M.FDR_Q), (0.20, 30, 0.10))
        self.assertEqual((M.BREADTH_MIN, M.PERTURB_NEED, M.AGAINST_P), (20, 5, 0.05))
        self.assertEqual((M.R2_CLUSTER_MIN, M.R2_EVALUABLE_MIN, M.R2_AGREE), (10, 2, 3))
        self.assertEqual((M.L1_P, M.FORWARD_P, M.FORWARD_EVENTS, M.FORWARD_MONTHS), (0.10, 0.10, 100, 12))
        self.assertEqual((M.N_PLACEBO, M.ATR_N, M.SEED_TAG, M.BOOT_N), (200, 20, "WY-P0", 2000))
        self.assertEqual((M.DENSE_SHARE, M.DENSE_REF_YEAR, M.DENSE_LOOKBACK_DAYS, M.HOLE_DAYS), (0.80, 2023, 60, 7))
        self.assertEqual(M.COST_PROFILE, "ftmo_demo_2026_09_relspread")
        self.assertEqual(M.FTMO_LINES, ("median_swap", "median_noswap", "p90_swap", "p90_noswap"))
        self.assertAlmostEqual(M.COST_RT, 0.0012)
        self.assertAlmostEqual(M.COST_STRESS, 0.0014)
        self.assertEqual(M.DEV_CUTOFF, "2024-03-01T00:00:00Z")
        self.assertEqual(len(M.W_CELLS), 8)
        self.assertEqual(M.NO_EDGE_CELLS, ("W-C-long-15m", "W-C-long-1H", "W-CAMP"))

    def test_symbols(self):
        self.assertEqual(M.TRADEABLE, ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200"))
        self.assertEqual(sorted(s for v in M.REPLICATION.values() for s in v),
                         sorted(["XPTUSD", "XPDUSD", "US2000", "EU50", "UK100", "JP225", "HK50"]))
        self.assertFalse(set(M.TRADEABLE) & {s for v in M.REPLICATION.values() for s in v})
        self.assertFalse(set(M.EXCLUDED) & (set(M.TRADEABLE) | {s for v in M.REPLICATION.values() for s in v}))
        self.assertEqual(M.v_symbols(), I.backtested("crypto"))
        src = open(os.path.join(ROOT, "scripts", "research", "edge_wyckoff.py")).read()
        for sym in I.backtested("crypto"):                       # family V reads instruments, never a literal
            self.assertNotIn(sym, src)

    def test_code_is_every_module_the_engine_and_l1_load_and_the_chain_compares_it(self):
        self.assertEqual(M.COMMITTED, (M.PREREG, M.LEDGER) + M.CODE)
        self.assertNotIn(M.LEDGER, M.CODE)                                         # other studies append to it
        self.assertIn(M.ABLATION, M.CODE)                                          # §10 item 4: one sealed code SHA
        for p in M.CODE:
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)
        self.assertEqual(set(M.code_sha256()), set(M.CODE))
        self.assertTrue({"script_sha256", "code_sha256"} <= set(M.META_FIXED))
        with mock.patch.dict(os.environ):                                          # reprice sets BT_HISTORY_ROOT
            M._load("reprice_real_costs_code_probe", M.REPRICE)                    # what L1 loads (module code only)
        self.assertEqual(M._loaded_code() - set(M.CODE), set())
        M._require_code_complete()
        rogue = types.ModuleType("_wy_rogue")
        rogue.__file__ = os.path.join(ROOT, "scripts", "rogue_helper.py")
        with mock.patch.dict(sys.modules, {"_wy_rogue": rogue}), self.assertRaises(SystemExit) as cm:
            M._require_code_complete()
        self.assertIn("scripts/rogue_helper.py", str(cm.exception))

    def test_every_docstring_cites_the_preregistration(self):
        for rel in ("scripts/research/edge_wyckoff.py", "scripts/tests/test_edge_wyckoff.py"):
            tree = ast.parse(open(os.path.join(ROOT, rel)).read())
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                    doc = ast.get_docstring(n)
                    if doc is not None:
                        self.assertIn(PREREG, doc, f"{rel}: {getattr(n, 'name', '<module>')}")


# ------------------------------------------------------------------------------------------------ §4 dense rule
def days_counts(spec_):
    """[(date, bars)] -> (sday per bar, dts per bar): `bars` bars spread over the day.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    sday, dts = [], []
    for d, n in spec_:
        for j in range(n):
            sday.append(d)
            dts.append(datetime.datetime(d.year, d.month, d.day, tzinfo=UTC) + datetime.timedelta(minutes=j * (1440 // n)))
    return sday, dts


class DenseRule(unittest.TestCase):
    def cal(self, a, b, n=lambda d: 20):
        d, out = a, []
        while d <= b:
            if d.weekday() < 5:
                out.append((d, n(d)))
            d += datetime.timedelta(days=1)
        return out

    def test_start_is_the_first_month_every_later_month_passes(self):
        D = datetime.date
        sday, dts = days_counts(self.cal(D(2022, 1, 3), D(2024, 2, 28), lambda d: 2 if d < D(2022, 6, 1) else 20))
        got = M.dense_start(sday, dts)
        self.assertEqual(got["ref_median"], 20)
        self.assertEqual(got["start"], "2022-06-01")
        self.assertEqual(got["months"]["2022-05"], 2)

    def test_a_later_sparse_month_moves_the_start_after_it(self):
        D = datetime.date
        sday, dts = days_counts(self.cal(D(2022, 1, 3), D(2024, 2, 28),
                                         lambda d: 10 if (d.year, d.month) == (2023, 8) else 20))
        self.assertEqual(M.dense_start(sday, dts)["start"], "2023-09-01")

    def test_a_hole_longer_than_seven_days_restarts_the_clock_at_the_next_month(self):
        D = datetime.date
        cal = [x for x in self.cal(D(2022, 1, 3), D(2024, 2, 28)) if not (D(2023, 3, 6) <= x[0] <= D(2023, 3, 20))]
        sday, dts = days_counts(cal)
        got = M.dense_start(sday, dts)
        self.assertEqual((got["start"], got["holes"]), ("2023-04-01", 1))
        cal = [x for x in self.cal(D(2022, 1, 3), D(2024, 2, 28)) if not (D(2023, 3, 6) <= x[0] <= D(2023, 3, 8))]
        got = M.dense_start(*days_counts(cal))                                     # Fri 03-03 -> Thu 03-09: < 7 days
        self.assertEqual((got["start"], got["holes"]), ("2022-01-01", 0))

    def test_no_reference_year_no_start(self):
        D = datetime.date
        self.assertIsNone(M.dense_start(*days_counts(self.cal(D(2021, 1, 4), D(2022, 6, 30))))["start"])

    def test_dense_days_are_point_in_time_and_events_read_the_previous_day(self):
        D = datetime.date
        cal = self.cal(D(2023, 1, 2), D(2023, 4, 28), lambda d: 5 if d == D(2023, 3, 15) else 20)
        sday, dts = days_counts(cal)
        dense, prev = M.dense_days(sday, D(2023, 1, 1))
        self.assertNotIn(D(2023, 1, 2), dense)                                      # no earlier day: no reference
        self.assertIn(D(2023, 1, 3), dense)
        self.assertNotIn(D(2023, 3, 15), dense)
        i = sday.index(D(2023, 3, 16))
        self.assertFalse(prev[i])                                                   # its previous server day was thin
        self.assertTrue(prev[sday.index(D(2023, 3, 15))])
        # the FUTURE never changes an earlier day: thin every day after 2023-04-01
        cal2 = [(d, 1 if d >= D(2023, 4, 1) else n) for d, n in cal]
        dense2, _ = M.dense_days(*days_counts(cal2)[:1], D(2023, 1, 1))
        self.assertEqual({d for d in dense if d < D(2023, 4, 1)}, {d for d in dense2 if d < D(2023, 4, 1)})

    def test_the_series_starts_at_the_dense_start_and_ends_at_the_read(self):
        c = candles(rising(200), "2023-12-01T00:00:00Z")
        S = M.Series("XAUUSD", "4H", c, UTC, datetime.date(2023, 12, 10), until="2024-01-01T00:00:00Z")
        self.assertEqual(S.T[0], "2023-12-10T00:00:00Z")
        self.assertEqual(S.T[-1], "2023-12-31T20:00:00Z")                          # closes at 2024-01-01T00:00Z <= until
        self.assertTrue(all(a == d + S.bar for a, d in zip(S.avail, S.dt)))


# ------------------------------------------------------------------------------------------------ §3.2 typing
class Typing(unittest.TestCase):
    def arrays(self, bars):
        return [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]

    def test_same_bar_reclaim_is_a_spring_signalling_at_the_reclaim(self):
        H, L, C = self.arrays([(90, 91, 89, 90.5, 1), (90, 90.5, 78, 81, 1), (81, 82, 80.5, 81.8, 1)])
        st = M.shake(H, L, C, 1, 80.0, 30.0, 2, 6, 12, 12)
        self.assertEqual((st["status"], st["type"], st["r"], st["signal"], st["spring_low"]), ("signal", "SPRING", 1, 1, 78))

    def test_typing_uses_sob_and_the_share_of_closes_below(self):
        bars = [(90, 91, 89, 90.5, 1), (85, 85, 78, 79.5, 1), (79.5, 81, 79, 80.5, 1)] + [(80.5, 82, 80.2, 81.5, 1)] * 3
        H, L, C = self.arrays(bars)
        st = M.shake(H, L, C, 1, 80.0, 30.0, 5, 6, 12, 12)                         # d = 1, 1 close below <= 1: SPRING
        self.assertEqual((st["type"], st["r"]), ("SPRING", 2))
        st = M.shake(H, L, C, 1, 80.0, 30.0, 5, 0, 12, 12)                         # d = 1 > sob 0: SHAKEOUT
        self.assertEqual(st["type"], "SHAKEOUT")
        bars = [(90, 91, 89, 90.5, 1), (85, 85, 78, 79.5, 1), (79.5, 79.9, 77, 79.0, 1), (79, 81, 78.5, 80.5, 1),
                (80.5, 82, 80.2, 81.8, 1)]
        H, L, C = self.arrays(bars)
        st = M.shake(H, L, C, 1, 80.0, 30.0, 4, 6, 12, 12)                         # d = 2, 2 closes below > 1.5
        self.assertEqual((st["type"], st["r"], st["spring_low"], st["status"], st["t"]), ("SHAKEOUT", 3, 77, "signal", 4))

    def test_a_shakeout_test_is_cancelled_by_a_lower_low_and_waits_for_its_window(self):
        bars = [(90, 91, 89, 90.5, 1), (85, 85, 78, 79.5, 1), (79.5, 79.9, 77, 79.0, 1), (79, 81, 78.5, 80.5, 1),
                (80.5, 80.6, 76.9, 77.5, 1), (77.5, 82, 77.4, 81.8, 1)]
        H, L, C = self.arrays(bars)
        st = M.shake(H, L, C, 1, 80.0, 30.0, 5, 6, 12, 12)
        self.assertEqual((st["status"], st["t"]), ("cancelled", None))
        self.assertEqual(M.shake(H, L, C, 1, 80.0, 30.0, 3, 6, 12, 12)["status"], "pending")   # Test window still open
        H, L, C = self.arrays(bars[:4] + [(80.5, 95, 90.01, 94, 1)] * 12)            # never back in the lower third
        self.assertEqual(M.shake(*self.arrays(bars[:4] + [(80.5, 95, 90, 94, 1)]), 1, 80.0, 30.0, 4, 6, 12, 12)["t"], 4)
        self.assertEqual(M.shake(H, L, C, 1, 80.0, 30.0, 15, 6, 12, 12)["status"], "no_test")

    def test_no_reclaim_within_the_window(self):
        H, L, C = self.arrays([(90, 91, 89, 90.5, 1)] + [(79, 79.5, 78, 79, 1)] * 13)
        self.assertEqual(M.shake(H, L, C, 1, 80.0, 30.0, 13, 6, 12, 12)["status"], "no_reclaim")
        self.assertEqual(M.shake(H, L, C, 1, 80.0, 30.0, 12, 6, 12, 12)["status"], "pending")
        H, L, C = self.arrays([(90, 91, 89, 90.5, 1)] + [(79, 79.5, 78, 79, 1)] * 13 + [(79, 81, 78.5, 80.5, 1)])
        self.assertEqual(M.shake(H, L, C, 1, 80.0, 30.0, 14, 6, 24, 12)["r"], 14)  # P5: the 24-bar reclaim window


# ------------------------------------------------------------------------------------------------ §3.1-§3.3 detection
def scen_series(kind, pre=300):
    bars = rising(pre) + scenario(kind) + rising(40, 118, 120)
    return series(bars), pre


class Detection(unittest.TestCase):
    def detect(self, S, cfg=None):
        cfg = cfg or dict(M.BASE_CFG)
        return M.detect_series(S, cfg, M.det_params(cfg), BT.P[S.tf]["sob"], None)

    def test_spring_fires_once_at_its_reclaim_with_the_book_trade(self):
        S, pre = scen_series("spring")
        out = self.detect(S)
        wc = [e for e in out["W-C"]]
        self.assertEqual(len(wc), 1)
        e = wc[0]
        s = pre + 92
        self.assertEqual((e["type"], e["s"], e["r"], e["k"], e["e"], e["spring_low"]), ("SPRING", s, s, s, s + 1, 78))
        self.assertEqual((e["sc"], e["tr_lo"], e["tr_hi"]), (pre + 40, 79.95, 110.05))     # bars 39 and 40 tie at 79.95:
        self.assertEqual(e["s"] - e["sc"], 52)                                       # swings() keeps the later pivot
        self.assertAlmostEqual(e["stop"], 78 * (1 - 0.0005))
        self.assertEqual(e["target"], 110.05)
        self.assertGreaterEqual(e["phase_b_tests"]["upper"] + e["phase_b_tests"]["lower"], 1)
        self.assertFalse(e["sloped"])

    def test_shakeout_fires_at_its_test_and_also_at_its_reclaim_descriptively(self):
        S, pre = scen_series("shakeout")
        out = self.detect(S)
        s = pre + 92
        (e,) = out["W-C"]
        self.assertEqual((e["type"], e["s"], e["r"], e["t"], e["k"], e["spring_low"]), ("SHAKEOUT", s, s + 2, s + 3, s + 3,
                                                                                         77.5))
        (sor,) = out["W-C-SOR"]
        self.assertEqual((sor["k"], sor["r"], sor["type"]), (s + 2, s + 2, "SHAKEOUT"))

    def test_a_cancelled_test_is_no_event_and_is_logged_once(self):
        S, _pre = scen_series("cancelled")
        out = self.detect(S)
        self.assertEqual(out["W-C"], [])
        self.assertEqual(out["logs"]["W-C|cancelled"], 1)

    def test_phase_d_fires_once_at_the_bu_bar_with_the_spring_low_stop(self):
        S, pre = scen_series("spring")
        out = self.detect(S)
        d = [e for e in out["W-D"] if e["side"] == "long"]
        self.assertEqual(len(d), 1)
        full = W.detect_accumulations(S.O, S.H, S.L, S.C, S.V, P=M.det_params(M.BASE_CFG))
        bu = [r["bu"]["bar"] for r in full if r["bu"]]
        self.assertIn(d[0]["k"], bu)
        self.assertEqual(d[0]["path"], "spring")
        self.assertAlmostEqual(d[0]["stop"], 78 * (1 - 0.0005))
        self.assertIsNone(d[0]["target"])                                           # chosen at the fill (§3.3)
        self.assertEqual(d[0]["key"], out["W-C"][0]["key"])                        # the same structure: W-CAMP's T3

    def test_the_mirror_is_read_as_a_distribution_with_real_price_stops(self):
        bars = rising(300) + scenario("spring") + rising(40, 118, 120)
        mir = [(300 - o, 300 - lo, 300 - h, 300 - c, v) for (o, h, lo, c, v) in bars]
        S = series(mir)
        out = self.detect(S)
        (e,) = out["W-C-short"]
        self.assertEqual((e["side"], e["type"], e["k"], e["spring_low"]), ("short", "SPRING", 392, 222))
        self.assertAlmostEqual(e["stop"], 222 * (1 + 0.0005))
        self.assertAlmostEqual(e["target"], 300 - 110.05)
        d = [x for x in out["W-D"] if x["side"] == "short"]
        self.assertEqual(len(d), 1)
        self.assertAlmostEqual(d[0]["stop"], 222 * (1 + 0.0005))

    def test_the_gates(self):
        rec = {"phase_b_tests": {"upper": 0, "lower": 0}, "sloped": False}
        self.assertFalse(M.gate(rec))
        self.assertTrue(M.gate(dict(rec, phase_b_tests={"upper": 0, "lower": 1})))
        self.assertFalse(M.gate(dict(rec, phase_b_tests={"upper": 2, "lower": 0}, sloped=True)))

    def test_window_pivots_and_window_own_pivots_fire_the_same_events(self):
        S, _pre = scen_series("shakeout")
        cfg, P = dict(M.BASE_CFG), M.det_params(M.BASE_CFG)
        pidx = W.pivot_index(S.H, S.L, P["pivot"])
        for k in range(299, len(S), 7):
            a = M.window_fire(S, k, cfg, P, 3, pidx)
            b = M.window_fire(S, k, cfg, P, 3, None)
            self.assertEqual(json.dumps(a, default=str), json.dumps(b, default=str))

    def test_campaign_tranches(self):
        S, pre = scen_series("spring")
        out = self.detect(S)
        (camp,) = M.campaigns(S, out["W-C"], out["W-D"], M.BASE_CFG)
        names = [t[0] for t in camp["tranches"]]
        self.assertEqual(names, ["T1", "T2", "T3"])
        s = pre + 92
        self.assertEqual(camp["tranches"][0], ["T1", s, s + 1])
        self.assertEqual(camp["tranches"][1], ["T2", s + 1, s + 2])                 # the Test, the bar after the Spring
        self.assertEqual(camp["tranches"][2][1], out["W-D"][0]["k"])
        S2, _ = scen_series("shakeout")
        out2 = self.detect(S2)
        (c2,) = M.campaigns(S2, out2["W-C"], out2["W-D"], M.BASE_CFG)
        self.assertEqual([t[0] for t in c2["tranches"]], ["T1", "T3"])               # a Shakeout's T1 IS the Test

    def test_1d_is_descriptive_only_and_never_pooled(self):
        ev = {"leg": "W-C", "tf": "1D", "type": "SPRING", "ctx": True}
        self.assertEqual(M.cells_of(ev), ["desc:W-C-long-1D", "desc:W-C-long-1D|SPRING"])
        self.assertEqual(M.cells_of(dict(ev, leg="W-D")), ["desc:W-D-1D"])
        self.assertEqual(M.cells_of(dict(ev, leg="W-CAMP")), ["desc:W-CAMP-1D"])
        self.assertEqual(M.cells_of(dict(ev, tf="4H")), ["W-C-long-4H", "desc:W-C-long-4H|SPRING", "W-CTX"])
        legs = ("W-C", "W-D", "W-CAMP", "W-C-short", "W-C-SOR")
        self.assertFalse(set(M.W_CELLS) & {c for lg in legs for c in M.cells_of(dict(ev, leg=lg))})
        self.assertTrue({"desc:W-C-long-1D", "desc:W-D-1D", "desc:W-CAMP-1D"} <= M._w_cells_wanted("R1", None))
        self.assertEqual(M._w_cells_wanted("R2", ["W-C-long-4H"]), {"W-C-long-4H"})
        self.assertEqual(M.desc_variants(dict(ev, tf="1D")), [])

    def test_r1_variants_ceiling_target_and_flatten_and_the_trend_placebo(self):
        S, _pre = scen_series("spring")
        evs = M.series_events(S, None, dict(M.BASE_CFG))
        (wc,) = evs["W-C"]
        seen, real = [], M.score

        def spy(bt, S_, ev, HZ, pricer, lo, hi, target=None, trend=False):
            seen.append((ev["leg"], target, trend, BT.OPTS["flat_before_rollover"], BT.OPTS["rollover_provider"]))
            return real(bt, S_, ev, HZ, pricer, lo, hi, target=target, trend=trend)
        wanted = M._w_cells_wanted("R1", None)
        with mock.patch.object(M, "score", spy), M.walk_opts(BT):
            rows, _sk = M.score_events(BT, S, evs, wanted, 30, FixedPricer(), None, None, extras=True)
            self.assertFalse(BT.OPTS["flat_before_rollover"])                      # the flatten block restored the read's
        self.assertIn(("W-C", None, True, False, None), seen)                      # the cell row, with the trend placebo
        self.assertIn(("W-C", wc["ceiling"], False, False, None), seen)            # §3.2: the raised-ceiling target
        self.assertIn(("W-C", None, False, True, M.PROVIDER), seen)                # §3.7: flatten before the rollover
        self.assertIn(("W-D", None, False, True, M.PROVIDER), seen)
        self.assertTrue(rows["desc:W-C-long-4H|ceiling-target"])
        self.assertTrue(all(r["target"] == wc["ceiling"] and r["variant"] == "ceiling"
                            for r in rows["desc:W-C-long-4H|ceiling-target"]))
        self.assertTrue(all(r["variant"] == "flatten" for r in rows["desc:W-C-long-4H|flatten"]))
        self.assertTrue(all("excess_trend" in r for r in rows["W-C-long-4H"]))
        seen.clear()
        with mock.patch.object(M, "score", spy), M.walk_opts(BT):
            plain, _ = M.score_events(BT, S, evs, {"W-C-long-4H", "W-D-4H"}, 30, FixedPricer(), None, None)
        self.assertFalse(any(c.startswith("desc:") for c in plain))
        self.assertFalse(any(t or flat or tgt is not None for _lg, tgt, t, flat, _p in seen))


# ------------------------------------------------------------------------------------------------ §3.3 HTF containment
class Containment(unittest.TestCase):
    def test_candidates_match_the_engine_and_the_latest_beyond_the_entry_wins(self):
        recs = [{"tr_lo": 10, "tr_hi": 20, "ceiling": 22, "sos": None}, {"tr_lo": 15, "tr_hi": 25, "ceiling": 25, "sos": 1}]
        C = [0, 30.0]
        for side in ("long", "short"):
            self.assertEqual(tuple(M.htf_candidate(r, C, side) for r in recs), BT._w7_candidates(recs, C, side))
        cands = [(10, 32, 20), (15, 35, 30.0)]
        self.assertEqual(M.target_for(cands, "long", 21), 30.0)
        self.assertEqual(M.target_for(cands, "long", 31), None)
        self.assertEqual(M.target_for([(10, 32, 20), (15, 35, 18)], "long", 19), 20)   # latest whose target is beyond
        self.assertEqual(M.target_for([(0, 50, 12), (0, 50, 25)], "short", 20), 12)

    def test_the_htf_prefix_is_the_point_in_time_one(self):
        S, _pre = scen_series("spring")
        H = M.Htf(S, M.det_params(M.BASE_CFG))
        for k in (100, 391, 392, 450):
            when = S.avail[k]
            self.assertEqual(H.prefix_len(when), len(pit.series_as_of(S.src, "4H", M._iso(when))))
            self.assertEqual(H.prefix_len(when), k + 1)
        full = H.cands("long", len(S))
        self.assertTrue(full)
        P = M.det_params(M.BASE_CFG)
        recs = W.detect_accumulations(S.O, S.H, S.L, S.C, S.V, P=P)
        self.assertEqual(full, tuple(M.htf_candidate(r, S.C, "long") for r in recs if M.gate(r)))
        early = H.cands("long", 392)
        self.assertEqual(early, tuple(M.htf_candidate(r, S.C, "long") for r in
                                      W.detect_accumulations(S.O[:392], S.H[:392], S.L[:392], S.C[:392], S.V[:392], P=P)
                                      if M.gate(r)))

    def test_enrich_reads_the_htf_at_the_signal_close(self):
        S, pre = scen_series("spring")
        H = M.Htf(S, M.det_params(M.BASE_CFG))
        ev = {"leg": "W-C", "side": "long", "k": pre + 120}
        M.enrich(ev, S, H)
        acc = H.contained("long", S.avail[pre + 120], S.C[pre + 120])
        self.assertEqual(ev["htf_cands"], [list(c) for c in acc])
        self.assertEqual(ev["ctx"], bool(acc) and not H.contained("short", S.avail[pre + 120], S.C[pre + 120]))
        ev2 = M.enrich({"leg": "W-D", "side": "long", "k": pre + 120}, S, None)
        self.assertEqual((ev2["htf_cands"], ev2["ctx"], ev2["no_htf"]), ([], False, True))


# ------------------------------------------------------------------------------------------------ §5 placebo / walks / costs
class FixedPricer:
    lines, primary = M.FTMO_LINES, "median_swap"

    def trade(self, S, side, entry, stop, e, x, outcome):
        return {"median_swap": 0.04, "median_noswap": 0.03, "p90_swap": 0.06, "p90_noswap": 0.05}


class Placebo(unittest.TestCase):
    def setUp(self):
        self.S = series(walk_bars(1500, 3), tf="1H", minutes=60)

    def test_the_pool_matches_slot_dense_previous_day_atr_and_window(self):
        S = self.S
        pool = S.pool(S.slot[700], None, None)
        self.assertTrue(pool)
        for p in pool:
            self.assertEqual(S.slot[p], S.slot[700])
            self.assertTrue(S.prev_dense[p] and S.atr[p - 1] > 0)
        lo = S.T[900]
        self.assertTrue(all(p >= 900 for p in S.pool(S.slot[700], lo, None)))

    def test_the_draw_is_seeded_without_replacement(self):
        S = self.S
        pool = list(range(5, 400))
        a = M.placebo_draw(S, pool, "2024-01-02T03:00:00Z")
        self.assertEqual(a, M.placebo_draw(S, pool, "2024-01-02T03:00:00Z"))
        self.assertEqual(len(a), 200)
        self.assertEqual(len(set(a)), 200)
        self.assertNotEqual(a, M.placebo_draw(S, pool, "2024-01-02T04:00:00Z"))
        import random as _r
        self.assertEqual(a, sorted(_r.Random(int(__import__("hashlib").sha256(
            f"WY-P0|{S.sym}|{S.tf}|2024-01-02T03:00:00Z".encode()).hexdigest()[:16], 16)).sample(pool, 200)))
        self.assertEqual(M.placebo_draw(S, pool[:50], "x"), pool[:50])

    def test_placebo_trades_carry_the_event_geometry_in_atr_multiples(self):
        S = self.S
        k = 800
        e = k + 1
        entry = S.O[e]
        ev = {"leg": "W-C", "side": "long", "k": k, "e": e, "stop": entry - 2.0, "target": entry + 5.0}
        calls = []

        def rec(bt, side, ent, stop, tgt, S_, e_, HZ):
            calls.append((side, ent, stop, tgt, e_, HZ))
            return {"R": 0.5, "exit": e_, "outcome": "timeout", "bars_held": 1}
        with mock.patch.object(M, "walk_from", rec):
            row, why = M.score(BT, S, ev, 72, FixedPricer(), None, None)
        self.assertIsNone(why)
        self.assertEqual(calls[0][:5], ("long", entry, entry - 2.0, entry + 5.0, e))
        ds, dt_ = 2.0 / S.atr[k], 5.0 / S.atr[k]
        drawn = M.placebo_draw(S, S.pool(S.slot[e], None, None), S.T[k])
        self.assertEqual([c[4] for c in calls[1:]], drawn)
        for side, ent, stop, tgt, p, HZ in calls[1:]:
            self.assertEqual((side, ent, HZ), ("long", S.O[p], 72))
            self.assertAlmostEqual(ent - stop, ds * S.atr[p - 1])
            self.assertAlmostEqual(tgt - ent, dt_ * S.atr[p - 1])
        self.assertEqual((row["excess"], row["n_placebo"]), (0.0, len(drawn)))
        self.assertAlmostEqual(row["net_excess"], -0.04)
        self.assertEqual(row["week"], M.week_of(S.dt[k]))
        # no target: the placebo has the stop and the cap only
        calls.clear()
        with mock.patch.object(M, "walk_from", rec):
            M.score(BT, S, dict(ev, leg="V4", target=None), 72, FixedPricer(), None, None)
        self.assertTrue(all(c[3] is None for c in calls))
        self.assertNotIn("placebo_trend", row)                                      # only R1 asks for it

    def test_the_trend_sign_is_the_close_against_the_close_twenty_days_earlier_point_in_time(self):
        S = self.S
        for j in (0, 400, 480, 481, 900, 1499):
            back = [i for i in range(j + 1) if S.dt[i] <= S.dt[j] - datetime.timedelta(days=20)]
            want = None if not back else (S.C[j] > S.C[back[-1]]) - (S.C[j] < S.C[back[-1]])
            self.assertEqual(S.trend(j), want, j)
        cut = M.Series(S.sym, S.tf, S.src[:901], S.zone, S.start)
        self.assertEqual([cut.trend(j) for j in range(901)], [S.trend(j) for j in range(901)])

    def test_the_trend_matched_placebo_is_the_matched_part_of_the_same_draw(self):
        S = self.S
        k, e = 800, 801
        ev = {"leg": "W-C", "side": "long", "k": k, "e": e, "stop": S.O[e] - 2.0, "target": S.O[e] + 5.0}

        def rec(bt, side, ent, stop, tgt, S_, e_, HZ):
            return {"R": 0.01 * (e_ % 7), "exit": e_, "outcome": "timeout", "bars_held": 1}
        with mock.patch.object(M, "walk_from", rec):
            row, why = M.score(BT, S, ev, 72, FixedPricer(), None, None, trend=True)
        self.assertIsNone(why)
        drawn = M.placebo_draw(S, S.pool(S.slot[e], None, None), S.T[k])
        matched = [p for p in drawn if S.trend(p - 1) == S.trend(k)]
        self.assertTrue(0 < len(matched) < len(drawn))
        self.assertEqual((row["trend"], row["n_placebo_trend"], row["n_placebo"]), (S.trend(k), len(matched), len(drawn)))
        self.assertAlmostEqual(row["placebo_trend"], sum(0.01 * (p % 7) for p in matched) / len(matched))
        self.assertAlmostEqual(row["excess_trend"], row["R"] - row["placebo_trend"])

    def test_an_entry_open_beyond_the_stop_or_target_is_skipped(self):
        S = self.S
        e = 801
        for st, tg in ((S.O[e] + 1, S.O[e] + 5), (S.O[e] - 5, S.O[e] - 1), (S.O[e], S.O[e] + 1)):
            row, why = M.score(BT, S, {"leg": "W-C", "side": "long", "k": 800, "e": e, "stop": st, "target": tg}, 72,
                               FixedPricer(), None, None)
            self.assertEqual((row, why), (None, "entry_beyond_stop_or_target"))
        ev = {"leg": "W-D", "side": "long", "k": 800, "e": e, "stop": S.O[e] - 1, "htf_cands": [[0, 1e9, S.O[e] - 0.5]]}
        with mock.patch.object(M, "walk_from", lambda *a: {"R": 0.0, "exit": e, "outcome": "timeout", "bars_held": 1}):
            row, why = M.score(BT, S, ev, 72, FixedPricer(), None, None)
        self.assertIsNone(row["target"])                                            # the only target is below the entry


class Walks(unittest.TestCase):
    def mk(self, bars):
        return series(bars, tf="1H", minutes=60)

    def test_same_bar_stop_before_target_and_gap_fills(self):
        flat = [(100, 100.5, 99.5, 100, 1)] * 5
        S = self.mk(flat + [(100, 105, 95, 100, 1)] + flat)
        with M.walk_opts(BT):
            w = M.walk_from(BT, "long", 100, 97, 103, S, 5, 10)
            self.assertEqual((w["outcome"], w["R"], w["exit"]), ("loss", -1.0, 5))
            S2 = self.mk(flat + [(94, 95, 93, 94.5, 1)] + flat)
            w = M.walk_from(BT, "long", 100, 97, 103, S2, 5, 10)
            self.assertEqual((w["outcome"], w["exit"]), ("loss", 5))
            self.assertAlmostEqual(w["R"], (94 - 100) / 3)                         # gap through: filled at the open
            w = M.walk_from(BT, "short", 100, 103, 97, self.mk(flat + [(106, 107, 105, 106, 1)] + flat), 5, 10)
            self.assertAlmostEqual(w["R"], -2.0)
            w = M.walk_from(BT, "long", 100, 97, None, self.mk(flat * 3), 2, 4)
            self.assertEqual((w["outcome"], w["exit"]), ("timeout", 5))
        self.assertFalse(BT.OPTS.get("fx_gap_fill"))                                # the module baseline is restored

    def test_the_campaign_walk_is_the_engine_walk_for_one_tranche(self):
        rnd = random.Random(7)
        for trial in range(150):
            S = self.mk(walk_bars(120, trial))
            e = rnd.randrange(30, 100)
            ent = S.O[e]
            stop = ent * (1 - rnd.uniform(0.002, 0.02))
            tgt = ent * (1 + rnd.uniform(0.002, 0.04)) if rnd.random() < 0.8 else None
            HZ = rnd.choice((5, 20, 72))
            with M.walk_opts(BT):
                w = M.walk_from(BT, "long", ent, stop, tgt, S, e, HZ)
            c = M.campaign_walk(S, stop, tgt, [e], HZ)
            self.assertEqual((c["exit"], c["outcome"]), (w["exit"], w["outcome"]), trial)
            self.assertAlmostEqual(M.campaign_R(c["filled"], c["X"], stop), w["R"], places=9)

    def test_campaign_tranches_r_cost_and_order(self):
        bars = [(100, 100.4, 99.8, 100.2, 1)] * 3 + [(100.2, 100.6, 99.9, 100.4, 1), (101, 101.2, 100.8, 101, 1),
                                                       (102, 102.3, 101.8, 102.1, 1), (102.1, 106, 102, 105.5, 1)]
        S = self.mk(bars + [(105, 105.2, 104.8, 105, 1)] * 5)
        c = M.campaign_walk(S, 98.0, 105.0, [3, 4, 5], 10)
        self.assertEqual(c["filled"], [[3, 100.2], [4, 101], [5, 102]])
        self.assertEqual((c["exit"], c["X"], c["outcome"]), (6, 105.0, "win"))
        R = M.campaign_R(c["filled"], c["X"], 98.0)
        self.assertAlmostEqual(R, ((105 - 100.2) + (105 - 101) + (105 - 102)) / ((100.2 - 98) + (101 - 98) + (102 - 98)))
        costs = [{"a": 0.1}, {"a": 0.2}, {"a": 0.3}]
        self.assertAlmostEqual(M.campaign_cost(costs, c["filled"], 98.0, ("a",))["a"],
                               (0.1 * 2.2 + 0.2 * 3 + 0.3 * 4) / 9.2)
        c = M.campaign_walk(S, 98.0, 105.0, [3, 9], 10)                              # T3 after the exit never fills
        self.assertEqual((c["filled"], c["exit"]), ([[3, 100.2]], 6))
        gap = self.mk(bars[:4] + [(97, 97.5, 96.5, 97.2, 1)] + bars[5:])
        c = M.campaign_walk(gap, 98.0, 105.0, [3, 4], 10)                           # the tranche opening beyond the stop
        self.assertEqual((c["filled"], c["skipped"], c["exit"], c["X"]), ([[3, 100.2]], [4], 4, 97))
        flat = self.mk([(100, 100.2, 99.9, 100, 1)] * 40)
        c = M.campaign_walk(flat, 98.0, None, [3, 6], 5)            # the cap runs H bars past the LAST tranche
        self.assertEqual((c["exit"], c["outcome"], len(c["filled"])), (10, "timeout", 2))
        c = M.campaign_walk(flat, 98.0, None, [3, 10], 5)                           # ... as of each bar: T1's cap ends first
        self.assertEqual((c["exit"], c["filled"]), (7, [[3, 100]]))
        self.assertIsNone(M.campaign_walk(flat, 100.5, None, [3], 5))               # T1 beyond the stop: no campaign


class Costs(unittest.TestCase):
    def test_four_ftmo_lines_from_cost_r(self):
        seen = []

        def cr(entry, stop, t_in, t_out, sym, side, profile, stat):
            seen.append((entry, stop, t_in, t_out, sym, side, profile, stat))
            return {"total_R": 0.10 if stat == "median" else 0.15, "swap_R": 0.02}
        S = series(walk_bars(50, 1), tf="1H", minutes=60)
        got = M.Pricer("ftmo", cost_r=cr).trade(S, "long", 100.0, 99.0, 10, 20, "timeout")
        self.assertEqual(got, {"median_swap": 0.10, "median_noswap": 0.08, "p90_swap": 0.15, "p90_noswap": 0.13})
        self.assertEqual([x[-1] for x in seen], ["median", "p90"])
        self.assertEqual(seen[0][:7], (100.0, 99.0, S.T[10], S.T[20], "XAUUSD", "long", M.COST_PROFILE))

    def test_the_real_cost_r_runs_in_the_server_table_frame(self):
        self.assertEqual(RC.HOUR_FRAME, "server_table")
        M._require_hour_frame()
        with mock.patch.object(RC, "HOUR_FRAME", "utc_legacy"), self.assertRaises(SystemExit):
            M._require_hour_frame()
        with mock.patch.object(RC, "HOUR_FRAME", "utc_legacy"), mock.patch.object(M, "_require_sealed", lambda: SEALED):
            with fresh(), self.assertRaises(SystemExit):
                M.run("R1", "/nonexistent/x.json", counts_path="/nonexistent/r0.json", loader=boom, require_clean=False)

    def test_binance_lines_are_bp_through_the_stop_plus_funding(self):
        bars = walk_bars(200, 2, p=30000.0)
        S = series(bars, sym="BTCUSDT", tf="1H", start="2021-06-01T00:00:00Z", minutes=60, venue="binance")
        stamps = [(S.dt[0] + datetime.timedelta(hours=8 * j), 0.0001, 8) for j in range(30)]
        F = H7.Funding(stamps)
        pr = M.Pricer("binance", funding={"BTCUSDT": F})
        e, x = 10, 40
        entry, stop = S.O[e], S.O[e] * 0.99
        got = pr.trade(S, "long", entry, stop, e, x, "timeout")
        fund, n = H7.funding_paid(S, 1, e, S.dt[x] + S.bar, F)
        self.assertGreater(n, 0)
        dist = entry - stop
        self.assertAlmostEqual(got["base"], 0.0012 * entry / dist + fund * entry / dist)
        self.assertAlmostEqual(got["stress"] - got["base"], 0.0002 * entry / dist)
        self.assertIsNone(M.Pricer("binance", funding={"BTCUSDT": H7.Funding([])}).trade(S, "long", entry, stop, e, x,
                                                                                         "timeout"))


# ------------------------------------------------------------------------------------------------ §3.6 G-C, §6.3 V4
def gc_reference(S, N, breaks, known=None):
    """§3.6 read literally, by brute force: the reference G-C implementation the fast one must equal. `known` = [(break,
    signal)]: the diagnostic variant excluding only on W-C-long events signalled by r.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    cands = {}
    for r in range(len(S)):
        for s in range(max(N, r - 12), r + 1):
            ell = min(S.L[s - N:s])
            if S.L[s] < ell:
                q = next((q for q in range(s, len(S)) if S.C[q] > ell), None)
                if q == r and q - s <= 12:
                    cands[r] = s
                    break
    out, last = [], None
    for r in sorted(cands):
        s = cands[r]
        if (any(abs(b - s) <= N for b in breaks) if known is None
                else any(abs(b - s) <= N and k <= r for b, k in known)):
            continue
        if last is not None and r - last < N:
            continue
        last = r
        out.append((r, s, min(S.L[s:r + 1]) * (1 - 0.0005), max(S.H[s - N:s])))
    return out


class Control(unittest.TestCase):
    def test_gc_equals_the_literal_rule(self):
        for seed in range(6):
            S = series(walk_bars(400, 50 + seed), tf="1H", minutes=60)
            for N, breaks in ((8, []), (15, [100, 230]), (30, [50])):
                got, _ = M.gc_events(S, N, breaks)
                self.assertEqual([(g["k"], g["s"], g["stop"], g["target"]) for g in got], gc_reference(S, N, breaks))

    def test_the_exclusion_window_is_plus_minus_n_of_the_break(self):
        S = series(walk_bars(400, 61), tf="1H", minutes=60)
        allg, _ = M.gc_events(S, 10, [])
        s0 = allg[0]["s"]
        for b, excluded in ((s0 - 10, True), (s0 + 10, True), (s0 - 11, False), (s0 + 11, False)):
            got, st = M.gc_events(S, 10, [b])
            self.assertEqual(s0 not in [g["s"] for g in got], excluded, b)

    def test_the_known_at_r_variant_equals_its_literal_rule(self):
        rnd = random.Random(4)
        for seed in range(5):
            S = series(walk_bars(400, 70 + seed), tf="1H", minutes=60)
            for N in (8, 15, 30):
                known = sorted((b, b + rnd.randrange(0, 40)) for b in rnd.sample(range(N, 380), 6))
                got, st = M.gc_events(S, N, [b for b, _ in known], known)
                lit = [(g["k"], g["s"], g["stop"], g["target"]) for g in got if "literal" in g["gc"]]
                kn = [(g["k"], g["s"], g["stop"], g["target"]) for g in got if "known" in g["gc"]]
                self.assertEqual(lit, gc_reference(S, N, [b for b, _ in known]))
                self.assertEqual(kn, gc_reference(S, N, None, known))
                self.assertEqual(len({g["k"] for g in got}), len(got))             # one row per control, both sets

    def test_a_later_wc_break_drops_the_control_only_as_written(self):
        """The review's case: a W-C-long break within N of the control's, signalled AFTER the control's decision bar r --
        §3.6 as written excludes the control on it, the known-at-r variant keeps it; signalled by r, both exclude.
        [prereg §3.6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        S = series(walk_bars(400, 61), tf="1H", minutes=60)
        g0 = M.gc_events(S, 10, [])[0][0]
        s0, r0 = g0["s"], g0["k"]
        later = [(s0 + 8, r0 + 3)]
        got, st = M.gc_events(S, 10, [s0 + 8], later)
        mine = [g for g in got if g["s"] == s0]
        self.assertEqual([g["gc"] for g in mine], [["known"]])
        self.assertGreaterEqual(st["excluded_wc_within_N"], 1)
        self.assertEqual(M.cells_of(mine[0]), ["G-C-known-1H", "G-C-known"])
        got, st = M.gc_events(S, 10, [s0 + 8], [(s0 + 8, r0)])
        self.assertFalse([g for g in got if g["s"] == s0])
        self.assertTrue(st["excluded_wc_within_N"] >= 1 and st["known:excluded_wc_within_N"] >= 1)
        self.assertEqual(M.cells_of(dict(g0, gc=["literal", "known"])), ["G-C-1H", "G-C", "G-C-known-1H", "G-C-known"])

    def test_v4_equals_the_literal_rule(self):
        rnd = random.Random(5)
        bars = []
        for i, b in enumerate(walk_bars(30 * 24, 9, p=2000.0)):
            o, h, lo, c, v = b
            if rnd.random() < 0.05:
                v *= 4.0
                h, lo = max(o, c) * 1.0005, min(o, c) * 0.9995
            bars.append((o, h, lo, c, v))
        S = series(bars, sym="ETHUSDT", tf="1H", start="2021-05-01T00:00:00Z", minutes=60, venue="binance")
        got = [(e["k"], e["side"], e["stop"]) for e in M.v4_events(S)]
        ref, last = [], {"long": None, "short": None}
        for i in range(21, len(S) - 1):
            hh = S.dt[i].hour
            prev = [S.V[j] for j in range(i) if S.dt[j].hour == hh and S.dt[j].date() < S.dt[i].date()
                    and (S.dt[i].date() - S.dt[j].date()).days <= 20]
            if not prev or S.V[i] < 2 * statistics.median(prev):
                continue
            if S.H[i] - S.L[i] > statistics.median(S.H[j] - S.L[j] for j in range(i - 20, i)):
                continue
            for side, ok in (("long", S.C[i - 1] < S.C[i - 21] and S.C[i] > min(S.C[i - 20:i])),
                             ("short", S.C[i - 1] > S.C[i - 21] and S.C[i] < max(S.C[i - 20:i]))):
                if ok and (last[side] is None or i - last[side] >= 20):
                    last[side] = i
                    ref.append((i, side, S.L[i] * (1 - 0.0005) if side == "long" else S.H[i] * (1 + 0.0005)))
        self.assertTrue(ref)
        self.assertEqual(got, ref)


# ------------------------------------------------------------------------------------------------ §10 item 5 probe
class TruncationProbe(unittest.TestCase):
    def setUp(self):
        self.loader = FakeLoader()
        c = self.loader("XAUUSD", "4H")[0]
        self.dense = {"XAUUSD|4H": {"start": "2023-12-01"}, "XAUUSD|1D": {"start": "2023-12-01"}}
        self.cfg = dict(M.BASE_CFG)
        del c

    def events(self, fire=None):
        S = M.make_series("XAUUSD", "4H", self.loader, self.dense, self.cfg)
        Hs = M.make_series("XAUUSD", "1D", self.loader, self.dense, self.cfg)
        H = M.Htf(Hs, M.det_params(self.cfg))
        P = M.det_params(self.cfg)
        if fire is None:
            evs = M.detect_series(S, self.cfg, P, 3, H)
            return [e for leg in ("W-C", "W-C-short", "W-C-SOR", "W-D") for e in evs[leg]]
        out, seen = [], set()
        for k in range(self.cfg["window"] - 1, len(S)):
            for e in fire(S, k, self.cfg, P, 3)[0]:
                if (e["leg"], e["key"]) not in seen:
                    seen.add((e["leg"], e["key"]))
                    out.append(M.enrich(e, S, H))
        return out

    def test_every_event_re_detects_identically_on_the_cut_series(self):
        evs = self.events()
        self.assertGreaterEqual(len({e["leg"] for e in evs}), 3)
        rep = M.probe(evs, self.loader, self.dense, self.cfg)
        self.assertEqual((rep["checked"], rep["violations"], rep["ok"]), (len(evs), 0, True), rep["first_violation"])

    def test_a_builder_that_reads_the_next_bar_is_caught(self):
        def leaky(S, k, cfg, P, sob, pidx=None):
            evs, logs = M.window_fire(S, k, cfg, P, sob, pidx)
            for e in evs:
                e["stop"] = S.C[k + 1] if k + 1 < len(S) else S.C[k]               # look-ahead
            return evs, logs
        evs = self.events(leaky)
        rep = M.probe(evs, self.loader, self.dense, self.cfg, fire=leaky)
        self.assertGreater(rep["violations"], 0)
        self.assertFalse(rep["ok"])

    def test_an_htf_read_past_the_signal_close_is_caught(self):
        evs = [e for e in self.events() if e["leg"] == "W-D"]
        self.assertTrue(evs)
        real = M.Htf.prefix_len
        rep = M.probe(evs, self.loader, self.dense, self.cfg)
        self.assertTrue(rep["ok"])
        bad = [dict(e, htf_cands=[[0.0, 1e9, 1.0]]) for e in evs]                   # what a future HTF record would add
        self.assertEqual(M.probe(bad, self.loader, self.dense, self.cfg)["violations"], len(bad))
        self.assertIs(M.Htf.prefix_len, real)

    def test_an_empty_probe_is_not_a_pass(self):
        self.assertFalse(M.probe([], self.loader, self.dense, self.cfg)["ok"])


# ------------------------------------------------------------------------------------------------ statistics, verdicts
def row(net, week, sym="XAUUSD", group="metals", R=0.0, placebo=None, cost=0.0, vt=None):
    exc = net + cost
    return {"excess": exc, "R": R, "placebo": R - exc if placebo is None else placebo, "week": week, "symbol": sym,
            "group": group, "net_excess": net, "vol_type": vt,
            "cost": {"median_swap": cost, "median_noswap": cost / 2, "p90_swap": cost * 1.5, "p90_noswap": cost,
                     "base": cost, "stress": cost * 1.2}}


class Statistics(unittest.TestCase):
    def test_summary_is_cr1_by_week_with_a_t_upper_bound(self):
        rows = [row(0.3 * math.sin(i) + 0.05, f"2023-W{i % 9:02d}") for i in range(60)]
        s = M.summarise(rows, M.FTMO_LINES)
        mu, se, df = EC.cr1([r["excess"] - r["cost"]["median_swap"] for r in rows], [r["week"] for r in rows])
        self.assertAlmostEqual(s["net_excess"], mu)
        self.assertEqual((s["weeks"], s["lines"]["median_swap"]["df"]), (9, df))
        self.assertAlmostEqual(s["p_one_sided"], EC.t_sf(mu / se, df))
        self.assertAlmostEqual(s["upper_95"], mu + M.t_quantile(0.95, df) * se)
        self.assertAlmostEqual(M.t_quantile(0.95, 10_000), 1.645, places=2)
        self.assertAlmostEqual(M.t_quantile(0.95, 8), 1.860, places=3)
        self.assertEqual(M.summarise([], M.FTMO_LINES), {"n": 0})
        one = M.summarise([row(0.5, "2023-W01")] * 3, M.FTMO_LINES)                # one cluster: no SE, no bound, p = 1
        self.assertEqual((one["p_one_sided"], one["upper_95"]), (1.0, None))

    def cells_dict(self, nets, n=40, groups=("metals", "indices")):
        out = {}
        for c in M.W_CELLS:
            m = nets.get(c, -0.01)
            rows = [row(m + 0.2 * math.sin(i * 1.7), f"2023-W{i % 20:02d}", group=groups[i % len(groups)], cost=0.05)
                    for i in range(n)]
            out[c] = M.w_test(c, rows, c in nets)
        return out

    def test_r1_gates_and_labels(self):
        t = M.r1_verdicts(self.cells_dict({"W-C-long-15m": 0.5, "W-C-long-1H": -0.6, "W-D-15m": 0.0}))
        v = t["W-C-long-15m"]["verdict"]
        self.assertEqual(v["bh_m"], 3)
        self.assertTrue(v["bh_rejected"] and v["cost_lines_positive"] and v["breadth_meetable"] and v["breadth"])
        self.assertTrue(v["gates_1_3"])
        self.assertTrue(t["W-C-long-1H"]["verdict"]["against_the_book"])
        self.assertNotIn("verdict", t["W-CAMP"])                                    # descriptive: no verdict
        thin = M.r1_verdicts(self.cells_dict({"W-C-long-15m": 0.5}, n=30))         # 15 per group < 20
        self.assertFalse(thin["W-C-long-15m"]["verdict"]["breadth_meetable"])
        self.assertFalse(thin["W-C-long-15m"]["verdict"]["gates_1_3"])
        small = M.r1_verdicts(self.cells_dict({"W-CAMP": 0.0}, n=400))
        self.assertTrue(small["W-CAMP"]["verdict"]["below_delta"])

    def r1(self, nets, n=40):
        return {"tests": M.r1_verdicts(self.cells_dict(nets, n)), "descriptive": {"G-C": {"n": 12}}}

    def perts(self, cell, signs):
        return {p: {"tests": {cell: {"summary": {"n": 5, "net_excess": 0.1 if s else -0.1}}}}
                for p, s in zip(M.PERTURBATIONS, signs)}

    def test_survivors_need_five_of_six(self):
        r1 = self.r1({"W-C-long-15m": 0.5})
        self.assertTrue(M.survivors(r1, self.perts("W-C-long-15m", [1, 1, 1, 1, 1, 0]))["W-C-long-15m"]["survivor"])
        self.assertFalse(M.survivors(r1, self.perts("W-C-long-15m", [1, 1, 1, 1, 0, 0]))["W-C-long-15m"]["survivor"])
        p = self.perts("W-C-long-15m", [1, 1, 1, 1, 1, 0])
        del p["P1"]
        self.assertFalse(M.survivors(r1, p)["W-C-long-15m"]["survivor"])          # a missing perturbation does not hold
        self.assertEqual(M.survivors(r1, p)["W-C-long-15m"]["positive"], 4)

    def test_final_label_precedence_and_attribution(self):
        cell = "W-C-long-15m"
        r1 = self.r1({cell: 0.5, "W-C-long-1H": -0.6, "W-CAMP": 0.0}, n=400)
        r1["tests"][cell]["gc_contrast_known"] = {"diff": 0.1}           # §3.6 (sealed): the point-in-time control decides
        self.assertEqual(M.final_label(cell, r1, None, None, None)["label"], "PENDING")
        good = self.perts(cell, [1] * 6)
        self.assertEqual(M.final_label(cell, r1, good, None, None)["label"], "PENDING")
        r2 = {"tests": {cell: {"r2_pass": True}}}
        r3 = {"tests": {cell: {"r3_veto": False}}}
        lab = M.final_label(cell, r1, good, r2, r3)
        self.assertEqual((lab["label"], lab["attribution"]), ("EDGE-CANDIDATE", "Wyckoff-attributed"))
        r1["tests"][cell]["gc_contrast_known"] = {"diff": -0.1}
        self.assertEqual(M.final_label(cell, r1, good, r2, r3)["attribution"],
                         "the shake works, but the Wyckoff range adds nothing measurable")
        # no G-C delta (G-C empty, so week_bootstrap returned diff None): never Wyckoff by default
        r1["tests"][cell]["gc_contrast_known"] = {"diff": None, "p_one_sided": None, "ci90": None, "n_a": 400, "n_b": 0}
        lab = M.final_label(cell, r1, good, r2, r3)
        self.assertEqual((lab["label"], lab["attribution"]), ("EDGE-CANDIDATE", M.ATTR_UNDETERMINED))
        del r1["tests"][cell]["gc_contrast_known"]
        self.assertEqual(M.final_label(cell, r1, good, r2, r3)["attribution"], M.ATTR_UNDETERMINED)
        # the literal (look-ahead) control never decides: it is only reported
        r1["tests"][cell].update(gc_contrast={"diff": 0.3}, gc_contrast_known={"diff": -0.2})
        lab = M.final_label(cell, r1, good, r2, r3)
        self.assertEqual((lab["attribution"], lab["gc_delta"]),
                         ("the shake works, but the Wyckoff range adds nothing measurable", {"literal": 0.3, "known_at_r": -0.2}))
        d = "W-D-15m"                                                              # §12.3: no G-C contrast for W-D
        rd = self.r1({d: 0.5}, n=400)
        lab = M.final_label(d, rd, self.perts(d, [1] * 6), {"tests": {d: {"r2_pass": True}}},
                            {"tests": {d: {"r3_veto": False}}})
        self.assertEqual((lab["label"], lab["attribution"]), ("EDGE-CANDIDATE", None))
        vetoed = M.final_label(cell, r1, good, r2, {"tests": {cell: {"r3_veto": True}}})
        self.assertIn(vetoed["label"], ("INCONCLUSIVE", "NO MECHANICAL EDGE"))
        self.assertEqual(M.final_label("W-C-long-1H", r1, None, None, None)["label"], "AGAINST THE BOOK")
        self.assertEqual(M.final_label("W-CAMP", r1, None, None, None)["label"], "NO MECHANICAL EDGE")
        self.assertEqual(M.final_label("W-D-4H", r1, None, None, None)["label"], "DESCRIPTIVE")

    def test_closing_rule(self):
        lab = {c: {"label": "NO MECHANICAL EDGE"} for c in M.NO_EDGE_CELLS}
        r1 = {"descriptive": {"G-C": {"n": 5}}}
        self.assertTrue(M.closing_rule(lab, r1)["closed_price_mechanical_on_cfds"])
        self.assertFalse(M.closing_rule(lab, r1)["closed_overall"])
        lab["W-C-long-1H"] = {"label": "AGAINST THE BOOK"}
        self.assertTrue(M.closing_rule(lab, r1)["closed_price_mechanical_on_cfds"])
        self.assertFalse(M.closing_rule(dict(lab, **{"W-D-15m": {"label": "EDGE-CANDIDATE"}}), r1)
                         ["closed_price_mechanical_on_cfds"])
        self.assertFalse(M.closing_rule(dict(lab, **{"W-CAMP": {"label": "INCONCLUSIVE"}}), r1)
                         ["closed_price_mechanical_on_cfds"])
        self.assertFalse(M.closing_rule(lab, {"descriptive": {}})["closed_price_mechanical_on_cfds"])   # G-C not read out

    def test_r2_pass_rule(self):
        def rows(nets_by_cluster):
            out = []
            for c, (n, m) in nets_by_cluster.items():
                sym = M.REPLICATION[c][0]
                out += [row(m + 0.05 * math.sin(i), f"2023-W{i % 10:02d}", sym=sym) for i in range(n)]
            return out
        self.assertTrue(M.r2_pass(rows({"metals": (12, .2), "US": (12, .2), "EU": (12, .2), "Asia": (12, -.1)}))["r2_pass"])
        self.assertFalse(M.r2_pass(rows({"metals": (12, .2), "US": (12, .2), "EU": (12, -.2),
                                         "Asia": (12, -.1)}))["r2_pass"])
        self.assertTrue(M.r2_pass(rows({"metals": (12, .2), "US": (12, .2), "EU": (5, -.5)}))["r2_pass"])  # 2 evaluable
        self.assertFalse(M.r2_pass(rows({"metals": (12, .2), "US": (5, .2)}))["r2_pass"])                   # 1 evaluable
        self.assertFalse(M.r2_pass(rows({"metals": (30, -.2), "US": (12, .3), "EU": (12, .3)}))["r2_pass"])  # pooled <= 0

    def test_week_bootstrap_and_v_verdicts(self):
        a = [row(0.4 + 0.1 * math.sin(i), f"2021-W{i % 15:02d}", vt=1) for i in range(60)]
        b = [row(-0.2 + 0.1 * math.cos(i), f"2021-W{i % 15:02d}", vt=2) for i in range(60)]
        bs = M.week_bootstrap(a, b, lambda r: r["net_excess"], 1)
        self.assertAlmostEqual(bs["diff"], statistics.mean(r["net_excess"] for r in a) -
                               statistics.mean(r["net_excess"] for r in b))
        self.assertLess(bs["p_one_sided"], 0.01)
        self.assertEqual(bs, M.week_bootstrap(a, b, lambda r: r["net_excess"], 1))
        tests = M.v_tests({"V1": a + b, "V2": b, "V4": [], "V3": a + b}, ["V1", "V2", "V3"])
        M.v_verdicts(tests)
        self.assertEqual(tests["V4"]["verdict"]["label"], "DESCRIPTIVE")
        self.assertEqual(tests["V2"]["verdict"]["label"], "AGAINST THE BOOK")
        self.assertEqual(tests["V3"]["verdict"]["label"], "EDGE-CANDIDATE")
        self.assertEqual(tests["V1"]["verdict"]["bh_m"], 3)


# ------------------------------------------------------------------------------------------------ guards and the read chain
class FakeGit:
    """Stands in for `git -C ROOT ...` (no real git state is read or changed).
    [prereg §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self, untracked=(), dirty=(), history=False, ancestor=True, tree=()):
        self.untracked, self.dirty, self.history, self.ancestor = set(untracked), set(dirty), history, ancestor
        self.tree = list(tree)                       # porcelain lines anywhere, e.g. "?? scripts/new_helper.py"

    def __call__(self, *args):
        if args[0] == "ls-files":
            return (1 if args[-1] in self.untracked else 0), ""
        if args[0] == "status":
            paths = args[args.index("--") + 1:]
            lines = [f" M {p}" for p in paths if p in self.dirty]
            lines += [ln for ln in self.tree if any(ln[3:] == p or ln[3:].startswith(p + "/") for p in paths)]
            return 0, "".join(ln + "\n" for ln in lines)
        if args[0] == "log":
            if "--diff-filter=A" in args:
                assert "--format=%cI" in args, args             # the seal is the sealing commit's COMMITTER date
                return 0, "2026-10-05T09:00:00+00:00\n"
            return 0, ("0123abcd\n" if self.history else "")
        if args[0] == "merge-base":
            return (0 if self.ancestor else 1), ""
        if args[0] == "rev-parse":
            return 0, "f" * 40 + "\n"
        raise AssertionError(args)


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        M._PROCESS["used"] = None

    def p(self, name):
        return os.path.join(self.tmp.name, name)

    def test_nothing_reads_before_the_sealed_preregistration_exists(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, M.PREREG)))              # still a DRAFT today
        for read in M.READS:
            with fresh(), self.assertRaises(SystemExit):
                M.run(read, self.p("x.json"), counts_path=self.p("r0.json"), loader=boom, vloader=boom,
                      funding_loader=boom, l1=boom, require_clean=False)
        with fresh(), self.assertRaises(SystemExit):
            M.forward("W-C-long-15m", self.p("f.json"), loader=boom, require_clean=False)
        with fresh(), self.assertRaises(SystemExit):
            M.report(self.p("rep.json"), require_clean=False)

    def r0(self, meta=None, probe="pass", **kw):
        """An R0 record (the meta this code writes, a passing probe unless given) at r0.json.
        [prereg §4 R0: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        rec = {"meta": meta or M._meta("counts"), "dense": {"XAUUSD|4H": {"start": "2023-12-01"}}, "gc_n": {"4H": 10},
               "confirmatory": {"W": [], "V": []}}
        if probe is not None:
            rec["probe"] = {"checked": 5, "violations": 0, "ok": True} if probe == "pass" else probe
        rec.update(kw)
        with open(self.p("r0.json"), "w") as fh:
            json.dump(rec, fh, default=str)
        return self.p("r0.json")

    def test_r0_needs_a_passing_truncation_probe_with_or_without_the_guard(self):
        bad = (None, {"checked": 0, "violations": 0, "ok": False}, {"checked": 9, "violations": 1, "ok": False},
               {"checked": 9, "violations": 0, "ok": False}, {"checked": 9, "violations": 2, "ok": True},
               {"checked": 0, "violations": 0, "ok": True})
        for probe in bad:
            path = self.r0(probe=probe)
            for clean in (False, True):
                with self.subTest(probe=probe, clean=clean), self.assertRaises(SystemExit) as cm:
                    M._r0(path, clean)
                self.assertIn("probe", str(cm.exception))
        self.assertEqual(M._r0(self.r0(), False)["probe"]["checked"], 5)
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        self.r0(probe={"checked": 200, "violations": 3, "ok": False})
        for read in ("R1", "V", "L1"):                                             # every R0-reading read refuses
            with fresh(sealed), self.assertRaises(SystemExit) as cm:
                M.run(read, self.p(f"{read}.json"), counts_path=self.p("r0.json"), loader=boom, vloader=boom,
                      funding_loader=boom, l1=boom, require_clean=False)
            self.assertIn("probe", str(cm.exception))

    def test_out_of_order_reads_refuse_before_touching_data(self):
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        with fresh(sealed), self.assertRaises(SystemExit):
            M.run("R1", self.p("r1.json"), loader=boom, require_clean=False)        # no R0
        with fresh(sealed), self.assertRaises(SystemExit):
            M.run("R2", self.p("r2.json"), loader=boom, require_clean=False)        # no R1
        with fresh(sealed), self.assertRaises(SystemExit):
            M.run("R3", self.p("r3.json"), perturb="P1", loader=boom, require_clean=False)
        json.dump({"meta": dict(M._meta("read", "R1"), guarded=False), "tests": {}}, open(self.p("r1.json"), "w"))
        with fresh(sealed), self.assertRaises(SystemExit):                          # nothing meets gates 1-3
            M.run("R1", self.p("p1.json"), after=self.p("r1.json"), perturb="P1", loader=boom, require_clean=False)
        with fresh(sealed), self.assertRaises(SystemExit):                          # no perturbation records
            M.run("R2", self.p("r2.json"), after=self.p("r1.json"), loader=boom, require_clean=False)
        json.dump({"meta": {"script": "scripts/research/edge_h7x.py", "kind": "counts"}}, open(self.p("r0.json"), "w"))
        with fresh(sealed), self.assertRaises(SystemExit):
            M.run("R1", self.p("r1b.json"), counts_path=self.p("r0.json"), loader=boom, require_clean=False)
        with fresh(sealed), self.assertRaises(SystemExit) as cm:                    # L1 too: R0 ties it to the code
            M.run("L1", self.p("l1.json"), loader=boom, l1=boom, require_clean=False)
        self.assertIn("--counts", str(cm.exception))
        open(self.p("exists.json"), "w").write("{}")
        self.r0()
        with fresh(sealed), self.assertRaises(SystemExit):
            M.run("R1", self.p("exists.json"), counts_path=self.p("r0.json"), loader=boom, require_clean=False)

    def test_the_guard(self):
        class Reached(Exception):
            pass

        def loader(*a, **k):
            raise Reached(a)                         # past the guard: the first data access stops the read

        def no_write(*a, **k):
            raise AssertionError("a guard test must never write a record")
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        want = os.path.join(ROOT, M.CANONICAL_OUT.format(seal="2026-10-05", name="R1"))
        meta0 = json.loads(json.dumps(M._meta("counts"), default=str))
        self.r0(meta0)
        rel = "docs/experiments/wyckoff-retest-R0-counts.json"
        named = mock.patch.object(M, "_prereg_text", lambda: f"... {rel} ...")
        relp = mock.patch.object(M, "_rel", lambda p: rel)
        ledger = mock.patch.object(M, "_require_ledger", lambda: None)
        dump = mock.patch.object(M, "_dump", no_write)
        rogue = types.ModuleType("_wy_rogue")
        rogue.__file__ = os.path.join(ROOT, "scripts", "rogue_helper.py")
        cases = ((FakeGit(untracked={M.SCRIPT}), ledger, "not tracked"),
                 (FakeGit(dirty={M.ENGINE}), ledger, "uncommitted"),
                 (FakeGit(dirty={"docs/architecture/risk-config.json"}), ledger, "uncommitted"),
                 (FakeGit(history=True), ledger, "already run"),
                 (FakeGit(), mock.patch.object(M, "_prereg_text", lambda: ""), "does not name"),
                 (FakeGit(dirty={rel}), ledger, "uncommitted"),
                 (FakeGit(tree=["?? scripts/new_helper.py"]), ledger, "clean"),                 # untracked, outside CODE
                 (FakeGit(tree=[" M docs/architecture/v-grid-ict.json"]), ledger, "clean"),
                 (FakeGit(tree=[" M data/history/costs/ftmo/symbol-map.json"]), ledger, "clean"),
                 (FakeGit(), mock.patch.dict(sys.modules, {"_wy_rogue": rogue}), "CODE does not fingerprint"))
        for git, extra, msg in cases:
            more = () if extra is ledger else (ledger,)
            with self.subTest(msg=msg), fresh(sealed, named, relp, extra, *more, dump, mock.patch.object(M, "_git", git)):
                with self.assertRaises(SystemExit) as cm:
                    M.run("R1", want, counts_path=self.p("r0.json"), loader=boom)
                self.assertIn(msg, str(cm.exception))
        with fresh(sealed, named, relp, ledger, dump, mock.patch.object(M, "_git", FakeGit())), self.assertRaises(SystemExit):
            M.run("R1", self.p("r1.json"), counts_path=self.p("r0.json"), loader=boom)    # not the canonical path
        with fresh(sealed, named, relp, dump, mock.patch.object(M, "_git", FakeGit())), self.assertRaises(SystemExit):
            M.run("R1", want, counts_path=self.p("r0.json"), loader=boom)              # the real ledger lacks the study
        real_sha = M._sha256                         # the sealed file does not exist yet: hash it as absent
        sha = mock.patch.object(M, "_sha256", lambda p: real_sha(p) if os.path.exists(p) else "absent")
        with fresh(sealed, named, relp, ledger, dump, sha, mock.patch.object(M, "_git", FakeGit())):
            with self.assertRaises(Reached):
                M.run("R1", want, counts_path=self.p("r0.json"), loader=loader)        # clean: the guard lets it through
        for k, v in (("script_sha256", "0" * 64), ("code_sha256", dict(meta0["code_sha256"], **{M.ENGINE: "0" * 64}))):
            self.r0(dict(meta0, **{k: v}))
            with fresh(sealed, named, relp, ledger, dump, mock.patch.object(M, "_git", FakeGit())):
                with self.assertRaises(SystemExit) as cm:
                    M.run("R1", want, counts_path=self.p("r0.json"), loader=boom)      # R0 from other code
                self.assertIn("different code", str(cm.exception))
        with mock.patch.object(M, "_git", FakeGit()):
            self.assertEqual(M._seal(), ("2026-10-05", "2026-10-05T09:00:00Z"))
        self.assertIn(M.SCRIPT, M.COMMITTED)
        self.assertIn(M.PREREG, M.COMMITTED)
        self.assertIn(M.REPRICE, M.COMMITTED)
        self.assertFalse(os.path.exists(want))

    def test_one_read_per_process(self):
        M._PROCESS["used"] = None
        M._require_fresh_process("run R1")
        with self.assertRaises(SystemExit):
            M._require_fresh_process("run R1-P1")
        M._PROCESS["used"] = None

    def test_a_prior_record_is_tied_to_history_and_registration(self):
        meta = json.loads(json.dumps(dict(M._meta("read", "R1"), guarded=True), default=str))
        open(self.p("r0.json"), "w").write("{}")
        moved = {"path": os.path.relpath(self.p("r0.json"), ROOT), "sha256": "0" * 64}
        cases = ((dict(meta, guarded=False), FakeGit(), "guard"), (meta, FakeGit(ancestor=False), "ancestor"),
                 (dict(meta, parameters=dict(meta["parameters"], delta=0.3)), FakeGit(), "parameters"),
                 (dict(meta, costs=dict(meta["costs"], profile="x")), FakeGit(), "costs"),
                 (meta, FakeGit(dirty={"r.json"}), "uncommitted"),
                 (dict(meta, script_sha256="0" * 64), FakeGit(), "script_sha256"),        # a record of other code
                 (dict(meta, code_sha256=dict(meta["code_sha256"], **{"scripts/risk_model.py": "0" * 64})), FakeGit(),
                  "code_sha256"),
                 (dict(meta, counts=moved), FakeGit(), "has changed since"))              # its R0 is not the R0 now
        for m, git, msg in cases:
            with self.subTest(msg=msg), mock.patch.object(M, "_git", git), mock.patch.object(M, "_rel", lambda p: "r.json"):
                with self.assertRaises(SystemExit) as cm:
                    M._tie("r.json", {"meta": m}, True)
                self.assertIn(msg, str(cm.exception))
        with mock.patch.object(M, "_git", FakeGit()), mock.patch.object(M, "_rel", lambda p: "r.json"):
            self.assertIsNone(M._tie("r.json", {"meta": meta}, True))
        # a record that names its R0 is re-anchored on it: same file, still valid (_r0 under the guard)
        rel = "docs/experiments/wyckoff-retest-R0-counts.json"
        path = self.r0(json.loads(json.dumps(M._meta("counts"), default=str)))
        named = dict(meta, counts={"path": os.path.relpath(path, ROOT), "sha256": M._sha256(path)})
        seen = []
        with mock.patch.object(M, "_git", FakeGit()), mock.patch.object(M, "_rel", lambda p: rel), \
                mock.patch.object(M, "_r0", lambda p, clean: seen.append((p, clean))):
            M._tie("r.json", {"meta": named}, True)
        self.assertEqual([(os.path.normpath(q), c) for q, c in seen], [(os.path.normpath(path), True)])
        with mock.patch.object(M, "_git", FakeGit()), mock.patch.object(M, "_rel", lambda p: rel), \
                mock.patch.object(M, "_prereg_text", lambda: ""), self.assertRaises(SystemExit) as cm:
            M._tie("r.json", {"meta": named}, True)
        self.assertIn("does not name", str(cm.exception))

    def test_the_forward_window_starts_at_the_seal_and_nobody_moves_it(self):
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        with fresh(sealed, mock.patch.object(M, "_git", FakeGit())), self.assertRaises(SystemExit) as cm:
            M.forward("L1", self.p("f.json"), since="2026-11-01T00:00:00Z", loader=boom, l1=boom)
        self.assertIn("starts at the seal", str(cm.exception))
        with fresh(sealed), self.assertRaises(SystemExit) as cm:                    # since None = the seal instant
            M.forward("L1", self.p("f.json"), loader=boom, l1=boom, chain_paths={}, require_clean=False)
        self.assertIn("not a surviving cell", str(cm.exception))
        with mock.patch.object(sys, "argv", ["x", "forward", "--cell", "L1", "--since", "2027-01-01", "--out", "o"]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            M.main()                                                               # the CLI has no --since
        seen = []
        with mock.patch.object(M, "forward", lambda *a, **k: seen.append((a, k))), \
                mock.patch.object(sys, "argv", ["x", "forward", "--cell", "L1", "--out", "o.json"]):
            M.main()
        self.assertEqual(seen, [(("L1", "o.json"), {})])

    def test_report_reads_r4_records_only_as_this_scripts_tied_records(self):
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        good = {"meta": dict(json.loads(json.dumps(M._meta("forward", "R4-W-CTX"), default=str)), guarded=False),
                "cell": "W-CTX", "verdict": {"pass": False, "p_threshold": 0.1}}
        json.dump(good, open(self.p("r4.json"), "w"))
        none = {"R1": self.p("absent-R1.json")}
        with fresh(sealed):
            rep = M.report(self.p("rep.json"), paths=none, require_clean=False, r4_paths={"W-CTX": self.p("r4.json")})
        self.assertEqual(rep["R4"], {"W-CTX": {"pass": False, "p_threshold": 0.1}})
        json.dump({"cell": "W-CTX", "verdict": {"pass": True}}, open(self.p("hand.json"), "w"))   # hand-written
        for r4, n in (({"W-CTX": self.p("hand.json")}, "rep2"), ({"W-D-1H": self.p("r4.json")}, "rep3")):
            with fresh(sealed), self.assertRaises(SystemExit):
                M.report(self.p(f"{n}.json"), paths=none, require_clean=False, r4_paths=r4)
            self.assertFalse(os.path.exists(self.p(f"{n}.json")))
        with fresh(sealed, mock.patch.object(M, "_git", FakeGit()), mock.patch.object(M, "_rel", lambda p: "r4.json"),
                   mock.patch.object(M, "_require_canonical", lambda *a: None)), self.assertRaises(SystemExit) as cm:
            M.report(self.p("rep4.json"), paths=none, r4_paths={"W-CTX": self.p("r4.json")})    # under the guard: _tie
        self.assertIn("registration guard", str(cm.exception))
        self.assertFalse(os.path.exists(self.p("rep4.json")))

    def test_forward_gate(self):
        with self.assertRaises(SystemExit):
            M._forward_gate(99, "2026-10-05T00:00:00Z", "2027-10-04T00:00:00Z")
        self.assertIsNone(M._forward_gate(100, "2026-10-05T00:00:00Z", "2026-10-06T00:00:00Z"))
        self.assertIsNone(M._forward_gate(3, "2026-10-05T00:00:00Z", "2027-10-05T00:00:00Z"))


# ----------------------------------------------------------------------------------------------- the chain on synthetic bars
class Chain(unittest.TestCase):
    """counts -> R1 -> P1..P6 -> R2 / R3 -> report on synthetic 4H books (no real data, guard off, sealing mocked).
    [prereg §4 "Reads", §6, §10: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = cls.tmp.name
        cls.loader = FakeLoader()
        M._PROCESS["used"] = None
        with fresh(mock.patch.object(M, "COUNT_GATE", 1)):
            cls.r0 = M.counts(os.path.join(cls.d, "r0.json"), loader=cls.loader, vloader=boom,
                              symbols=("XAUUSD", "US500"), replication=("XPTUSD", "EU50"), vsyms=[], timeframes=("4H",),
                              v_timeframes=(), probe_n=40)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def p(self, name):
        return os.path.join(self.d, name)

    def test_1_counts_are_outcome_blind_and_complete(self):
        r0 = self.r0
        self.assertEqual(set(r0["reads"]), {"R1", "R2", "R3", "V"})
        self.assertTrue(r0["reads"]["R1"]["W-C-long-4H"]["placeable"] > 0)
        self.assertTrue(r0["reads"]["R3"]["W-C-long-4H"]["signals"] > 0)
        self.assertIn("W-CAMP", r0["reads"]["R1"])
        self.assertIsNotNone(r0["gc_n"]["4H"])
        self.assertEqual(r0["gc_n"]["4H"], 92 - 40)                                  # every synthetic break is SC + 52
        self.assertTrue(r0["probe"]["ok"], r0["probe"])
        self.assertIn("W-C-long-4H", r0["confirmatory"]["W"])
        self.assertEqual(r0["dense"]["XAUUSD|4H"]["start"], "2023-12-01")
        self.assertIn("planned_rr", r0["reads"]["R1"]["W-C-long-4H"])
        forbidden = {"R", "excess", "placebo", "net_excess", "cost", "mean_R", "outcome", "exit_time", "p_one_sided",
                     "upper_95", "X", "filled"}

        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)
        self.assertFalse(forbidden & set(keys({k: v for k, v in r0.items() if k != "meta"})))

    def test_1b_counts_touch_no_outcome_function(self):
        def refuse(*a, **k):
            raise AssertionError("R0 touched an outcome function")
        names = ("score", "score_campaign", "walk_from", "campaign_walk", "campaign_R", "campaign_cost", "summarise",
                 "placebo_draw")
        with fresh(*[mock.patch.object(M, n, refuse) for n in names],
                   mock.patch.object(M.Pricer, "trade", refuse), mock.patch.object(BT, "walk", refuse)):
            M.counts(self.p("r0b.json"), loader=FakeLoader(), vloader=boom, symbols=("XAUUSD",), replication=(),
                     vsyms=[], timeframes=("4H",), v_timeframes=(), probe_n=5)

    def test_2_the_read_chain(self):
        sealed = mock.patch.object(M, "_require_sealed", lambda: SEALED)
        kw = dict(require_clean=False, loader=self.loader, cost_r=fake_cost_r, timeframes=("4H",))
        with fresh(sealed):
            r1 = M.run("R1", self.p("edge-wyckoff-R1.json"), counts_path=self.p("r0.json"), symbols=("XAUUSD", "US500"),
                       **kw)
        t = r1["tests"]["W-C-long-4H"]
        self.assertTrue(t["confirmatory"] and t["summary"]["n"] > 0)
        self.assertEqual(set(t["summary"]["lines"]), set(M.FTMO_LINES))
        self.assertIn("verdict", t)
        self.assertIn("gc_contrast", t)
        self.assertIn("gc_contrast_known", t)
        self.assertGreater(r1["descriptive"]["G-C"]["n"], 0)
        self.assertGreaterEqual(r1["descriptive"]["G-C-known"]["n"], r1["descriptive"]["G-C"]["n"] // 2)
        self.assertTrue(any(k.startswith("desc:W-C-long-4H|") for k in r1["descriptive"]))
        for c in ("desc:W-C-long-4H|ceiling-target", "desc:W-C-long-4H|flatten", "desc:W-D-4H|flatten",
                  "desc:W-C-long-4H|trend-placebo", "desc:W-D-4H|trend-placebo", "desc:W-CTX|trend-placebo"):
            self.assertIn(c, r1["descriptive"])
        self.assertGreater(r1["descriptive"]["desc:W-C-long-4H|trend-placebo"]["n"], 0)
        self.assertIn("XAUUSD|1D", r1["data"])                                      # 1D read (descriptive only)
        self.assertFalse(any(k.startswith("desc:") or k.endswith("-1D") for k in r1["tests"]))
        rows = r1["rows"]["W-C-long-4H"]
        self.assertTrue(all(r["signal_time"] < M.DEV_CUTOFF and r["entry_time"] < M.DEV_CUTOFF for r in rows))
        self.assertTrue(all(r["n_placebo"] > 0 and set(r["cost"]) == set(M.FTMO_LINES) for r in rows))
        self.assertTrue(all(abs(r["net_excess"] - (r["excess"] - r["cost"]["median_swap"])) < 1e-12 for r in rows))
        self.assertTrue(all("excess_trend" in r for r in rows))
        self.assertEqual(r1["meta"]["code_sha256"], M.code_sha256())
        camp = r1["rows"]["W-CAMP"]
        self.assertTrue(camp and all(r["filled"] for r in camp))
        saved = json.load(open(self.p("edge-wyckoff-R1.json")))
        self.assertEqual(saved["registered"]["gc_n"], self.r0["gc_n"])
        with fresh(sealed), self.assertRaises(SystemExit):                          # each read ONCE
            M.run("R1", self.p("edge-wyckoff-R1.json"), counts_path=self.p("r0.json"), symbols=("XAUUSD",), **kw)
        # the perturbations read only the cells meeting gates 1-3: force one, as a survivor-to-be would
        saved["tests"]["W-C-long-4H"]["verdict"]["gates_1_3"] = True
        json.dump(saved, open(self.p("edge-wyckoff-R1.json"), "w"))
        for p in M.PERTURBATIONS:
            with fresh(sealed):
                rp = M.run("R1", self.p(f"edge-wyckoff-R1-{p}.json"), after=self.p("edge-wyckoff-R1.json"), perturb=p,
                           symbols=("XAUUSD", "US500"), **kw)
            self.assertEqual(list(rp["tests"]), ["W-C-long-4H"], p)
            self.assertEqual(rp["meta"]["perturb"], p)
        with fresh(sealed):
            rp = json.load(open(self.p("edge-wyckoff-R1-P6.json")))
        self.assertTrue(all(r["bars_held"] <= 60 for r in rp["rows"]["W-C-long-4H"]))
        # R2 / R3 refuse without a survivor; with one they read only survivor cells
        signs = {p: json.load(open(self.p(f"edge-wyckoff-R1-{p}.json"))) for p in M.PERTURBATIONS}
        if M.survivors(saved, signs)["W-C-long-4H"]["survivor"] is False:
            with fresh(sealed), self.assertRaises(SystemExit):
                M.run("R2", self.p("edge-wyckoff-R2.json"), after=self.p("edge-wyckoff-R1.json"), symbols=("XPTUSD",),
                      **kw)
        for p, rec in signs.items():
            rec["tests"]["W-C-long-4H"]["summary"].update(n=5, net_excess=0.1)
            json.dump(rec, open(self.p(f"edge-wyckoff-R1-{p}.json"), "w"))
        with fresh(sealed):
            r2 = M.run("R2", self.p("edge-wyckoff-R2.json"), after=self.p("edge-wyckoff-R1.json"),
                       symbols=("XPTUSD", "EU50"), **kw)
        self.assertEqual(list(r2["tests"]), ["W-C-long-4H"])
        self.assertIn("r2_pass", r2["tests"]["W-C-long-4H"])
        self.assertTrue(all(r["symbol"] in ("XPTUSD", "EU50") for r in r2["rows"]["W-C-long-4H"]))
        with fresh(sealed):
            r3 = M.run("R3", self.p("edge-wyckoff-R3.json"), after=self.p("edge-wyckoff-R1.json"),
                       symbols=("XAUUSD", "US500"), **kw)
        self.assertIn("r3_veto", r3["tests"]["W-C-long-4H"])
        self.assertTrue(all(r["entry_time"] >= M.DEV_CUTOFF for r in r3["rows"]["W-C-long-4H"]))
        paths = {n: self.p(f"edge-wyckoff-{n}.json") for n in ["R1", "R2", "R3"] + [f"R1-{p}" for p in M.PERTURBATIONS]}
        with fresh(sealed):
            rep = M.report(self.p("edge-wyckoff-report.json"), paths=paths, require_clean=False)
        self.assertEqual(set(rep["W"]), set(M.W_CELLS))
        self.assertEqual(rep["W"]["W-C-long-15m"]["label"], "DESCRIPTIVE")
        self.assertIn(rep["W"]["W-C-long-4H"]["label"], ("EDGE-CANDIDATE", "AGAINST THE BOOK", "NO MECHANICAL EDGE",
                                                         "INCONCLUSIVE"))
        self.assertIn("closing", rep)
        self.assertTrue(os.path.exists(self.p("edge-wyckoff-report.md")))
        with fresh(sealed), self.assertRaises(SystemExit):                          # R4 reads surviving cells only
            M.forward("W-D-4H", self.p("edge-wyckoff-R4-W-D-4H.json"), loader=boom, chain_paths=paths,
                      require_clean=False)


class L1(unittest.TestCase):
    """L1 through a stub of reprice_real_costs (its config A, scan, simulate): the 6 indices pooled, CR1 by date.
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def stub(self, nets):
        calls = []

        class BTs:
            OPTS = {}

            def reset_opts(self):
                BTs.OPTS = {}

            def scan(self, sym, tf, opts=None):
                calls.append(("scan", sym, tf, opts))
                tr = [{"entry_time": f"2024-0{3 + i % 6}-{10 + i % 9:02d}T10:00:00Z", "exit_time": "x", "side": "long",
                       "R": 1.0, "net_R": nets.get(sym, 0.0) + 0.3 * math.sin(i), "leg": "spring"} for i in range(25)]
                return {"trades": {"WYCKOFF-BOOK": tr + [dict(tr[0], entry_time="2024-02-01T00:00:00Z")]}}

            def simulate(self, trades, fee, entry_order_type=None, live_parity_sizing=None, cost_profile=None):
                calls.append(("simulate", len(trades), fee, entry_order_type, live_parity_sizing, cost_profile))
                return None, None, trades

        class RP:
            bt = BTs()
            CONFIG_A = {"mgmt": "none"}
            FEE, PROFILE, TF = 0.0005, "ftmo_demo_2026_09", "15m"
            _M = type("Mm", (), {"RUNNER_METHODS": {"WYCKOFF-BOOK": {"entry": "market"}}})
        return RP, calls

    def test_l1_pools_the_indices_after_the_cutoff_through_reprice_config_a(self):
        RP, calls = self.stub({s: 0.2 for s in M.L1_SYMBOLS})
        rows, desc = M.run_l1(RP)
        self.assertEqual(len(rows), 25 * 6)
        self.assertTrue(all(r["entry_time"] >= M.DEV_CUTOFF for r in rows))
        sims = [c for c in calls if c[0] == "simulate"]
        self.assertTrue(all(c[2:] == (0.0005, "taker", False, "ftmo_demo_2026_09") for c in sims))
        self.assertTrue(all(c[2] == "15m" and c[3] == {"mgmt": "none"} for c in calls if c[0] == "scan"))
        self.assertEqual(set(desc), set(M.L1_DESCRIPTIVE))
        s = M.l1_summary(rows)
        mu, se, df = EC.cr1([r["net_R"] for r in rows], [r["date"] for r in rows])
        self.assertAlmostEqual(s["mean_net_R"], mu)
        self.assertTrue(s["pass"])
        self.assertFalse(M.l1_summary([dict(r, net_R=-r["net_R"]) for r in rows])["pass"])

    def test_the_forward_gate_runs_before_any_trade_is_admitted(self):
        RP, calls = self.stub({})
        seen = []

        def gate(n):
            seen.append(n)
            M._forward_gate(n - 60, "2026-10-05T00:00:00Z", "2026-11-01T00:00:00Z")     # 90 < 100 forward trades
        with self.assertRaises(SystemExit):
            M.run_l1(RP, descriptive=False, gate=gate)
        self.assertEqual(seen, [150])
        self.assertFalse([c for c in calls if c[0] == "simulate"])


class DenseFinalMonth(unittest.TestCase):
    def test_a_partial_final_month_does_not_erase_the_dense_start(self):
        import datetime as _dt
        UTC_ = _dt.timezone.utc
        days, dts = [], []
        d = _dt.date(2023, 1, 2)
        while d <= _dt.date(2023, 3, 31):
            if d.weekday() < 5:
                for k in range(92):
                    days.append(d)
                    dts.append(_dt.datetime(d.year, d.month, d.day, tzinfo=UTC_) + _dt.timedelta(minutes=15 * k))
            d += _dt.timedelta(days=1)
        for k in range(17):                                  # 2023-04-03: a partial final month, 17 bars
            days.append(_dt.date(2023, 4, 3))
            dts.append(_dt.datetime(2023, 4, 3, tzinfo=UTC_) + _dt.timedelta(minutes=15 * k))
        self.assertEqual(M.dense_start(days, dts)["start"], "2023-01-01")


if __name__ == "__main__":
    unittest.main()
