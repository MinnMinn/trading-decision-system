"""scripts/research/fvg_forward.py on HAND-BUILT bars only (paper log; no account, no real outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fvg_forward
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("fvg_forward", os.path.join(ROOT, "scripts", "research", "fvg_forward.py"))
FF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FF)
EC = FF.EC
UTC = datetime.timezone.utc


def bars(start, ohlc):
    t0 = datetime.datetime.fromisoformat(start).replace(tzinfo=UTC)
    return [{"time": (t0 + datetime.timedelta(minutes=5 * k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "open": o, "high": h, "low": l, "close": c} for k, (o, h, l, c) in enumerate(ohlc)]


class Costs0:
    def round_trip(self, a, b, stat="median"):
        return 0.0


class Forward(unittest.TestCase):
    def test_resolve_time_exit_and_stop(self):
        s = EC.Series("XAUUSD", bars("2026-10-05T00:00:00", [(100.0, 100.5, 99.5, 100.0)] * 30 +
                                     [(100.0, 101.0, 99.9, 101.0)] * 30), UTC, end="9999-12-31T00:00:00Z")
        row = {"symbol": "XAUUSD", "h": 24, "side": 1, "entry_time": s.T[0], "entry": 100.0, "stop": 98.0,
               "stop_distance": 2.0, "status": "open"}
        r = FF.resolve_row(s, row, Costs0())
        self.assertEqual((r["status"], r["exit_reason"], r["exit_time"]), ("closed", "time", s.T[23]))
        self.assertAlmostEqual(r["R"], 0.0)
        r2 = FF.resolve_row(s, dict(row, stop=99.6, stop_distance=0.4), Costs0())
        self.assertEqual(r2["exit_reason"], "stop")
        self.assertAlmostEqual(r2["R"], -1.0)

    def test_open_row_waits_for_its_exit_bar(self):
        s = EC.Series("XAUUSD", bars("2026-10-05T00:00:00", [(100.0, 100.5, 99.5, 100.0)] * 10), UTC,
                      end="9999-12-31T00:00:00Z")
        row = {"symbol": "XAUUSD", "h": 24, "side": 1, "entry_time": s.T[0], "entry": 100.0, "stop": 98.0,
               "stop_distance": 2.0, "status": "open"}
        self.assertEqual(FF.resolve_row(s, row, Costs0()), row)

    def test_places_no_order(self):
        src = open(os.path.join(ROOT, "scripts", "research", "fvg_forward.py")).read()
        for word in ("order_send", "mcp", "execute(", "strategy-runner"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
