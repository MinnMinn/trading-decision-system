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

    def test_eod_rows_wait_for_the_day_to_end(self):
        bars1 = bars("2026-10-05T20:00:00", [(100.0, 100.5, 99.5, 100.0)] * 20)          # 20:00-21:35 UTC, one server day
        s = EC.Series("XAUUSD", bars1, UTC, end="9999-12-31T00:00:00Z")
        row = {"symbol": "XAUUSD", "h": "eod", "side": 1, "entry_time": s.T[2], "entry": 100.0, "stop": 98.0,
               "stop_distance": 2.0, "status": "open"}
        self.assertEqual(FF.resolve_row(s, row, Costs0()), row)                         # no later-day bar yet
        s2 = EC.Series("XAUUSD", bars1 + bars("2026-10-07T00:00:00", [(101.0, 101.5, 100.5, 101.0)] * 3), UTC,
                       end="9999-12-31T00:00:00Z")
        r = FF.resolve_row(s2, row, Costs0())
        self.assertEqual((r["status"], r["exit_time"]), ("closed", s2.T[19]))

    def test_every_watched_component_is_known(self):
        self.assertEqual(set(FF.WATCH), {"E5_XAUUSD_24", "E5_US500_48", "H7_XAUUSD_eod"})

    def test_accumulate_builds_a_store_and_warns_on_a_hole(self):
        import json, tempfile
        live, store = tempfile.mkdtemp(), tempfile.mkdtemp()
        b1 = bars("2030-01-07T10:00:00", [(1.0, 1.1, 0.9, 1.0)] * 3)                 # a Monday
        json.dump({"candles": b1}, open(os.path.join(live, "ohlcv.XAUUSD.5m.json"), "w"))
        n, w = FF.accumulate("XAUUSD", live, store)
        self.assertEqual(n, 3)
        self.assertIsNotNone(w)                       # the stored history ends years before 2030: a hole, warned
        b2 = bars("2030-01-07T10:10:00", [(1.0, 1.1, 0.9, 1.0)] * 3)                 # overlaps by one bar
        json.dump({"candles": b2}, open(os.path.join(live, "ohlcv.XAUUSD.5m.json"), "w"))
        n, w = FF.accumulate("XAUUSD", live, store)
        self.assertEqual((n, w), (2, None))
        self.assertEqual(len(json.load(open(os.path.join(store, "XAUUSD.5m.json")))), 5)

    def test_places_no_order(self):
        src = open(os.path.join(ROOT, "scripts", "research", "fvg_forward.py")).read()
        for word in ("order_send", "mcp", "execute(", "strategy-runner"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
