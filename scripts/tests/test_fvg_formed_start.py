"""D3 (docs/audits/2026-10-02-strategic-diagnosis.md §2 #3): `OPTS["fx_fvg_formed_start"]`.

v1 (key off) starts the ICT "already triggered" scan and the fill scan at `mss_i + 1`. When the MSS candle is the FVG's
MIDDLE candle (the canonical displacement FVG), bar `mss_i + 1` is the FVG's THIRD candle, whose own low (bull) / high
(bear) IS the IOFED edge, so `L[j] <= edge` is trivially true and the setup is always refused. With the key on, both
scans start after the third candle has closed; the K-bar expiry stays anchored on `mss_i`.

Every series here is hand-built: no real history, no R / expectancy of any evaluation.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fvg_formed_start
"""
import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _bt():
    spec = importlib.util.spec_from_file_location("bt_fvg_formed_start", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (high, low, close); bar 5 is the displacement / MSS candle and the FVG's middle candle: H[4]=101 < L[6]=103.
BULL = [(101.0, 99.0, 100.0), (100.0, 96.0, 97.0), (99.0, 96.5, 98.5), (100.5, 98.0, 100.0),
        (101.0, 99.5, 100.8), (106.0, 100.5, 105.8), (107.0, 103.0, 106.5),
        (106.0, 102.8, 103.5),            # bar 7: first bar after the gap exists; retraces into the edge 103 -> fill
        (125.0, 103.5, 124.5), (125.0, 120.0, 121.0)]


def _case(bt, bars=BULL, mss_i=5, fvg_i=5, side="long", entry=103.0, stop=96.0, target=124.0, i=6, K=12):
    H = [b[0] for b in bars]; L = [b[1] for b in bars]; C = [b[2] for b in bars]
    Tm = [f"2023-01-02T{h:02d}:00:00Z" for h in range(len(bars))]
    x = types.SimpleNamespace(sym="XAUUSD", tf="1H", c=None, Tm=Tm, H=H, L=L, C=C, O=[c for c in C], methods=("ict",),
                              n=len(bars), idx_of_time={t: j for j, t in enumerate(Tm)}, hz=50, b7_kz=False, K=K)
    su = {"side": side, "entry": entry, "stop": stop, "target": target, "R": (target - entry) / (entry - stop),
          "entry_models": {"fill": H[fvg_i - 1]}, "mss": {"time": Tm[mss_i]}, "fvg": {"time": Tm[fvg_i]},
          "sweep": {"time": Tm[1]}}
    return x, su, i


class _Base(unittest.TestCase):
    def setUp(self):
        self.bt = _bt()

    def tearDown(self):
        self.bt.reset_opts()

    def opts(self, **kw):
        self.bt.OPTS = dict(self.bt._OPTS_BASE, **kw)


class Registered(_Base):
    def test_off_by_default_and_live_never_sets_it(self):
        self.assertIs(self.bt._OPTS_BASE["fx_fvg_formed_start"], False)
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("fx_fvg_formed_start", src)

    def test_fund_search_adopts_it(self):
        src = open(os.path.join(ROOT, "scripts", "fund-search.py"), encoding="utf-8").read()
        start = src.index("ADOPTED_F_KEYS = (")
        self.assertIn('"fx_fvg_formed_start"', src[start:src.index(")", start)])


class SelfTouch(_Base):
    def test_v1_refuses_the_displacement_fvg_through_its_own_third_candle(self):
        self.opts(fx_fvg_formed_start=False)
        x, su, i = _case(self.bt)
        self.assertIsNone(self.bt._ict_trade(x, i, su))

    def test_d3_takes_it_and_fills_after_the_gap_exists(self):
        self.opts(fx_fvg_formed_start=True)
        x, su, i = _case(self.bt)
        t = self.bt._ict_trade(x, i, su)
        self.assertIsNotNone(t)
        self.assertEqual(t["entry_time"], x.Tm[7])         # never the third candle (bar 6) itself
        self.assertEqual(t["outcome"], "win")

    def test_d3_still_refuses_a_real_earlier_touch(self):
        """Detection at bar 7 after bar 7 already traded the edge: a genuine 'already triggered' stays refused."""
        self.opts(fx_fvg_formed_start=True)
        x, su, _ = _case(self.bt)
        self.assertIsNone(self.bt._ict_trade(x, 7, su))

    def test_d3_keeps_expiry_anchored_on_the_mss(self):
        self.opts(fx_fvg_formed_start=True)
        x, su, i = _case(self.bt, K=2)                    # window mss+1 .. mss+2 = bars 6, 7
        self.assertIsNotNone(self.bt._ict_trade(x, i, su))
        x, su, i = _case(self.bt, K=1)                    # window = bar 6 only, which precedes the gap -> no order
        self.assertIsNone(self.bt._ict_trade(x, i, su))

    def test_bear_mirror(self):
        bars = [(102.0, 100.0, 101.0), (105.0, 103.0, 104.0), (104.5, 102.0, 102.5), (103.0, 100.0, 101.0),
                (101.5, 99.0, 99.2), (99.5, 94.0, 94.2), (97.0, 93.0, 93.5),       # L[4]=99 > H[6]=97: bear FVG, edge 97
                (97.2, 95.0, 96.0), (96.0, 75.0, 76.0), (80.0, 74.0, 79.0)]
        for on, expect_trade in ((False, False), (True, True)):
            self.opts(fx_fvg_formed_start=on)
            x, su, i = _case(self.bt, bars=bars, side="short", entry=97.0, stop=105.0, target=76.0)
            su["entry_models"] = {"fill": bars[4][1]}
            self.assertEqual(self.bt._ict_trade(x, i, su) is not None, expect_trade, on)


class Helpers(_Base):
    def test_start_is_the_bar_after_the_third_candle(self):
        x, su, _ = _case(self.bt)
        self.assertEqual(self.bt.fvg_formed_start(su, x.idx_of_time), 7)
        su["fvg"]["time"] = "unknown"
        self.assertIsNone(self.bt.fvg_formed_start(su, x.idx_of_time))

    def test_fvg_fill_default_start_is_unchanged(self):
        x, su, _ = _case(self.bt)
        a = self.bt.fvg_fill("long", 5, 103.0, 101.0, 96.0, x.H, x.L, 12, x.n)
        b = self.bt.fvg_fill("long", 5, 103.0, 101.0, 96.0, x.H, x.L, 12, x.n, start=None)
        self.assertEqual(a, b)
        self.assertEqual(a[0], 6)                         # v1: the third candle "fills" itself
        self.assertEqual(self.bt.fvg_fill("long", 5, 103.0, 101.0, 96.0, x.H, x.L, 12, x.n, start=7)[0], 7)


if __name__ == "__main__":
    unittest.main()
