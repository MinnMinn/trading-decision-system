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
            return {"balance": 100000}
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


if __name__ == "__main__":
    unittest.main()
