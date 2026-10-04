"""scripts/research/fvg_forward.py on HAND-BUILT bars only (paper log; no account, no real outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fvg_forward
"""
import datetime
import importlib.util
import os
import unittest
from unittest import mock

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

    def round_trip_at(self, a, b, stat="median"):
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
        self.assertEqual(set(FF.WATCH), {"H7_XAUUSD_eod", "G9_XAUUSD_eod", "G9_XAGUSD_eod"})        # E5 left 2026-10-03 (erratum)

    def test_the_paper_stop_is_the_demo_book_at_the_signal_time(self):
        """Point in time: before asg-0004 (fvg-book v4, 2026-10-03T18:10Z) the demo traded H7 / G9 gold at 2.0; from it, 1.4.
        A row logged later (a scan run after the switch) must still carry the stop of ITS signal time."""
        self.assertEqual(FF.stop_k_at("G9_XAUUSD_eod", "2026-10-03T09:43:25Z"), 2.0)
        self.assertEqual(FF.stop_k_at("H7_XAUUSD_eod", "2026-09-30T10:00:00Z"), 2.0)
        self.assertEqual(FF.stop_k_at("G9_XAGUSD_eod", "2026-10-05T10:00:00Z"), 2.0)       # not in any book
        R = FF._registry()
        for row in R.assignments(FF.PAPER_TWIN_OF):
            comps = {(c["setup"], c["instrument"]): c["params"] for c in R.system_of(row)["components"]}
            for name in ("H7_XAUUSD_eod", "G9_XAUUSD_eod"):
                want = float(comps.get(tuple(name.split("_")[:2]), {}).get("stop_k", 2.0))
                self.assertEqual(FF.stop_k_at(name, row["effective_from"]), want, (row["id"], name))

    def test_g9_signal_logs_a_stop_and_unknown_kinds_refuse(self):
        import datetime as _dt
        t0 = _dt.datetime(2026, 9, 1, tzinfo=UTC)
        bs = []
        for d in range(25):
            n = 288 if d < 24 else 20
            for b in range(n):
                t = t0 + _dt.timedelta(days=d, minutes=5 * b)
                px = 100.0 + (0.1 if b % 2 else -0.1) + (2.0 if d == 24 and b >= 10 else 0.0)   # a jump at bar 10 of the last day
                bs.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
        s = EC.Series("XAUUSD", bs, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
        with mock.patch.object(FF, "FORWARD_START", "2000-01-01T00:00:00Z"):
            rows = FF.signals(s, "XAUUSD", "eod", "G9", "G9_XAUUSD_eod")
            self.assertEqual([(r["side"], r["signal_time"]) for r in rows][-1], (1, s.T[s.day_rows[s.sday[-1]][10]]))
            self.assertLess(rows[-1]["stop"], rows[-1]["entry"])
            self.assertEqual(rows[-1]["stop_k"], 2.0)                                   # 2026-09: the demo book's stop was 2.0
        with mock.patch.object(FF, "FORWARD_START", "2000-01-01T00:00:00Z"), \
                mock.patch.object(FF, "stop_k_at", lambda name, at: 1.4 if name == "G9_XAUUSD_eod" else 2.0):
            rows = FF.signals(s, "XAUUSD", "eod", "G9", "G9_XAUUSD_eod")
            self.assertEqual(rows[-1]["stop_k"], 1.4)
            ag = FF.signals(s, "XAGUSD", "eod", "G9", "G9_XAGUSD_eod")[-1]
            self.assertEqual(ag["stop_k"], 2.0)                                         # not in the book: unchanged
            self.assertAlmostEqual(rows[-1]["stop_distance"] / ag["stop_distance"], 0.7, places=9)
            with self.assertRaises(ValueError):
                FF.signals(s, "XAUUSD", "eod", "ZZ")

    def test_holes_skip_the_weekend_but_not_a_weekday_gap(self):
        fri, mon = "2026-09-25T20:55:00Z", "2026-09-27T22:00:00Z"            # Fri close -> Sun open: the weekend
        self.assertEqual(FF.holes([fri, mon]), [])
        a, b = "2026-09-28T17:00:00Z", "2026-10-02T04:10:00Z"                # Mon -> Fri: a real hole
        self.assertEqual(FF.holes([a, b]), [(a, b)])
        self.assertEqual(FF.holes(["2026-09-29T10:00:00Z", "2026-09-29T13:00:00Z"]), [])   # 3 h: a session gap
        self.assertEqual(FF.holes(["2026-09-07T16:55:00Z", "2026-09-07T22:05:00Z"]), [])   # US Labor Day early close
        self.assertEqual(FF.holes(["2026-12-24T18:00:00Z", "2026-12-27T23:00:00Z"]), [])   # Christmas Thu -> Sun
        t1, t2 = "2026-09-29T20:00:00Z", "2026-09-30T21:00:00Z"                              # Tue -> Wed: a missing day
        self.assertEqual(FF.holes([t1, t2]), [(t1, t2)])
        self.assertEqual(FF.holes([a, b], since=FF._dt("2026-10-03T00:00:00Z")), [])        # outside the window

    def test_paper_signal_after_a_hole_is_refused(self):
        import datetime as _dt
        t0 = _dt.datetime(2026, 9, 1, tzinfo=UTC)
        bs = []
        for d in range(25):
            if d in (14, 15):                                               # Tue-Wed 2026-09-15/16 missing
                continue
            n = 288 if d < 24 else 20
            for b in range(n):
                t = t0 + _dt.timedelta(days=d, minutes=5 * b)
                px = 100.0 + (0.1 if b % 2 else -0.1) + (2.0 if d == 24 and b >= 10 else 0.0)
                bs.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
        s = EC.Series("XAUUSD", bs, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
        with mock.patch.object(FF, "FORWARD_START", "2000-01-01T00:00:00Z"):
            rows = FF.signals(s, "XAUUSD", "eod", "G9", "G9_XAUUSD_eod")
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["status"], "refused")
        self.assertIn("data hole", rows[-1]["reason"])

    def test_accumulate_keeps_warning_while_a_hole_remains(self):
        import json, tempfile
        live, store = tempfile.mkdtemp(), tempfile.mkdtemp()
        b1 = bars("2030-01-07T10:00:00", [(1.0, 1.1, 0.9, 1.0)] * 3)
        json.dump({"candles": b1}, open(os.path.join(live, "ohlcv.XAUUSD.5m.json"), "w"))
        with mock.patch.object(FF, "merged_candles", lambda sym, l, s: [{"time": "2030-01-02T10:00:00Z"}] + b1):
            FF.accumulate("XAUUSD", live, store)
            _n, w = FF.accumulate("XAUUSD", live, store)                  # second cycle: the store is no longer empty
        self.assertIsNotNone(w)
        self.assertIn("hole", w)

    def test_live_file_uses_the_broker_spelling(self):
        import json, tempfile
        live, store = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.assertTrue(FF.live_path("US500", live).endswith("ohlcv.US500.cash.5m.json"))
        b = bars("2030-01-07T10:00:00", [(1.0, 1.1, 0.9, 1.0)] * 3)
        json.dump({"candles": b}, open(os.path.join(live, "ohlcv.US500.cash.5m.json"), "w"))
        n, _w = FF.accumulate("US500", live, store)
        self.assertEqual(n, 3)
        self.assertTrue(os.path.exists(os.path.join(store, "US500.5m.json")))      # the store keeps the CANONICAL name

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
        self.assertEqual(n, 2)
        self.assertIn("hole", w)              # the history -> store hole is still there: the warning persists until filled
        self.assertEqual(len(json.load(open(os.path.join(store, "XAUUSD.5m.json")))), 5)

    def test_places_no_order(self):
        src = open(os.path.join(ROOT, "scripts", "research", "fvg_forward.py")).read()
        for word in ("order_send", "mcp", "execute(", "strategy-runner"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
