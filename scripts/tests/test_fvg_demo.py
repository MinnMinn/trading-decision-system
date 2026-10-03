"""scripts/fvg_demo.py with a FAKE bridge and hand-built bars: the safety gates and the order lifecycle. No terminal, no account.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fvg_demo
"""
import datetime
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("fvg_demo", os.path.join(ROOT, "scripts", "fvg_demo.py"))
FD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FD)
EC = FD.EC
UTC = datetime.timezone.utc
CFG = {"enabled": True, "risk_pct": 0.01, "components": {"XAUUSD": 24}, "bridge_subdir": "x", "max_bar_age_minutes": 15,
       "close_before_rollover_minutes": 10, "tp_stop_multiple": 5}


class FakeBridge:
    def __init__(self, demo=True):
        self.demo, self.calls, self.orders, self.n = demo, [], {}, 100

    def __call__(self, *a):
        self.calls.append(a)
        cmd = a[0]
        if cmd == "check":
            return {"demo": self.demo}
        if cmd == "account":
            return {"balance": getattr(self, "balance", 100000)}
        if cmd == "symbol":
            return {"tick_value": 1.0, "tick_size": 0.01, "volume_step": 0.01, "volume_min": 0.01, "volume_max": 50,
                    "digits": 2}
        if cmd == "limit":
            self.n += 1
            self.orders[self.n] = {"state": "pending", "price": float(a[4])}
            return {"ok": True, "ticket": self.n}
        if cmd == "order-status":
            return dict(self.orders[int(a[1])])
        if cmd == "cancel":
            self.orders[int(a[1])]["state"] = "canceled"
            return {"ok": True}
        if cmd == "position-status":
            return {"state": "open"}
        if cmd == "market":
            return {"ok": True, "ticket": 555, "price": 0.0 + float(a[4]) * 0 + 1.0}
        if cmd == "close":
            return {"ok": True, "price": 1.0}
        raise AssertionError(a)


def series_with_fresh_gap():
    """21 dense flat days, then a displacement FVG whose third bar is the last closed bar."""
    t0 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    bars, k = [], 0
    for d in range(22):
        for b in range(288 if d < 21 else 40):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            px = 2000.0 + (0.3 if b % 2 else -0.3)
            bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
    last = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00"))
    for j, (o, h, l, c) in enumerate([(2000.0, 2000.4, 1999.6, 2000.2), (2000.2, 2006.0, 2000.2, 2005.8),
                                      (2005.8, 2007.0, 2002.0, 2006.5)]):
        t = last + datetime.timedelta(minutes=5 * (j + 1))
        bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c})
    s = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    now = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=6)
    return s, now


class Gates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = dict(state_path=os.path.join(self.tmp, "s.json"), log_path=os.path.join(self.tmp, "l.jsonl"))
        self.s, self.now = series_with_fresh_gap()
        p = mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: self.s)
        p.start(); self.addCleanup(p.stop)
        z = mock.patch.object(FD.FF, "_zone", lambda: UTC)
        z.start(); self.addCleanup(z.stop)

    def test_disabled_does_nothing(self):
        b = FakeBridge()
        self.assertEqual(FD.tick(self.now, b, dict(CFG, enabled=False), **self.paths, event_blocked=lambda s, t: (False, "")), "disabled")
        self.assertEqual(b.calls, [])

    def test_non_demo_account_is_refused_before_anything(self):
        b = FakeBridge(demo=False)
        self.assertEqual(FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, "")), "refused")
        self.assertEqual([c[0] for c in b.calls], ["check"])

    def test_places_one_limit_with_its_stop_then_never_twice(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        lim = [c for c in b.calls if c[0] == "limit"]
        self.assertEqual(len(lim), 1)
        _, sym, side, lots, px, sl, tp, _cmt = lim[0]
        self.assertEqual((sym, side, px), ("XAUUSD", "buy", "2002.00"))      # the gap's near edge = third bar's low
        self.assertLess(float(sl), float(px))
        self.assertGreater(float(tp), float(px))
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertEqual(len([c for c in b.calls if c[0] == "limit"]), 1)

    def test_event_risk_blocks_a_new_entry(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (True, "NFP window"))
        self.assertFalse([c for c in b.calls if c[0] == "limit"])

    def test_stale_bars_block_a_new_entry(self):
        b = FakeBridge()
        FD.tick(self.now + datetime.timedelta(hours=2), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertFalse([c for c in b.calls if c[0] == "limit"])

    def test_risk_is_clamped_to_the_ceiling(self):
        import trading_env      # noqa: F401  (read the real ceiling BEFORE open() is mocked)
        with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(dict(CFG, risk_pct=0.05)))):
            self.assertLessEqual(FD.load_config("x")["risk_pct"], 0.01)

    def test_fill_then_time_exit(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        tk = max(b.orders)
        b.orders[tk] = {"state": "filled", "price": 2002.0, "position_ticket": 777}
        FD.tick(self.now + datetime.timedelta(minutes=5), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        st = json.load(open(self.paths["state_path"]))
        self.assertEqual(len(st["open"]), 1)
        FD.tick(self.now + datetime.timedelta(hours=3), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertIn(("close", 777), b.calls)
        self.assertEqual(json.load(open(self.paths["state_path"]))["open"], [])


def series_with_h7_breakout():
    """22 dense rising days, then a partial day whose last closed bar closes above the previous day's high."""
    t0 = datetime.datetime(2026, 8, 3, tzinfo=UTC)
    bars = []
    for d in range(23):
        base = 2000.0 + 5.0 * min(d, 21)          # the partial last day opens inside the previous day's range
        for b in range(288 if d < 22 else 30):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            px = base + (0.3 if b % 2 else -0.3)
            bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
    prev_high = 2000.0 + 5.0 * 21 + 0.8
    t = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=5)
    bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": prev_high - 1, "high": prev_high + 3, "low": prev_high - 1,
                 "close": prev_high + 2})
    s = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    return s, t + datetime.timedelta(minutes=6)


class H7(unittest.TestCase):
    def test_market_entry_on_the_breakout_bar_once(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        cfg = dict(CFG, components={}, h7_symbols=["XAUUSD"])
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: s), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            b = FakeBridge()
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual(len(mk), 1)
        self.assertEqual(mk[0][1:3], ("XAUUSD", "buy"))
        self.assertLess(float(mk[0][4]), s.C[-1])          # the stop is below the entry reference


class DataGate(unittest.TestCase):
    def test_a_hole_in_the_decision_window_blocks_new_entries(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        keep = [i for i, t in enumerate(s.T) if not ("2026-08-19" <= t[:10] <= "2026-08-20")]   # a Wed-Thu hole
        bars = [{"time": s.T[i], "open": s.O[i], "high": s.H[i], "low": s.L[i], "close": s.C[i]} for i in keep]
        holed = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
        cfg = dict(CFG, components={"XAUUSD": 24}, h7_symbols=["XAUUSD"])
        b = FakeBridge()
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: holed), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        self.assertFalse([c for c in b.calls if c[0] in ("market", "limit")])
        rows = [json.loads(l) for l in open(paths["log_path"])]
        self.assertTrue(any("data hole" in r.get("reason", "") for r in rows))


class Isolation(unittest.TestCase):
    def test_a_symbol_the_ea_does_not_know_never_blocks_the_others(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()

        class Partial(FakeBridge):
            def __call__(self, *a):
                if a[0] == "symbol" and a[1] == "US500":
                    self.calls.append(a)
                    return {"ok": False, "comment": "symbol US500.cash not in the EA's symbols.json"}
                return super().__call__(*a)

        def boom(sym, now, live_dir=None):
            if sym == "AUS200":
                raise RuntimeError("corrupt bridge file")
            return s
        cfg = dict(CFG, components={"AUS200": 48}, h7_symbols=["US500", "XAUUSD"])
        b = Partial()
        with mock.patch.object(FD, "closed_series", boom), mock.patch.object(FD.FF, "_zone", lambda: UTC):
            self.assertEqual(FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, "")), "ok")
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual([c[1] for c in mk], ["XAUUSD"])                  # US500 skipped, AUS200 errored, gold still traded
        kinds = [json.loads(l)["kind"] for l in open(paths["log_path"])]
        self.assertIn("error", kinds)
        self.assertIn("skip", kinds)
        self.assertTrue(os.path.exists(paths["state_path"]))              # the state is still written


class V2(unittest.TestCase):
    """Trading System v2: G9 gold market entries and the dd3 drawdown throttle."""

    def _run(self, cfg, now_shift=datetime.timedelta(0), balances=(100000,)):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        b = FakeBridge()
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: s), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            for bal in balances:
                b.balance = bal
                FD.tick(now + now_shift, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        return b, s, paths

    def test_g9_places_one_market_order_on_the_live_last_bar(self):
        cfg = dict(CFG, components={}, h7_symbols=[], g9_symbols=["XAUUSD"])
        b, s, _ = self._run(cfg, balances=(100000, 100000))
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual(len(mk), 1)
        self.assertEqual((mk[0][1], mk[0][2], mk[0][-1]), ("XAUUSD", "buy", "g9-XAUUSD"))

    def test_g9_signal_ignored_in_the_research_series(self):
        s, _ = series_with_h7_breakout()
        research = EC.Series("XAUUSD", [{"time": t, "open": o, "high": h, "low": l, "close": c}
                                        for t, o, h, l, c in zip(s.T, s.O, s.H, s.L, s.C)], UTC, end="9999-12-31T00:00:00Z")
        self.assertFalse([e for e in FD.FF._f4().ev_vol_breakout(research) if e["i"] == len(research.T) - 1])
        self.assertTrue([e for e in FD.FF._f4().ev_vol_breakout(s) if e["i"] == len(s.T) - 1])

    def test_no_entry_inside_the_pre_rollover_window(self):
        cfg = dict(CFG, components={}, h7_symbols=["XAUUSD"], close_before_rollover_minutes=24 * 60)
        b, _s, paths = self._run(cfg)
        self.assertFalse([c for c in b.calls if c[0] == "market"])

    def test_throttle_steps_and_never_raises_risk(self):
        cfg = dict(CFG, throttle={"kind": "dd3", "initial_balance": 100000})
        self.assertEqual(FD.throttle_mult(cfg, 99000, 100000), 1.0)
        self.assertEqual(FD.throttle_mult(cfg, 96000, 100000), 0.5)
        self.assertEqual(FD.throttle_mult(cfg, 93000, 100000), 0.25)
        self.assertEqual(FD.throttle_mult(cfg, 50000, None), 0.25)          # unknown reference: most conservative
        self.assertEqual(FD.throttle_mult(dict(CFG), 50000, 100000), 1.0)   # no throttle configured
        st = {}
        self.assertEqual(FD.sizing(cfg, st, 120000), (0.01, 100000))        # sized on the INITIAL balance, never above 1 %
        self.assertEqual(FD.sizing(cfg, st, 95000), (0.005, 100000))
        st2 = {}
        cfg2 = dict(CFG, throttle={"kind": "dd3", "initial_balance": None})
        FD.sizing(cfg2, st2, 80000)
        self.assertEqual(st2["initial_balance"], 80000)                     # first balance seen becomes the reference
        self.assertEqual(FD.sizing(cfg2, st2, 75000)[0], 0.0025)

    def test_throttled_lots_are_smaller(self):
        info = {"tick_value": 1.0, "tick_size": 0.01, "volume_step": 0.01, "volume_max": 50}
        full = FD.lots_for(info, 100000, 0.01, 2000.0, 1990.0)
        half = FD.lots_for(info, 100000, 0.005, 2000.0, 1990.0)
        self.assertAlmostEqual(half, full / 2, places=6)


if __name__ == "__main__":
    unittest.main()
