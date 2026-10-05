"""scripts/research/news_flat.py on synthetic calendars, rows and bars (no market history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_news_flat
(docs/plans/2026-10-04-news-flat-preregistration-DRAFT.md [NF-P1])
"""
import contextlib
import copy
import datetime
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


NF = _load("news_flat", "scripts/research/news_flat.py")
UTC = datetime.timezone.utc
T = NF.utc


def ev(id_, typ="NFP", date="2012-06-01", time="08:30", status="released", impact="HIGH",
       avail="2012-05-04T12:30:00Z", withdrawn=None, superseded=None):
    """A synthetic calendar row (NOT a sourced release: tests only)."""
    row = {"id": id_, "type": typ, "status": status, "date_et": date, "time_et": time,
           "scheduled_event_time": NF.iso(NF.et_to_utc(date, time)) if time else None,
           "time_status": "KNOWN" if time else "UNKNOWN", "available_time": avail, "withdrawn_available_time": withdrawn,
           "superseded_by": superseded, "sources": [{"role": "date-time", "source": "S1", "quote": "synthetic"}]}
    if impact is not None:
        row["impact"] = impact
    return row


def doc(rows, cov_from="2000-01-01", cov_to="2030-12-31"):
    return {"schema": "nf-calendar/1", "snapshot": {"id": "synthetic"},
            "sources": {"S1": {"url": "https://example.invalid/x", "sha256": "0" * 64, "retrieved_utc": "2026-10-04T00:00:00Z"}},
            "coverage": {t: {"from": cov_from, "through": cov_to} for t in NF.TYPES}, "events": rows}


def cal(rows, **kw):
    return NF.load_calendar(doc=doc(rows, **kw))


def trade(entry, exit_open, R=0.5, how="time", side=1, comp="H7_XAUUSD_eod"):
    return {"component": comp, "entry_time": entry, "exit_time": exit_open, "server_day": entry[:10], "R": R,
            "mae_R": min(0.0, R), "exit": how, "side": side, "entry_px": 100.0, "stop_bp": 100.0, "stop_k": 1.4,
            "cost_R": 0.0, "adv_path_R": [-0.1, -0.3, -0.2, -0.9]}


NFP = ev("nfp-a")                                             # 2012-06-01 08:30 EDT = 12:30 UTC; window 12:20-12:40 UTC


# ------------------------------------------------------------------------------------------------ windows
class Boundaries(unittest.TestCase):
    def setUp(self):
        self.c = cal([NFP])

    def test_exact_start_and_end_are_inside(self):
        for t in ("2012-06-01T12:20:00Z", "2012-06-01T12:40:00Z", "2012-06-01T12:30:00Z"):
            self.assertTrue(NF.classify(trade(t, "2012-06-01T20:00:00Z"), self.c)["p1_drop"], t)

    def test_one_bar_outside_is_not_blocked(self):
        k = NF.classify(trade("2012-06-01T12:45:00Z", "2012-06-01T20:00:00Z"), self.c)
        self.assertFalse(k["p1_drop"])
        self.assertIsNone(k["flatten_at"])                    # the window is over: nothing to flatten

    def test_open_at_the_window_start_is_flattened_there(self):
        k = NF.classify(trade("2012-06-01T12:15:00Z", "2012-06-01T20:00:00Z"), self.c)
        self.assertFalse(k["p1_drop"])
        self.assertEqual(k["flatten_at"], T("2012-06-01T12:20:00Z"))
        k = NF.classify(trade("2012-06-01T12:10:00Z", "2012-06-01T12:20:00Z", how="stop"), self.c)
        self.assertEqual(k["flatten_at"], T("2012-06-01T12:20:00Z"))   # exit bar opens at the start: still open then

    def test_closed_before_the_window_start_is_untouched(self):
        for exit_open in ("2012-06-01T12:15:00Z", "2012-06-01T12:10:00Z"):   # stop inside the bar that ends at 12:20
            self.assertIsNone(NF.classify(trade("2012-06-01T12:10:00Z", exit_open, how="stop"), self.c)["flatten_at"])

    def test_membership_is_closed_like_the_live_gate(self):
        w = NF.windows_at(self.c, T("2012-06-01T00:00:00Z"), T("2012-06-01T00:00:00Z"), T("2012-06-02T00:00:00Z"))
        self.assertEqual([(NF.iso(a), NF.iso(b)) for a, b, _ in w], [("2012-06-01T12:20:00Z", "2012-06-01T12:40:00Z")])
        self.assertTrue(NF.in_windows(T("2012-06-01T12:40:00Z"), w))
        self.assertFalse(NF.in_windows(T("2012-06-01T12:40:01Z"), w))


class Overlaps(unittest.TestCase):
    def wins(self, times):
        rows = [ev(f"e{i}", typ="FOMC_STATEMENT" if i else "NFP", time=t) for i, t in enumerate(times)]
        c = cal(rows)
        return c, NF.windows_at(c, T("2012-06-01T00:00:00Z"), T("2012-06-01T00:00:00Z"), T("2012-06-02T00:00:00Z"))

    def test_overlapping_windows_are_the_union(self):
        c, w = self.wins(["08:30", "08:45"])                 # 12:20-12:40 and 12:35-12:55 UTC
        self.assertEqual([(NF.iso(a), NF.iso(b)) for a, b, _ in w], [("2012-06-01T12:20:00Z", "2012-06-01T12:55:00Z")])
        self.assertEqual(sorted(w[0][2]), ["e0", "e1"])

    def test_adjacent_windows_join_without_a_gap(self):
        c, w = self.wins(["08:30", "08:50"])                 # 12:20-12:40 and 12:40-13:00 UTC touch at 12:40
        self.assertEqual(len(w), 1)
        self.assertTrue(NF.classify(trade("2012-06-01T12:40:00Z", "2012-06-01T20:00:00Z"), c)["p1_drop"])

    def test_separate_windows_leave_the_gap_and_flatten_at_the_next_start(self):
        c, w = self.wins(["08:30", "08:55"])                 # 12:20-12:40 and 12:45-13:05 UTC
        self.assertEqual(len(w), 2)
        k = NF.classify(trade("2012-06-01T12:40:01Z", "2012-06-01T20:00:00Z"), c)
        self.assertFalse(k["p1_drop"])
        self.assertEqual(k["flatten_at"], T("2012-06-01T12:45:00Z"))
        self.assertEqual(k["events"], ["e1"])

    def test_statement_and_press_conference_are_two_windows(self):
        rows = [ev("st", typ="FOMC_STATEMENT", date="2021-03-17", time="14:00", avail="2020-07-02T14:00:00Z"),
                ev("pc", typ="FOMC_PRESS_CONFERENCE", date="2021-03-17", time="14:30", avail="2020-07-02T14:00:00Z")]
        c = cal(rows)
        w = NF.windows_at(c, T("2021-03-17T00:00:00Z"), T("2021-03-17T00:00:00Z"), T("2021-03-18T00:00:00Z"))
        self.assertEqual([(NF.iso(a), NF.iso(b)) for a, b, _ in w],
                         [("2021-03-17T17:50:00Z", "2021-03-17T18:10:00Z"), ("2021-03-17T18:20:00Z", "2021-03-17T18:40:00Z")])


class DaylightSaving(unittest.TestCase):
    def test_new_york_wall_time_follows_each_dates_rules(self):
        cases = {("2006-03-10", "08:30"): "2006-03-10T13:30:00Z",   # old US rules: DST from 2006-04-02
                 ("2006-04-07", "08:30"): "2006-04-07T12:30:00Z",
                 ("2007-03-09", "08:30"): "2007-03-09T13:30:00Z",   # 2007 rules: DST from 2007-03-11
                 ("2007-03-16", "08:30"): "2007-03-16T12:30:00Z",
                 ("2008-10-31", "08:30"): "2008-10-31T12:30:00Z",   # DST ends 2008-11-02
                 ("2008-11-07", "08:30"): "2008-11-07T13:30:00Z",
                 ("2021-03-17", "14:00"): "2021-03-17T18:00:00Z"}
        for (d, t), want in cases.items():
            self.assertEqual(NF.iso(NF.et_to_utc(d, t)), want, d)

    def test_a_row_with_the_wrong_offset_is_refused(self):
        row = ev("bad", date="2007-03-16")
        row["scheduled_event_time"] = "2007-03-16T13:30:00Z"           # EST offset on an EDT date
        with self.assertRaises(SystemExit) as cm:
            cal([row])
        self.assertIn("DST", str(cm.exception))

    def test_window_on_a_dst_week_uses_the_right_utc_hour(self):
        c = cal([ev("cpi", typ="CPI", date="2007-03-16", avail="2007-02-27T13:30:00Z")])
        self.assertTrue(NF.classify(trade("2007-03-16T12:25:00Z", "2007-03-16T20:00:00Z"), c)["p1_drop"])
        k = NF.classify(trade("2007-03-16T13:25:00Z", "2007-03-16T20:00:00Z"), c)   # 08:25 only under a wrong EST reading
        self.assertFalse(k["p1_drop"])
        self.assertIsNone(k["flatten_at"])

    def test_naive_timestamps_are_refused(self):
        with self.assertRaises(SystemExit):
            NF.utc("2012-06-01T12:30:00")


# ------------------------------------------------------------------------------------------------ impact
class ImpactNeverLow(unittest.TestCase):
    def test_missing_impact_loads_as_unknown_and_restricts(self):
        c = cal([ev("x", impact=None)])
        self.assertEqual(c.events[0].impact, "UNKNOWN")
        self.assertTrue(NF.classify(trade("2012-06-01T12:30:00Z", "2012-06-01T20:00:00Z"), c)["p1_drop"])

    def test_low_and_medium_do_not_restrict(self):
        for imp in ("LOW", "medium"):
            c = cal([ev("x", impact=imp)])
            k = NF.classify(trade("2012-06-01T12:30:00Z", "2012-06-01T20:00:00Z"), c)
            self.assertFalse(k["p1_drop"], imp)
            self.assertEqual(k["unknown"], [], imp)

    def test_an_invented_level_is_refused(self):
        with self.assertRaises(SystemExit):
            cal([ev("x", impact="SEVERE")])

    def test_unknown_time_is_unknown_not_clear(self):
        c = cal([ev("st", typ="FOMC_STATEMENT", date="2004-06-30", time=None, avail="2003-06-11T03:59:59Z")])
        k = NF.classify(trade("2004-06-30T09:00:00Z", "2004-06-30T20:55:00Z"), c)
        self.assertEqual(k["unknown"], ["st"])
        out, book = NF.apply_policies([trade("2004-06-30T09:00:00Z", "2004-06-30T20:55:00Z")], c, None)
        self.assertEqual([len(out[p]) for p in NF.POLICIES], [0, 0, 0])   # gone from all three policies alike
        self.assertEqual(len(book["unknown"]), 1)


# ------------------------------------------------------------------------------------------------ point in time
class PointInTime(unittest.TestCase):
    def test_a_row_published_after_the_decision_cannot_restrict_it(self):
        late = ev("late", date="2013-10-22", avail="2013-10-22T12:25:00Z")      # synthetic: known only at 12:25 UTC
        c = cal([late])
        self.assertFalse(NF.classify(trade("2013-10-22T12:22:00Z", "2013-10-22T20:00:00Z"), c)["p1_drop"])
        self.assertTrue(NF.classify(trade("2013-10-22T12:30:00Z", "2013-10-22T20:00:00Z"), c)["p1_drop"])
        self.assertIsNone(NF.classify(trade("2013-10-22T12:00:00Z", "2013-10-22T20:00:00Z"), c)["flatten_at"])

    def test_postponed_row_restricts_until_its_withdrawal_is_public(self):
        rows = [ev("old", date="2013-10-04", status="postponed", avail="2013-09-06T12:30:00Z",
                   withdrawn="2013-10-02T04:57:28Z", superseded="new"),
                ev("new", date="2013-10-22", avail="2013-10-18T03:20:51Z")]
        self.assertIsNone(NF.classify(trade("2013-10-04T12:00:00Z", "2013-10-04T20:00:00Z"), cal(rows))["flatten_at"])
        rows[0]["withdrawn_available_time"] = None                               # withdrawal never published: still expected
        self.assertEqual(NF.classify(trade("2013-10-04T12:00:00Z", "2013-10-04T20:00:00Z"), cal(rows))["flatten_at"],
                         T("2013-10-04T12:20:00Z"))
        rows[0]["withdrawn_available_time"] = "2013-10-04T12:25:00Z"             # withdrawn after the flatten instant
        self.assertEqual(NF.classify(trade("2013-10-04T12:00:00Z", "2013-10-04T20:00:00Z"), cal(rows))["flatten_at"],
                         T("2013-10-04T12:20:00Z"))

    def test_unscheduled_actions_never_restrict(self):
        c = cal([ev("u", typ="FOMC_STATEMENT", date="2008-10-08", time="07:00", status="unscheduled",
                    avail="2008-10-08T11:00:00Z")])
        k = NF.classify(trade("2008-10-08T10:55:00Z", "2008-10-08T20:00:00Z"), c)
        self.assertEqual((k["p1_drop"], k["flatten_at"], k["unknown"]), (False, None, []))

    def test_truncation_probe_future_rows_change_no_earlier_decision(self):
        rows, trades = [], []
        d0 = datetime.date(2015, 1, 5)
        for k in range(40):
            d = d0 + datetime.timedelta(days=7 * k)
            rows.append(ev(f"r{k}", date=d.isoformat(), time="08:30", avail=f"{(d - datetime.timedelta(days=30)).isoformat()}T00:00:00Z"))
            for hh in ("12:05", "13:25", "13:35", "14:00"):
                entry = f"{d.isoformat()}T{hh}:00Z"
                trades.append(trade(entry, f"{d.isoformat()}T20:00:00Z"))
        cut = datetime.date(2015, 6, 1)
        full = cal(rows)
        past_only = cal([r for r in rows if r["date_et"] < cut.isoformat()])
        early = [t for t in trades if t["entry_time"][:10] < (cut - datetime.timedelta(days=2)).isoformat()]
        self.assertGreater(len(early), 50)
        self.assertEqual([NF.classify(t, full) for t in early], [NF.classify(t, past_only) for t in early])
        known_by = T("2015-03-01T00:00:00Z")                                    # rows not yet published are invisible
        visible = cal([r for r in rows if T(r["available_time"]) <= known_by])
        before = [t for t in trades if T(t["exit_time"]) < known_by]
        self.assertEqual([NF.classify(t, full) for t in before], [NF.classify(t, visible) for t in before])

    def test_coverage_gap_is_unknown_not_no_news(self):
        c = cal([NFP], cov_from="2013-01-01")
        self.assertEqual(NF.classify(trade("2012-06-01T09:00:00Z", "2012-06-01T20:00:00Z"), c)["unknown"], ["coverage"])

    def test_availability_unknown_is_unknown(self):
        c = cal([ev("pc", typ="FOMC_PRESS_CONFERENCE", date="2012-01-25", time="14:15", avail=None)])
        self.assertEqual(NF.classify(trade("2012-01-25T19:00:00Z", "2012-01-25T21:00:00Z"), c)["unknown"], ["pc"])
        self.assertEqual(NF.classify(trade("2012-01-25T14:00:00Z", "2012-01-25T15:00:00Z"), c)["unknown"], [])


class LoaderRefusals(unittest.TestCase):
    def test_unsourced_duplicate_and_malformed_rows_are_refused(self):
        bad = []
        r = ev("a"); r["sources"] = []; bad.append([r])
        r = ev("a"); r["sources"] = [{"role": "x", "source": "S9", "quote": "q"}]; bad.append([r])
        bad.append([ev("a"), ev("a")])
        r = ev("a"); r["type"] = "PPI"; bad.append([r])
        r = ev("a", status="postponed"); bad.append([r])                      # postponed without a replacement
        r = ev("a", avail="2012-06-01T12:31:00Z"); bad.append([r])            # "released" yet known only after it
        r = ev("a"); r["time_status"] = "UNKNOWN"; bad.append([r])
        for rows in bad:
            with self.assertRaises(SystemExit):
                cal(rows)
        d = doc([ev("a")]); del d["coverage"]["CPI"]
        with self.assertRaises(SystemExit):
            NF.load_calendar(doc=d)
        d = doc([ev("a")]); d["snapshot"] = {}
        with self.assertRaises(SystemExit):
            NF.load_calendar(doc=d)


# ------------------------------------------------------------------------------------------------ policies
class Policies(unittest.TestCase):
    def test_flatten_row_arithmetic(self):
        r = trade("2012-06-01T12:10:00Z", "2012-06-01T20:00:00Z")
        f = NF.flatten_row(r, "2012-06-01T12:15:00Z", 100.5, 0.02, 3)
        self.assertAlmostEqual(f["R"], 0.48)
        self.assertEqual(f["adv_path_R"], [-0.1, -0.3, -0.2])
        self.assertAlmostEqual(f["mae_R"], -0.32)
        self.assertEqual((f["exit"], f["exit_time"], f["server_day"]), ("news_flat", "2012-06-01T12:15:00Z", "2012-06-01"))
        s = dict(r, side=-1)
        self.assertAlmostEqual(NF.flatten_row(s, "2012-06-01T12:15:00Z", 99.0, 0.02, 1)["R"], 0.98)
        self.assertEqual(r["exit"], "time")                                     # pure: the input row is not changed

    def test_flatten_paper_row_arithmetic(self):
        p = {"entry": 100.0, "side": -1, "stop_distance": 2.0, "R": -1.0, "exit_reason": "stop"}
        f = NF.flatten_paper_row(p, "2027-01-08T13:15:00Z", 99.0, 0.1)
        self.assertAlmostEqual(f["R"], 0.45)
        self.assertAlmostEqual(f["net_bp"], 90.0)
        self.assertEqual(f["exit_reason"], "news_flat")

    def test_apply_policies_keeps_identical_rows_and_counts(self):
        c = cal([NFP, ev("st", typ="FOMC_STATEMENT", date="2004-06-30", time=None, avail="2003-06-11T03:59:59Z")])
        rows = [trade("2012-06-01T12:30:00Z", "2012-06-01T20:00:00Z", R=0.9),       # P1 drop
                trade("2012-06-01T12:00:00Z", "2012-06-01T20:00:00Z", R=-1.39, how="stop"),   # flattened by P2
                trade("2012-06-01T14:00:00Z", "2012-06-01T20:00:00Z", R=0.2),       # untouched
                trade("2004-06-30T09:00:00Z", "2004-06-30T20:00:00Z", R=0.1)]       # UNKNOWN
        cut = lambda r, s: dict(r, R=0.05, exit="news_flat", exit_time=NF.iso(s))
        out, book = NF.apply_policies(rows, c, cut)
        self.assertEqual([len(out[p]) for p in NF.POLICIES], [3, 2, 2])
        self.assertEqual([r["R"] for r in out["P2"]], [0.05, 0.2])
        self.assertEqual(book["p2_flattened"][0]["R_P1"], -1.39)
        self.assertEqual(len(book["p1_dropped"]), 1)
        self.assertEqual(len(book["unknown"]), 1)

    def test_a_missing_cut_bar_makes_the_trade_unknown_in_all_three_policies(self):
        c = cal([NFP])
        rows = [trade("2012-06-01T12:00:00Z", "2012-06-01T20:00:00Z", R=-0.4), trade("2012-06-01T14:00:00Z", "2012-06-01T20:00:00Z", R=0.2)]
        out, book = NF.apply_policies(rows, c, lambda r, s: None)
        self.assertEqual([len(out[p]) for p in NF.POLICIES], [1, 1, 1])
        self.assertEqual([u["reasons"] for u in book["unknown"]], [["no_bar_at_flatten_instant"]])
        self.assertEqual(book["p2_flattened"], [])

    def test_summary_tail_and_gap_count(self):
        rows = [trade("2012-06-01T12:00:00Z", "x", R=-1.39, how="stop"), trade("2012-06-04T12:00:00Z", "x", R=-1.02, how="stop"),
                trade("2013-01-02T12:00:00Z", "x", R=1.5), dict(trade("2013-01-03T12:00:00Z", "x", R=0.3), exit="news_flat")]
        s = NF.summary(rows)
        self.assertAlmostEqual(s["worst_loss_pct_of_balance"], 1.39)
        self.assertEqual((s["gap_through_stops"], s["flattened"], s["n"]), (1, 1, 4))
        self.assertEqual(set(s["by_year"]), {"2012", "2013"})

    def test_summary_reads_paper_rows_exit_reason(self):
        rows = [{"entry_time": "2027-01-08T12:00:00Z", "R": -1.2, "exit": 99.0, "exit_reason": "stop"},
                {"entry_time": "2027-01-08T13:00:00Z", "R": 0.4, "exit": 101.0, "exit_reason": "news_flat"}]
        s = NF.summary(rows)
        self.assertEqual((s["gap_through_stops"], s["flattened"], s["stop_share"]), (1, 1, 0.5))

    def test_dry_counts_labels_by_reason(self):
        c = cal([NFP, ev("st", typ="FOMC_STATEMENT", date="2004-06-30", time=None, avail="2003-06-11T03:59:59Z")])
        rows = {"H7_XAUUSD_eod": [trade("2012-06-01T12:30:00Z", "2012-06-01T20:55:00Z"),
                                  trade("2012-06-01T11:00:00Z", "2012-06-01T20:55:00Z"),
                                  trade("2004-06-30T10:00:00Z", "2004-06-30T20:55:00Z")]}
        out = NF.dry_counts(rows, c)["H7_XAUUSD_eod"]
        self.assertEqual(out["2012"], {"planned": 2, "p1_entry_blocked": 1, "p1_entry_blocked:NFP": 1,
                                       "planned_open_across_window": 1, "planned_open_across_window:NFP": 1,
                                       "release_days_with_open_trade": 1})
        self.assertEqual(out["2004"], {"planned": 1, "unknown": 1, "unknown:FOMC_STATEMENT": 1,
                                       "release_days_with_open_trade": 0})

    def test_daily_breach_days(self):
        rows = [dict(trade("2012-06-01T12:00:00Z", "x", R=-2.5), mae_R=-2.6) for _ in range(2)]
        rows.append(dict(trade("2012-06-04T12:00:00Z", "x", R=-1.0), mae_R=-4.9))
        self.assertEqual(NF.daily_breach_days(rows), {"realised": 1, "floating_bound": 1})


class CutBar(unittest.TestCase):
    class S:
        pass

    def series(self, closes, start="2012-06-01T11:50:00Z", gap=None):
        s = self.S()
        t0 = T(start)
        s.dt = [t0 + datetime.timedelta(minutes=5 * k) for k in range(len(closes)) if k != gap]
        s.T = [NF.iso(t) for t in s.dt]
        s.C = [c for k, c in enumerate(closes) if k != gap]
        s.sday = [datetime.date(2012, 6, 1) if t < T("2012-06-01T21:00:00Z") else datetime.date(2012, 6, 4) for t in s.dt]
        return s

    class Costs:
        """A median leg of 2 bp and a p90 leg of 6 bp (relative); the book_sim round trip is the median one."""
        def leg_at(self, t, stat="median"):
            return 0.0002 if stat == "median" else 0.0006

        def round_trip_at(self, a, b):
            return 0.0002

    def test_cut_is_the_last_bar_ending_by_the_flatten_instant(self):
        s = self.series([100 + 0.1 * k for k in range(20)])
        r = trade("2012-06-01T12:00:00Z", "2012-06-01T13:00:00Z")
        f = NF.series_cutter(s, self.Costs())(r, T("2012-06-01T12:20:00Z"))
        self.assertEqual(f["exit_time"], "2012-06-01T12:15:00Z")               # 12:15-12:20 bar, closes at 12:20
        gross = s.C[5] - 100.0
        self.assertAlmostEqual(f["R"], (gross - 0.0004 * 100.0) / 1.0)          # primary: median entry leg + p90 flatten leg
        self.assertAlmostEqual(f["R_med"], (gross - 0.0002 * 100.0) / 1.0)      # book_sim pricing (sensitivity)
        self.assertAlmostEqual(f["R_neutral"], gross / 1.0 - r["cost_R"])       # the held trade's own cost (sensitivity)
        self.assertLess(f["R"], f["R_med"])                                     # the conservative leg never favours P2
        self.assertEqual(len(f["adv_path_R"]), 4)                               # 12:00, 12:05, 12:10, 12:15

    def test_a_missing_bar_at_the_flatten_instant_gives_no_price(self):
        s = self.series([100 + 0.1 * k for k in range(20)], gap=5)             # the 12:15 bar (it ends at 12:20) is missing
        cut = NF.series_cutter(s, self.Costs())
        self.assertIsNone(cut(trade("2012-06-01T12:00:00Z", "2012-06-01T13:00:00Z"), T("2012-06-01T12:20:00Z")))
        self.assertEqual(NF.cut_bar(s, 2, T("2012-06-01T12:20:00Z")), 4)        # the stale bar the read must NOT use
        self.assertFalse(NF.exact_cut(s, 4, T("2012-06-01T12:20:00Z")))

    def test_bars_after_the_cut_do_not_matter(self):
        a = self.series([100 + 0.1 * k for k in range(20)])
        b = self.series([100 + 0.1 * k if k <= 5 else 50.0 for k in range(20)])
        r = trade("2012-06-01T12:00:00Z", "2012-06-01T13:00:00Z")
        fa = NF.series_cutter(a, self.Costs())(r, T("2012-06-01T12:20:00Z"))
        fb = NF.series_cutter(b, self.Costs())(r, T("2012-06-01T12:20:00Z"))
        self.assertEqual(fa, fb)


# ------------------------------------------------------------------------------------------------ forward rule
class ForwardRule(unittest.TestCase):
    def book(self, pairs):
        return {"p2_flattened": [{"R_P1": a, "R_P2": b, "R_P2_med": b, "R_P2_neutral": b,
                                  "flatten_at": f"2027-{1 + k // 28:02d}-{1 + k % 28:02d}T12:20:00Z"}
                                 for k, (a, b) in enumerate(pairs)]}

    def test_paired_delta_cr1(self):
        d = NF.paired_delta({"p2_flattened": [{"R_P1": 1.0, "R_P2": 0.0, "flatten_at": "2027-01-08T12:20:00Z"},
                                              {"R_P1": 0.0, "R_P2": 0.0, "flatten_at": "2027-01-08T17:50:00Z"},
                                              {"R_P1": 0.0, "R_P2": 1.0, "flatten_at": "2027-02-05T12:20:00Z"}]})
        self.assertEqual((d["n"], d["clusters"]), (3, 2))
        self.assertAlmostEqual(d["mean_dR"], 0.0)
        self.assertAlmostEqual(d["se_cr1"], (2 * (1.0 ** 2 + 1.0 ** 2) / 9) ** 0.5)
        self.assertEqual(NF.paired_delta({"p2_flattened": []}), {"n": 0})

    def test_sensitivities_are_reported_and_do_not_move_the_decision(self):
        rows = [{"R_P1": 0.0, "R_P2": -0.10, "R_P2_med": -0.04, "R_P2_neutral": -0.02, "flatten_at": f"2027-01-{1 + k:02d}T12:20:00Z"}
                for k in range(30)]
        d = NF.paired_delta({"p2_flattened": rows})
        self.assertAlmostEqual(d["mean_dR"], -0.10)
        self.assertAlmostEqual(d["sensitivity"]["mean_dR_median_cost"], -0.04)
        self.assertAlmostEqual(d["sensitivity"]["mean_dR_cost_neutral"], -0.02)
        self.assertEqual(NF.forward_verdict(d), "CHEAP")                           # -0.10 with no spread: inside the 0.20 R margin

    def test_verdicts(self):
        cheap = self.book([(0.0, 0.01 * (k % 3)) for k in range(60)])
        self.assertEqual(NF.forward_verdict(NF.paired_delta(cheap)), "CHEAP")
        costly = self.book([(0.5, -0.5 + 0.02 * (k % 5)) for k in range(60)])
        self.assertEqual(NF.forward_verdict(NF.paired_delta(costly)), "COSTLY")
        noisy = self.book([(0.0, (-1) ** k * 1.5 - 0.1) for k in range(60)])
        self.assertEqual(NF.forward_verdict(NF.paired_delta(noisy)), "INCONCLUSIVE")
        few = {"p2_flattened": [{"R_P1": 0.0, "R_P2": 0.0, "flatten_at": f"2027-01-{1 + k % 5:02d}T12:20:00Z"} for k in range(60)]}
        self.assertEqual(NF.forward_verdict(NF.paired_delta(few)), "INCONCLUSIVE")      # 5 release days only

    def test_forward_due(self):
        seal = datetime.date(2026, 10, 12)
        self.assertTrue(NF.forward_due(50, seal, seal))
        self.assertFalse(NF.forward_due(49, seal, datetime.date(2029, 10, 11)))
        self.assertTrue(NF.forward_due(0, seal, datetime.date(2029, 10, 12)))


# ------------------------------------------------------------------------------------------------ VC ordering and as-of
class TempRepo(unittest.TestCase):
    """A temporary git repository with controllable committer dates."""

    def git(self, *a, date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid")
        if date:
            env.update(GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date)
        return subprocess.run(["git", "-C", self.root, *a], check=True, capture_output=True, text=True, env=env)

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, msg="x", date=None):
        self.git("add", "-f", "-A")
        self.git("commit", "-q", "-m", msg, "--allow-empty", date=date)

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.git("init", "-q")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.excludesFile", os.devnull)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class VcOrdering(TempRepo):
    def test_the_exposed_read_waits_for_vcs_holdout_read(self):
        self.assertTrue(NF.AFTER_VC)
        self.write("docs/audits/2026-10-10-edge-vc-crypto.json", json.dumps({"meta": {"tag": NF.VC_TAG, "read": "crypto"}}))
        self.commit("another VC read")
        with self.assertRaises(SystemExit) as cm:
            NF.require_vc_first(self.root)
        self.assertIn("VC's xau-holdout read", str(cm.exception))
        name = "docs/audits/2026-10-11-edge-vc-xau-holdout.json"
        self.write(name, json.dumps({"meta": {"tag": "[OTHER-P1]", "read": "xau-holdout"}}))
        self.commit("a file of that name with another tag")
        with self.assertRaises(SystemExit) as cm:
            NF.require_vc_first(self.root)
        self.assertIn("carries tag", str(cm.exception))
        self.write(name, json.dumps({"meta": {"tag": NF.VC_TAG, "read": "xau-holdout"}}))
        with self.assertRaises(SystemExit) as cm:
            NF.require_vc_first(self.root)                                     # right content, not committed
        self.assertIn("uncommitted", str(cm.exception))
        self.commit("VC's read")
        self.assertEqual(NF.require_vc_first(self.root), name)

    def test_a_second_vc_output_is_refused(self):
        for day in ("2026-10-11", "2026-10-12"):
            self.write(f"docs/audits/{day}-edge-vc-xau-holdout.json", json.dumps({"meta": {"tag": NF.VC_TAG, "read": "xau-holdout"}}))
        self.commit("two outputs")
        with self.assertRaises(SystemExit) as cm:
            NF.require_vc_first(self.root)
        self.assertIn("each read runs once", str(cm.exception))


class AsOfCalendar(TempRepo):
    """The forward read's calendar is the one COMMITTED at each decision (CLAUDE.md §29)."""

    R1 = dict(date="2027-01-08", avail="2026-12-01T00:00:00Z")
    R2 = dict(date="2027-01-15", avail="2026-12-01T00:00:00Z")

    def v1(self, **kw):
        return cal([ev("r1", **self.R1)], cov_from="2026-01-01", cov_to="2027-01-09", **kw)

    def v2(self):
        return cal([ev("r1", **self.R1), ev("r2", **self.R2)], cov_from="2026-01-01", cov_to="2027-01-31")

    def asof(self):
        return NF.AsOf([(T("2026-12-01T00:00:00Z"), self.v1()), (T("2027-01-16T00:00:00Z"), self.v2())])

    def test_a_day_the_committed_calendar_did_not_cover_is_unknown_not_no_news(self):
        a = self.asof()
        late = trade("2027-01-15T10:00:00Z", "2027-01-15T20:55:00Z")
        self.assertEqual(NF.classify(late, a)["unknown"], ["coverage"])            # v1 stopped at 2027-01-09
        self.assertEqual(NF.classify(late, self.v2())["flatten_at"], T("2027-01-15T13:20:00Z"))   # the final file alone would flatten
        ok = trade("2027-01-08T10:00:00Z", "2027-01-08T20:55:00Z")
        self.assertEqual(NF.classify(ok, a)["flatten_at"], T("2027-01-08T13:20:00Z"))

    def test_a_row_committed_in_time_is_used(self):
        a = NF.AsOf([(T("2026-12-01T00:00:00Z"), self.v1()), (T("2027-01-14T00:00:00Z"), self.v2())])
        self.assertEqual(NF.classify(trade("2027-01-15T10:00:00Z", "2027-01-15T20:55:00Z"), a)["flatten_at"], T("2027-01-15T13:20:00Z"))

    def test_a_row_that_reaches_the_calendar_while_the_position_is_open_flattens_it(self):
        v1 = cal([ev("r1", **self.R1)], cov_from="2026-01-01", cov_to="2027-01-31")           # covers 01-15, row r2 not yet there
        a = NF.AsOf([(T("2026-12-01T00:00:00Z"), v1), (T("2027-01-15T11:00:00Z"), self.v2())])   # r2 committed at 11:00 UTC
        k = NF.classify(trade("2027-01-15T10:00:00Z", "2027-01-15T20:55:00Z"), a)
        self.assertEqual((k["p1_drop"], k["flatten_at"]), (False, T("2027-01-15T13:20:00Z")))   # P1 saw no row; P2 sees it at 13:20
        late = NF.AsOf([(T("2026-12-01T00:00:00Z"), v1), (T("2027-01-15T13:25:00Z"), self.v2())])   # committed after the window start
        self.assertIsNone(NF.classify(trade("2027-01-15T10:00:00Z", "2027-01-15T20:55:00Z"), late)["flatten_at"])

    def test_a_backdated_withdrawal_committed_after_the_decision_does_not_count(self):
        edited = cal([ev("r1", date=self.R1["date"], avail=self.R1["avail"], status="postponed", withdrawn="2027-01-01T00:00:00Z",
                         superseded="r2"), ev("r2", **self.R2)], cov_from="2026-01-01", cov_to="2027-01-31")
        a = NF.AsOf([(T("2026-12-01T00:00:00Z"), self.v1()), (T("2027-01-09T00:00:00Z"), edited)])
        k = NF.classify(trade("2027-01-08T10:00:00Z", "2027-01-08T20:55:00Z"), a)
        self.assertEqual(k["flatten_at"], T("2027-01-08T13:20:00Z"))               # the edit is dated 01-09: too late to count
        self.assertEqual(NF.classify(trade("2027-01-08T10:00:00Z", "2027-01-08T20:55:00Z"), edited)["flatten_at"], None)

    def test_before_the_first_commit_there_is_no_calendar(self):
        a = self.asof()
        self.assertIs(a.at(T("2026-11-30T00:00:00Z")), NF.EMPTY)
        self.assertEqual(NF.classify(trade("2026-11-30T10:00:00Z", "2026-11-30T20:55:00Z"), a)["unknown"], ["coverage"])
        self.assertIs(a.latest.at(T("2030-01-01T00:00:00Z")), a.latest)

    def test_versions_come_from_git_with_their_commit_times(self):
        rel = "data/calendar/c.json"
        d1 = doc([ev("r1", **self.R1)], cov_to="2027-01-09")
        self.write(rel, json.dumps(d1))
        self.commit("v1", date="2026-12-01T00:00:00Z")
        self.write("other.txt", "x")
        self.commit("unrelated", date="2026-12-15T00:00:00Z")                      # does not touch the calendar
        d2 = doc([ev("r1", **self.R1), ev("r2", **self.R2)], cov_to="2027-01-31")
        self.write(rel, json.dumps(d2))
        self.commit("v2", date="2027-01-16T00:00:00Z")
        vs = NF.calendar_versions(self.root, rel)
        self.assertEqual(sorted(NF.iso(t) for t, _ in vs), ["2026-12-01T00:00:00Z", "2027-01-16T00:00:00Z"])   # the unrelated commit is not a version
        a = NF.AsOf(vs)
        self.assertEqual(len(a.versions), 2)
        self.assertEqual(sorted(a.at(T("2026-12-20T00:00:00Z")).by_id), ["r1"])
        self.assertEqual(sorted(a.at(T("2027-01-20T00:00:00Z")).by_id), ["r1", "r2"])
        self.assertIs(a.at(T("2026-01-01T00:00:00Z")), NF.EMPTY)
        self.write(rel, "{ not json")
        self.commit("broken", date="2027-02-01T00:00:00Z")
        with self.assertRaises(Exception):
            NF.calendar_versions(self.root, rel)                                    # a broken version is a refusal, not skipped

    def test_commits_of_one_second_resolve_to_the_newest_and_backwards_time_is_refused(self):
        rel = "data/calendar/c.json"
        self.write(rel, json.dumps(doc([ev("r1", **self.R1)], cov_to="2027-01-09")))
        self.commit("first", date="2026-12-01T00:00:00Z")
        self.write(rel, json.dumps(doc([ev("r1", **self.R1), ev("r2", **self.R2)], cov_to="2027-01-31")))
        self.commit("second, same second", date="2026-12-01T00:00:00Z")
        a = NF.AsOf(NF.calendar_versions(self.root, rel))
        self.assertEqual(sorted(a.at(T("2026-12-01T00:00:00Z")).by_id), ["r1", "r2"])      # the newer of the two
        self.write(rel, json.dumps(doc([ev("r1", **self.R1)], cov_to="2027-01-31")))
        self.commit("third, earlier date", date="2026-11-01T00:00:00Z")                    # a rewritten or skewed clock
        with self.assertRaises(SystemExit) as cm:
            NF.calendar_versions(self.root, rel)
        self.assertIn("go backwards", str(cm.exception))


# ------------------------------------------------------------------------------------------------ calendar pinning
class CalendarPin(unittest.TestCase):
    def test_history_digest_ignores_appends_and_sees_edits(self):
        d = doc([NFP, ev("later", date="2026-11-06", avail="2026-10-02T12:30:00Z")])
        h = NF.calendar_history_digest(d, "2026-10-05")
        d2 = copy.deepcopy(d)
        d2["events"].append(ev("later2", date="2026-12-04", avail="2026-10-01T10:55:44Z"))
        d2["coverage"]["NFP"]["through"] = "2026-12-31"
        self.assertEqual(NF.calendar_history_digest(d2, "2026-10-05"), h)
        d3 = copy.deepcopy(d)
        d3["events"][0]["time_et"] = "08:35"
        self.assertNotEqual(NF.calendar_history_digest(d3, "2026-10-05"), h)
        d4 = copy.deepcopy(d)
        d4["sources"]["S1"]["sha256"] = "1" * 64
        self.assertNotEqual(NF.calendar_history_digest(d4, "2026-10-05"), h)

    def test_require_calendar_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "c.json")
            d = doc([NFP])
            with open(p, "w") as fh:
                json.dump(d, fh)
            h = NF.calendar_history_digest(d, "2026-10-05")
            line = f"calendar-history-sha256 {h} before 2026-10-05 {NF.CALENDAR}"
            self.assertEqual(NF.require_calendar_history(f"x\n{line}\n", p), "2026-10-05")
            tampered = line.replace(h, ("1" if h[0] == "0" else "0") + h[1:])
            other_path = line.replace(NF.CALENDAR, "data/calendar/other.json")
            for text in ("x\n", f"{line}\n{line}\n", tampered + "\n", other_path + "\n"):
                with self.assertRaises(SystemExit):
                    NF.require_calendar_history(text, p)


# ------------------------------------------------------------------------------------------------ the repo calendar
class RepoCalendar(unittest.TestCase):
    def setUp(self):
        self.c = NF.load_calendar()

    def test_loads_covers_the_xau_history_and_is_point_in_time(self):
        start = datetime.date(2004, 6, 11)                      # first XAUUSD 5m bar (data/history/ftmo index)
        for typ, (f, th) in self.c.coverage.items():
            self.assertLessEqual(f, start, typ)
            self.assertGreaterEqual(th, datetime.date(2026, 10, 2), typ)
        for e in self.c.events:
            if e.status == "released" and e.t is not None and e.avail is not None:
                self.assertLess(e.avail, e.t - datetime.timedelta(minutes=NF.PRE_MIN), e.id)

    def test_the_two_worst_v4_gap_days_have_their_release(self):
        """vol-schedule.md:40-41: 2012-06-01 payrolls, 2021-03-17 FOMC statement at 18:00 UTC."""
        by = {e.id: e for e in self.c.events}
        self.assertEqual(NF.iso(by["nfp-2012-06-01"].t), "2012-06-01T12:30:00Z")
        self.assertEqual(NF.iso(by["fomc-stmt-2021-03-17"].t), "2021-03-17T18:00:00Z")
        self.assertTrue(NF.classify(trade("2012-06-01T12:25:00Z", "2012-06-01T20:00:00Z"), self.c)["p1_drop"])
        self.assertEqual(NF.classify(trade("2012-06-01T12:05:00Z", "2012-06-01T20:00:00Z"), self.c)["flatten_at"],
                         T("2012-06-01T12:20:00Z"))                     # the audit's entry time: flattened 10 min before
        self.assertEqual(NF.classify(trade("2021-03-17T17:15:00Z", "2021-03-17T20:00:00Z"), self.c)["flatten_at"],
                         T("2021-03-17T17:50:00Z"))

    def test_deviations_are_carried(self):
        by = {e.id: e for e in self.c.events}
        old, new = by["nfp-2013-10-04-postponed"], by["nfp-2013-10-22"]
        self.assertEqual(old.superseded_by, new.id)
        self.assertLess(old.withdrawn, old.t)
        self.assertLess(new.avail, new.t)
        self.assertEqual(by["cpi-2025-11-13-cancelled"].status, "cancelled")


# ------------------------------------------------------------------------------------------------ registration guard
class Guard(unittest.TestCase):
    def test_prereg_constant_is_the_sealed_name_and_the_draft_does_not_pass(self):
        self.assertFalse(NF.PREREG.endswith("-DRAFT.md"))
        draft = os.path.join(ROOT, NF.PREREG.replace(".md", "-DRAFT.md"))
        self.assertTrue(os.path.exists(draft))
        with open(draft, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(NF.TAG, text)
        with self.assertRaises(SystemExit):
            NF.G.check_sealed_text(text, NF.PREREG, NF.TAG)

    # The refusal before a sealed text exists is tested in a temporary git repository (SealRehearsal): a test on THIS
    # repository would turn red the moment the text is sealed, and this file is pinned by the seal's manifest.

    def test_a_read_writes_only_its_one_output_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                NF.main(["run", "--read", "exposed", "--out", os.path.join(tmp, "x.json")])
            self.assertIn("edge-nf-exposed.json", str(cm.exception))

    def test_a_dry_run_refuses_a_reads_output_name(self):
        out = os.path.join(ROOT, "docs", "audits", "2099-12-31-edge-nf-exposed.json")
        with self.assertRaises(SystemExit) as cm:
            NF.main(["dry-run", "--out", out])
        self.assertIn("output name", str(cm.exception))
        self.assertFalse(os.path.exists(out))

    def test_bytecode_outside_the_repository_is_refused(self):
        saved = sys.pycache_prefix
        try:
            sys.pycache_prefix = "/tmp/elsewhere"
            with self.assertRaises(SystemExit) as cm:
                NF.require_no_pycache_prefix()
            self.assertIn("pycache_prefix", str(cm.exception))
            sys.pycache_prefix = None
            NF.require_no_pycache_prefix()
        finally:
            sys.pycache_prefix = saved

    def test_the_exposed_loader_is_capped_whatever_the_caller_asks(self):
        seen = []
        ns = types.SimpleNamespace(EC=types.SimpleNamespace(load=lambda sym, end=None: seen.append((sym, end)) or "series"))
        orig = ns.EC.load
        with NF.capped(ns):
            self.assertEqual(ns.EC.load("XAUUSD", end="9999-12-31T00:00:00Z"), "series")
            ns.EC.load("XAUUSD")
        self.assertEqual(seen, [("XAUUSD", NF.EXPOSED_END), ("XAUUSD", NF.EXPOSED_END)])
        self.assertIs(ns.EC.load, orig)                                             # restored
        with self.assertRaises(RuntimeError):
            with NF.capped(ns):
                raise RuntimeError("boom")
        self.assertIs(ns.EC.load, orig)                                             # restored after an error too

    def test_the_dataset_digest_sees_only_the_bars_before_the_end(self):
        import history_store as HS
        bars = [{"time": f"2026-10-0{d}T00:00:00Z", "open": 1.0 + d, "high": 2.0, "low": 0.5, "close": 1.5} for d in (1, 2)]
        later = [{"time": "2026-10-03T00:00:00Z", "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0},
                 {"time": "2026-10-05T00:00:00Z", "open": 9.0, "high": 9.0, "low": 9.0, "close": 9.0}]
        orig_read, orig_bs = HS.read_doc, NF._bs
        NF._bs = lambda: types.SimpleNamespace(EC=types.SimpleNamespace(HIST_ROOT="unused"))
        try:
            HS.read_doc = lambda sym, tf, root=None: ({"candles": bars}, None)
            base = NF.exposed_dataset_digest()
            HS.read_doc = lambda sym, tf, root=None: ({"candles": bars + later}, None)
            self.assertEqual(NF.exposed_dataset_digest(), base)                      # bars at or after the end change nothing
            edited = [dict(bars[0], close=1.6), bars[1]]
            HS.read_doc = lambda sym, tf, root=None: ({"candles": edited + later}, None)
            self.assertNotEqual(NF.exposed_dataset_digest(), base)                   # an edit of an earlier bar does
            HS.read_doc = lambda sym, tf, root=None: ({"candles": bars}, None)
            line = NF.dataset_line()
            self.assertEqual(NF.require_dataset(f"x\n{line}\n"), {"key": "XAUUSD|5m", "before": NF.EXPOSED_END, "sha256": base})
            for text in ("x\n", f"{line}\n{line}\n", line.replace(base, ("1" if base[0] == "0" else "0") + base[1:]) + "\n",
                         line.replace("XAUUSD|5m", "XAGUSD|5m") + "\n", line.replace(NF.EXPOSED_END, "2026-10-09T00:00:00Z") + "\n"):
                with self.assertRaises(SystemExit):
                    NF.require_dataset(text)
        finally:
            HS.read_doc, NF._bs = orig_read, orig_bs

    def test_code_files_exist(self):
        self.assertEqual(len(NF.CODE), len(set(NF.CODE)))
        for p in NF.CODE + (NF.CALENDAR,):
            self.assertTrue(os.path.exists(os.path.join(ROOT, p)), p)

    def test_code_lists_every_module_a_read_loads(self):
        NF.G.trace_start(ROOT)
        bs = NF._bs()
        NF._load("pass_policy", "scripts/research/pass_policy.py")
        FF = NF._load("fvg_forward", "scripts/research/fvg_forward.py")
        import real_costs  # noqa: F401  (the reads use it for costs and the server zone)
        import history_store  # noqa: F401  (dataset snapshot)
        bs.EC.Costs("XAUUSD")
        real_costs.server_zone(bs.EC.PROVIDER)
        real_costs.price_ref_info(bs.EC.COST_PROFILE, "XAUUSD")                      # cost_profile
        with tempfile.TemporaryDirectory() as tmp:                                   # the forward read's file paths
            FF.live_path("XAUUSD", live_dir=tmp)                                     # merged_candles -> broker_symbols
            FF._store_path("XAUUSD", store_dir=tmp)
            FF._read_log(os.path.join(tmp, "none.jsonl"))
        NF.G.require_covered(NF.CODE)
        loaded = set()
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if not f:
                continue
            rel = os.path.relpath(os.path.abspath(f), ROOT).replace(os.sep, "/")
            if rel.startswith("scripts/") and not rel.startswith("scripts/tests/") and rel.endswith(".py"):
                loaded.add(rel)
        self.assertEqual(sorted(loaded - set(NF.CODE)), [])


# ------------------------------------------------------------------------------------------------ synthetic market
import real_costs as RC  # noqa: E402  (news_flat put scripts/ on sys.path)

ZONE = RC.server_zone("mt5_bridge_ftmo")[1]


def synth_candles(d0, d1, px=100.0, wiggle=0.0004):
    """Server-day 5m bars 01:05-23:40 server time on weekdays (272 a day): a zig-zag around a flat price. SYNTHETIC."""
    out, d = [], d0
    while d <= d1:
        if d.weekday() < 5:
            for k in range(272):
                t = datetime.datetime(d.year, d.month, d.day, 1, 5, tzinfo=ZONE) + datetime.timedelta(minutes=5 * k)
                c = px * (1 + wiggle * (1 if k % 2 else -1))
                out.append({"time": NF.iso(t), "open": px, "high": max(px, c) * 1.0002, "low": min(px, c) * 0.9998, "close": c})
                px = c
        d += datetime.timedelta(days=1)
    return out


def synth_events(offset, extra=()):
    """An events function in book_sim's shape: an entry on the bar after every 97th bar, sides alternating, plus the
    `extra` entries [(entry bar time, side)] placed on purpose around the synthetic releases. SYNTHETIC."""
    def events(series):
        out = [{"i": i, "entry_i": i + 1, "side": 1 if (i // 97) % 2 else -1} for i in range(offset, len(series.T) - 2, 97)]
        idx = {t: j for j, t in enumerate(series.T)}
        out += [{"i": idx[t] - 1, "entry_i": idx[t], "side": side} for t, side in extra]
        return sorted(out, key=lambda ev_: ev_["entry_i"])
    return events


class FlatCosts:
    """The same stub as CutBar.Costs: median leg 2 bp, p90 leg 6 bp, book_sim round trip 2 bp."""
    def __init__(self, sym=None):
        pass

    def leg_at(self, t, stat="median"):
        return 0.0002 if stat == "median" else 0.0006

    def round_trip_at(self, a, b):
        return 0.0002


def synth_series():
    BS = NF._bs()
    s = BS.EC.Series("XAUUSD", synth_candles(datetime.date(2019, 1, 2), datetime.date(2019, 3, 15)), ZONE,
                     end="9999-12-31T00:00:00Z", sigma_every_day=True)
    return BS, s


def synth_trades(BS, s, events):
    """book_sim.trades on the synthetic series (market loaders swapped for the synthetic series and a flat cost)."""
    orig_load, orig_costs = BS.EC.load, BS.EC.Costs
    BS.EC.load, BS.EC.Costs = (lambda sym, end=None: s), FlatCosts
    try:
        return BS.trades("XAUUSD", events, "eod", stop_k=NF.STOP_K)
    finally:
        BS.EC.load, BS.EC.Costs = orig_load, orig_costs


def synth_extra():
    """Around every synthetic release: an entry three hours before its window (open across it), one just inside it, one after."""
    extra, h = [], datetime.timedelta
    for e in synth_calendar().events:
        a, b = NF.window(e)
        extra += [(NF.iso(a - h(hours=3)), 1), (NF.iso(a + h(minutes=5)), -1), (NF.iso(b + h(minutes=20)), 1)]
    return extra


def synth_rows(BS, s):
    """book_sim rows (stop 1.4) of two synthetic components on the synthetic series, as the exposed read builds them."""
    extra = synth_extra()
    return [dict(r, component=c) for c, off, sign in (("H7_XAUUSD_eod", 3, 1), ("G9_XAUUSD_eod", 50, -1))
            for r in synth_trades(BS, s, synth_events(off, [(t, sign * sd) for t, sd in extra]))]


def synth_calendar():
    """Six Wednesday 08:30 New York releases (synthetic rows, each known 30 days ahead); 2019-03-10 starts US daylight time."""
    days = ["2019-02-06", "2019-02-13", "2019-02-20", "2019-02-27", "2019-03-06", "2019-03-13"]
    return cal([ev(f"w{k}", date=d, avail=f"{(datetime.date.fromisoformat(d) - datetime.timedelta(days=30)).isoformat()}T12:00:00Z")
                for k, d in enumerate(days)])


class PlannedEntries(unittest.TestCase):
    def test_same_entries_as_book_sim_without_the_exit_walk(self):
        BS, s = synth_series()
        events = synth_events(3, [("2019-02-20T10:20:00Z", 1), ("2019-02-20T13:25:00Z", -1)])
        full = synth_trades(BS, s, events)
        planned = NF.planned_entries(s, events, "eod")
        self.assertGreater(len(planned), 20)
        self.assertEqual([(r["entry_time"], r["side"], r["server_day"]) for r in planned],
                         [(r["entry_time"], r["side"], r["server_day"]) for r in full])
        self.assertTrue(all(set(r) == {"entry_time", "exit_time", "server_day", "side"} for r in planned))   # no R, no price


class PlannedSpan(unittest.TestCase):
    """UNKNOWN is judged on the planned span, never on the realised exit (CLAUDE.md §37)."""

    def setUp(self):
        # a row with an UNKNOWN time on the New York date 2004-06-30; the server day of the trades below runs from
        # 2004-06-29 22:00 UTC (server UTC+2, DST not yet in force on the server) to 2004-06-30 21:00 UTC
        self.c = cal([ev("st", typ="FOMC_STATEMENT", date="2004-06-30", time=None, avail="2003-06-11T03:59:59Z")])

    def test_a_stop_hit_before_the_unknown_date_does_not_make_the_trade_known(self):
        entry = "2004-06-30T03:00:00Z"                          # 2004-06-29 23:00 New York (EDT): the evening before
        early = trade(entry, "2004-06-30T03:20:00Z", how="stop")    # stopped out 20 minutes later, before the date's window
        held = trade(entry, "2004-06-30T20:55:00Z")                 # held to the end of the server day
        self.assertEqual(NF.classify(held, self.c)["unknown"], ["st"])
        self.assertEqual(NF.classify(early, self.c)["unknown"], [])           # no zone: the realised end is all there is
        self.assertEqual(NF.classify(early, self.c, zone=ZONE)["unknown"], ["st"])    # with the zone: the planned span
        self.assertEqual(NF.classify(early, self.c, zone=ZONE)["unknown"], NF.classify(held, self.c, zone=ZONE)["unknown"])

    def test_server_day_end_is_the_next_server_midnight(self):
        self.assertEqual(NF.iso(NF.server_day_end(T("2019-02-20T10:00:00Z"), ZONE)), "2019-02-20T22:00:00Z")   # server UTC+2
        self.assertEqual(NF.iso(NF.server_day_end(T("2019-07-10T10:00:00Z"), ZONE)), "2019-07-10T21:00:00Z")   # server UTC+3

    def test_flatten_still_uses_the_state_of_the_position_at_the_window_start(self):
        c = cal([ev("a", date="2019-02-20", avail="2019-01-21T12:00:00Z")])             # 13:30 UTC, window from 13:20
        stopped_before = trade("2019-02-20T10:00:00Z", "2019-02-20T13:10:00Z", how="stop")
        held = trade("2019-02-20T10:00:00Z", "2019-02-20T21:35:00Z")
        self.assertIsNone(NF.classify(stopped_before, c, zone=ZONE)["flatten_at"])      # closed before s: nothing to flatten
        self.assertEqual(NF.classify(held, c, zone=ZONE)["flatten_at"], T("2019-02-20T13:20:00Z"))


class ExposedEndToEnd(unittest.TestCase):
    """exposed_result on synthetic bars: the real book_sim rows, the real cut, the real challenge machinery."""

    @classmethod
    def setUpClass(cls):
        cls.BS, cls.s = synth_series()
        cls.rows = synth_rows(cls.BS, cls.s)
        cls.cal = synth_calendar()
        cls.PP = NF._load("pass_policy", "scripts/research/pass_policy.py")
        cls.res = NF.exposed_result(cls.cal, cls.rows, cls.s, FlatCosts(), ZONE, cls.PP)

    def test_the_policies_are_nested_on_identical_rows(self):
        book = self.res["bookkeeping"]
        pol = self.res["policies"]
        self.assertGreater(len(self.rows), 60)
        self.assertEqual(pol["P0"]["n"] + len(book["unknown"]), len(self.rows))
        self.assertEqual(pol["P1"]["n"], pol["P0"]["n"] - len(book["p1_dropped"]))
        self.assertEqual(pol["P2"]["n"], pol["P1"]["n"])
        self.assertGreater(len(book["p1_dropped"]), 0)
        self.assertGreater(len(book["p2_flattened"]), 5)
        self.assertEqual(pol["P2"]["flattened"], len(book["p2_flattened"]))
        self.assertEqual(book["unknown"], [])

    def test_a_flattened_trade_is_the_close_at_the_cut_bar(self):
        s, c = self.s, self.cal
        cut = NF.series_cutter(s, FlatCosts())
        idx = {t: j for j, t in enumerate(s.T)}
        flat = [r for r in self.rows if NF.classify(r, c, zone=ZONE)["flatten_at"] is not None]
        self.assertEqual(len(flat), len(self.res["bookkeeping"]["p2_flattened"]))
        r = flat[0]
        k = NF.classify(r, c, zone=ZONE)
        f = cut(r, k["flatten_at"])
        e = idx[r["entry_time"]]
        j = NF.cut_bar(s, e, k["flatten_at"])
        self.assertEqual(NF.utc(s.T[j]) + NF.BAR, k["flatten_at"])                 # the bar closes exactly at the window start
        dist = r["stop_bp"] / 1e4 * r["entry_px"]
        gross = r["side"] * (s.C[j] - r["entry_px"])
        self.assertAlmostEqual(f["R"], (gross - 0.0004 * r["entry_px"]) / dist)        # median entry leg + p90 flatten leg
        self.assertAlmostEqual(f["R_med"], (gross - 0.0002 * r["entry_px"]) / dist)    # book_sim pricing (sensitivity)
        self.assertEqual((f["exit"], f["exit_time"], f["server_day"]), ("news_flat", s.T[j], r["server_day"]))
        self.assertLess(NF.utc(f["exit_time"]), NF.utc(r["exit_time"]))

    def test_no_row_enters_or_stays_inside_a_known_window(self):
        for r in self.res["bookkeeping"]["p1_dropped"]:
            self.assertTrue(r["events"])
        c = self.cal
        for ev_ in c.events:
            a, b = NF.window(ev_)
            for r in self.rows:
                if a <= NF.utc(r["entry_time"]) <= b:
                    key = (r["component"], r["entry_time"], r["side"])
                    self.assertIn(key, {(d["component"], d["entry_time"], d["side"]) for d in self.res["bookkeeping"]["p1_dropped"]})

    def test_report_shape(self):
        self.assertEqual(set(self.res["ftmo"]), set(NF.POLICIES))
        for p in NF.POLICIES:
            self.assertEqual(set(self.res["ftmo"][p]), {"selection", "confirmation", "daily_loss_breach_days"})
        self.assertEqual(self.res["p2_vs_p1"]["n"], len(self.res["bookkeeping"]["p2_flattened"]))
        self.assertIn("POLICY-EXPOSED", self.res["label"])
        json.dumps(self.res, default=str)                                       # serialisable as the read writes it

    def test_future_bars_do_not_change_the_flatten_decision(self):
        """The cut reads only bars up to the window start: wrecking every later bar leaves each flattened R unchanged."""
        s2 = copy.copy(self.s)
        s2.C = list(self.s.C)
        cut_after = {}
        cutter = NF.series_cutter(self.s, FlatCosts())
        idx = {t: j for j, t in enumerate(self.s.T)}
        for r in self.rows:
            k = NF.classify(r, self.cal, zone=ZONE)
            if k["flatten_at"] is not None:
                cut_after[(r["component"], r["entry_time"])] = (NF.cut_bar(self.s, idx[r["entry_time"]], k["flatten_at"]), k["flatten_at"])
        self.assertGreater(len(cut_after), 5)
        lo_bar = min(j for j, _ in cut_after.values())
        for j in range(lo_bar + 1, len(s2.C)):
            if all(j > jj for jj, _ in cut_after.values()):
                s2.C[j] = 1.0
        a = NF.apply_policies(self.rows, self.cal, cutter, zone=ZONE)
        b = NF.apply_policies(self.rows, self.cal, NF.series_cutter(s2, FlatCosts()), zone=ZONE)
        self.assertEqual([r["R"] for r in a[0]["P2"]], [r["R"] for r in b[0]["P2"]])


class ForwardEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.BS, cls.s = synth_series()
        cls.cal = synth_calendar()
        cls.idx = {t: j for j, t in enumerate(cls.s.T)}

    def paper(self, entry_utc, comp="H7_XAUUSD_eod", side=1, R=-0.2, how="time"):
        s = self.s
        e = self.idx[entry_utc]
        last = max(j for j in range(e, len(s.T)) if s.sday[j] == s.sday[e])
        return {"component": comp, "symbol": "XAUUSD", "h": "eod", "side": side, "entry_time": s.T[e], "exit_time": s.T[last],
                "entry": s.O[e] if hasattr(s, "O") else s.C[e], "stop_distance": 1.0, "stop_k": 1.4, "R": R, "exit_reason": how,
                "exit": s.C[last], "status": "closed", "net_bp": 0.0}

    def rows_for(self, days, per_day):
        out = []
        for d in days:
            for k in range(per_day):
                t = datetime.datetime.fromisoformat(f"{d}T05:00:00+00:00") + datetime.timedelta(minutes=5 * k)
                out.append(self.paper(NF.iso(t), R=-0.2 - 0.001 * k))
        return out

    def test_due_by_time_reports_the_paired_delta_and_the_verdict(self):
        rows = [self.paper("2019-02-20T10:00:00Z"),                                 # open across the window: flattened
                self.paper("2019-02-20T13:25:00Z"),                                 # entered inside the window: P1 drops it
                self.paper("2019-02-20T14:00:00Z")]                                 # entered after the window: untouched
        res = NF.forward_result(self.cal, rows, self.s, FlatCosts(), ZONE, datetime.date(2015, 1, 1), datetime.date(2019, 3, 14))
        self.assertEqual([res["policies"][p]["n"] for p in NF.POLICIES], [3, 2, 2])
        self.assertEqual(res["p2_vs_p1"]["n"], 1)
        self.assertEqual(res["verdict"], "INCONCLUSIVE")                           # one release day only
        self.assertEqual(res["policies"]["P2"]["flattened"], 1)
        self.assertIn("FAIR", res["label"])
        self.assertEqual(res["data_end"], "2019-03-14")

    def test_due_by_count(self):
        days = ["2019-02-06", "2019-02-13", "2019-02-20", "2019-02-27", "2019-03-06", "2019-03-13"]
        rows = self.rows_for(days, 9)                                              # 54 rows open at 08:20 New York
        res = NF.forward_result(self.cal, rows, self.s, FlatCosts(), ZONE, datetime.date(2019, 1, 1), datetime.date(2019, 3, 14))
        self.assertEqual(res["p2_vs_p1"]["n"], 54)
        self.assertEqual(res["p2_vs_p1"]["clusters"], 6)
        self.assertEqual(res["verdict"], "INCONCLUSIVE")                           # fewer than 20 release days

    def test_not_due_and_uncovered_are_refused(self):
        rows = [self.paper("2019-02-20T10:00:00Z")]
        with self.assertRaises(SystemExit) as cm:
            NF.forward_result(self.cal, rows, self.s, FlatCosts(), ZONE, datetime.date(2019, 1, 1), datetime.date(2019, 3, 14))
        self.assertIn("not due", str(cm.exception))
        short = cal([NFP], cov_from="2030-01-01")
        with self.assertRaises(SystemExit) as cm:
            NF.forward_result(short, rows, self.s, FlatCosts(), ZONE, datetime.date(2015, 1, 1), datetime.date(2019, 3, 14))
        self.assertIn("cover", str(cm.exception))
        with self.assertRaises(SystemExit):
            NF.forward_result(self.cal, [], self.s, FlatCosts(), ZONE, datetime.date(2015, 1, 1), datetime.date(2019, 3, 14))

    def test_last_full_day_is_the_day_before_the_last_bars_server_day(self):
        times = [r["time"] for r in synth_candles(datetime.date(2019, 7, 1), datetime.date(2019, 7, 3))]
        self.assertEqual(NF.last_full_day(times, ZONE), datetime.date(2019, 7, 2))
        self.assertEqual(NF.last_full_day(list(reversed(times)), ZONE), datetime.date(2019, 7, 2))
        self.assertIsNone(NF.last_full_day([], ZONE))


class DryCounts(unittest.TestCase):
    def test_pooled_by_type_and_release_days(self):
        c = cal([NFP, ev("st", typ="FOMC_STATEMENT", date="2012-06-01", time="14:00", avail="2012-01-01T00:00:00Z")])
        rows = {"H7_XAUUSD_eod": [trade("2012-06-01T12:30:00Z", "2012-06-01T20:55:00Z"),     # entry inside the NFP window
                                  trade("2012-06-01T11:00:00Z", "2012-06-01T20:55:00Z")],    # open across both windows
                "G9_XAUUSD_eod": [trade("2012-06-01T11:30:00Z", "2012-06-01T20:55:00Z")]}
        out = NF.dry_counts(rows, c)
        self.assertEqual(out["H7_XAUUSD_eod"]["2012"], {"planned": 2, "p1_entry_blocked": 1, "p1_entry_blocked:NFP": 1,
                                                          "planned_open_across_window": 1, "planned_open_across_window:NFP": 1,
                                                          "release_days_with_open_trade": 1})
        self.assertEqual(out["pooled"]["2012"]["planned"], 3)
        self.assertEqual(out["pooled"]["2012"]["planned_open_across_window"], 2)
        self.assertEqual(out["pooled"]["2012"]["release_days_with_open_trade"], 1)       # one release day for both components


class GlueEndToEnd(unittest.TestCase):
    """`_exposed` and `_forward` themselves (the capped loader, book_sim.trades, pass_policy, the cost profile, the committed
    calendar versions, the snapshots) on synthetic bars, with only the file readers swapped for synthetic ones. A bug in
    this glue would otherwise show only at the real read, after the seal."""

    def test_exposed_reads_through_the_capped_loader(self):
        BS, s = synth_series()
        extra = synth_extra()
        BS.COMPONENTS = {"H7_XAUUSD_eod": ("XAUUSD", synth_events(3, extra), "eod"),
                         "G9_XAUUSD_eod": ("XAUUSD", synth_events(50, [(t, -sd) for t, sd in extra]), "eod")}
        asked = []
        BS.EC.load = lambda sym, end=None: asked.append(end) or s
        BS.EC.Costs = FlatCosts
        orig_bs, NF._bs = NF._bs, (lambda: BS)
        try:
            res, pairs = NF._exposed(synth_calendar())
        finally:
            NF._bs = orig_bs
        self.assertEqual(set(asked), {NF.EXPOSED_END})                              # every load saw the cap, never the caller's 9999
        self.assertGreaterEqual(len(asked), 3)                                      # two components and the cut series
        self.assertEqual(pairs, [("XAUUSD", "5m")])
        self.assertEqual(set(res), {"policies", "ftmo", "p2_vs_p1", "p1_vs_p0", "bookkeeping", "label", "cost_profile"})
        self.assertEqual(set(res["cost_profile"]), {"name", "spec_sha256", "price_ref_info"})
        self.assertGreater(res["p2_vs_p1"]["n"], 5)
        self.assertEqual(res["policies"]["P2"]["n"], res["policies"]["P1"]["n"])
        json.dumps(res, default=str)

    def test_forward_reads_rows_calendar_versions_and_snapshot(self):
        candles = synth_candles(datetime.date(2019, 1, 2), datetime.date(2019, 3, 15))
        BS, s = synth_series()
        idx = {t_: j for j, t_ in enumerate(s.T)}
        rows = []
        for d in ("2019-02-06", "2019-02-13", "2019-02-20", "2019-02-27", "2019-03-06", "2019-03-13"):
            for k in range(9):
                tt = NF.iso(datetime.datetime.fromisoformat(f"{d}T05:00:00+00:00") + datetime.timedelta(minutes=5 * k))
                e = idx[tt]
                last = max(j for j in range(e, len(s.T)) if s.sday[j] == s.sday[e])
                rows.append({"component": "H7_XAUUSD_eod", "symbol": "XAUUSD", "h": "eod", "side": 1, "entry_time": tt,
                             "exit_time": s.T[last], "entry": s.O[e], "stop_distance": 1.0, "stop_k": 1.4, "R": -0.2,
                             "exit_reason": "time", "exit": s.C[last], "status": "closed", "net_bp": 0.0})
        rows.append(dict(rows[0], stop_k=2.0))                                       # a pre-v4 row: not read
        rows.append(dict(rows[1], status="open"))                                    # not closed: not read
        rows.append(dict(rows[2], component="E5_XAUUSD_24"))                         # another component: not read
        tmp = tempfile.mkdtemp()
        try:
            log = os.path.join(tmp, "fvg-paper.jsonl")
            with open(log, "w") as fh:
                fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
            FF = NF._load("fvg_forward", "scripts/research/fvg_forward.py")
            FF.LOG = log
            FF._read_log = lambda path=None: [json.loads(ln) for ln in open(log) if ln.strip()]
            FF.merged_candles = lambda sym, live_dir=None, store_dir=None: candles
            FF._store_path = lambda sym, store_dir=None: os.path.join(tmp, "store.json")
            FF.live_path = lambda sym, live_dir=None: os.path.join(tmp, "live.json")
            FF.EC.Costs = FlatCosts
            saved = (NF._load, NF.calendar_versions)
            NF._load = lambda name, rel: FF if name == "fvg_forward" else saved[0](name, rel)
            NF.calendar_versions = lambda root, rel=NF.CALENDAR: [(T("2015-01-01T00:00:00Z"), synth_calendar())]
            try:
                res, pairs = NF._forward(None, datetime.date(2015, 1, 1), ZONE)
            finally:
                NF._load, NF.calendar_versions = saved
            self.assertEqual(res["p2_vs_p1"]["n"], 54)                                # the 54 closed v4 rows open at each window
            self.assertEqual(res["calendar_versions"], 1)
            self.assertEqual(res["forward_snapshot"]["paper_log"]["rows"], len(rows))
            self.assertEqual(res["forward_snapshot"]["paper_log"]["sha256"], NF.G.file_sha256(log))
            self.assertEqual(res["forward_snapshot"]["candles"]["n"], len(candles))
            self.assertEqual(res["forward_snapshot"]["sources"], {"forward_store_sha256": None, "live_bridge_sha256": None})
            self.assertEqual(set(res["cost_profile"]), {"name", "spec_sha256", "price_ref_info"})
            self.assertEqual(res["verdict"], "INCONCLUSIVE")                           # six release days
            self.assertEqual(pairs, [("XAUUSD", "5m")])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Repricing(unittest.TestCase):
    def test_both_legs_share_one_cost_basis_and_the_log_is_kept(self):
        BS, s = synth_series()
        idx = {t_: j for j, t_ in enumerate(s.T)}
        e, x = idx["2019-02-20T10:00:00Z"], idx["2019-02-20T21:35:00Z"]
        row = {"component": "H7_XAUUSD_eod", "side": -1, "entry_time": s.T[e], "exit_time": s.T[x], "entry": 100.0, "exit": 99.0,
               "stop_distance": 2.0, "R": 123.0, "net_bp": 1.0, "exit_reason": "time", "status": "closed"}
        out = NF.reprice_paper_row(row, s, idx, FlatCosts())
        self.assertAlmostEqual(out["R"], (1.0 - 0.0002 * 100.0) / 2.0)                # gross +1.0 on a short, 2 bp round trip
        self.assertEqual(out["R_logged"], 123.0)                                       # the log's own figure is only kept
        self.assertAlmostEqual(out["net_bp"], (1.0 - 0.02) / 100.0 * 1e4)
        self.assertEqual(row["R"], 123.0)                                              # pure


class DryCountsBars(unittest.TestCase):
    def test_a_missing_bar_at_the_window_start_is_counted_not_flattened(self):
        c = synth_calendar()
        candles = [b for b in synth_candles(datetime.date(2019, 1, 2), datetime.date(2019, 3, 15)) if b["time"] != "2019-02-20T13:15:00Z"]
        BS = NF._bs()
        s = BS.EC.Series("XAUUSD", candles, ZONE, end="9999-12-31T00:00:00Z", sigma_every_day=True)
        rows = {"H7_XAUUSD_eod": [trade("2019-02-20T10:00:00Z", "2019-02-20T21:35:00Z"),      # window 13:20: its bar (13:15) is gone
                                  trade("2019-02-13T10:00:00Z", "2019-02-13T21:35:00Z")]}     # a clean day
        out = NF.dry_counts(rows, c, ZONE, s)["H7_XAUUSD_eod"]["2019"]
        self.assertEqual((out["planned"], out["no_bar_at_flatten_instant"], out["planned_open_across_window"]), (2, 1, 1))
        self.assertEqual(out["release_days_with_open_trade"], 1)
        without = NF.dry_counts(rows, c, ZONE)["H7_XAUUSD_eod"]["2019"]                     # without bars the gap is invisible
        self.assertEqual((without["planned_open_across_window"], "no_bar_at_flatten_instant" in without), (2, False))


# ------------------------------------------------------------------------------------------------ ledger and seal rehearsal
class SealRehearsal(TempRepo):
    """The read's refusals in the order the CLI checks them, in a temporary git repository (as test_edge_vc.SealRehearsal):
    refused before the seal, on a manifest gap, a missing calendar pin or dataset pin, a missing or wrong ledger entry, a
    changed dataset, an unread VC, bytecode outside the repository; one read; then read-once and code-change refusals. The
    market glue is stubbed; the guard chain is the real one."""

    DIGEST = "ab" * 32

    def sealed_text(self, drop=None, calendar=True, dataset=True):
        lines = [x for x in NF.G.manifest_lines(self.root, NF.CODE) if drop is None or not x.endswith(" " + drop)]
        if calendar:
            lines.append(NF.calendar_line(path=os.path.join(self.root, NF.CALENDAR)))
        if dataset:
            lines.append(NF.dataset_line())
        return f"# rehearsal {NF.TAG}\n\nStatus: SEALED\n\n" + "\n".join(lines) + "\n"

    def ledger(self, **over):
        entry = {"preregistration": NF.PREREG, "tag": NF.TAG, "policies": len(NF.POLICIES), "reads": len(NF.READS)}
        entry.update(over)
        self.write(NF.LEDGER, json.dumps({NF.LEDGER_KEY: entry}))

    def run_read(self, read, day="2026-10-06"):
        out = os.path.join(self.root, "docs", "audits", f"{day}-edge-nf-{read}.json")
        with contextlib.redirect_stdout(io.StringIO()):
            NF.cmd_run(read, out)
        return out

    def refused(self, read, fragment, day="2026-10-06"):
        with self.assertRaises(SystemExit) as cm:
            self.run_read(read, day)
        self.assertIn(fragment, str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "audits", f"{day}-edge-nf-{read}.json")))

    def setUp(self):
        super().setUp()
        for rel in NF.CODE:
            self.write(rel, f"# stub {rel}\n")
        self.write(NF.CALENDAR, json.dumps(doc([NFP])))
        self.ledger()
        self.commit("code, calendar, ledger")
        self.calls = []
        self.saved = (NF.ROOT, NF._exposed, NF._forward, NF.AFTER_VC, NF.G.dataset_snapshot, NF.exposed_dataset_digest)
        NF.ROOT = self.root
        NF._exposed = lambda cal_: self.calls.append("exposed") or ({"policies": {}}, [])
        NF._forward = lambda cal_, seal_day, zone: self.calls.append("forward") or ({"p2_vs_p1": {"n": 0}}, [])
        NF.G.dataset_snapshot = lambda *a, **k: {}
        NF.exposed_dataset_digest = lambda: self.digest
        self.digest = self.DIGEST
        NF.AFTER_VC = False

    def tearDown(self):
        NF.ROOT, NF._exposed, NF._forward, NF.AFTER_VC, NF.G.dataset_snapshot, NF.exposed_dataset_digest = self.saved
        NF.G._TRACE["on"] = False
        super().tearDown()

    def test_refuses_before_a_sealed_text_exists(self):
        """Both reads, no sealed text anywhere: refused before any data is touched, and nothing is written."""
        for read in NF.READS:
            self.refused(read, "does not exist")
            self.refused(read, NF.PREREG)
        self.assertEqual(self.calls, [])                                           # no read ran
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "audits")))
        self.write(NF.PREREG.replace(".md", "-DRAFT.md"), f"# draft {NF.TAG}\n\nStatus: DRAFT. Not sealed.\n")
        self.commit("only the draft")
        self.refused("exposed", "does not exist")                                  # a draft is not a sealed text

    def test_the_chain_in_order(self):
        self.write(NF.PREREG, self.sealed_text(drop="scripts/research/book_sim.py"))
        self.refused("exposed", "is not tracked")                                   # written, not committed
        self.commit("sealed text without book_sim in the manifest")
        self.refused("exposed", "does not list scripts/research/book_sim.py")       # a file the read needs is not listed
        self.write(NF.PREREG, self.sealed_text(calendar=False))
        self.commit("no calendar pin")
        self.refused("exposed", "calendar-history-sha256")
        self.write(NF.PREREG, self.sealed_text(dataset=False))
        self.commit("no dataset pin")
        self.refused("exposed", "dataset-sha256")                                   # the exposed read only
        self.write(NF.PREREG, self.sealed_text())
        self.write(NF.LEDGER, json.dumps({}))
        self.commit("sealed, ledger without the entry")
        self.refused("exposed", "no 'news_flat' entry")
        self.ledger(policies=2)
        self.commit("ledger with a wrong budget count")
        self.refused("exposed", "records 2 policies")
        self.ledger()
        self.commit("ledger right")
        self.digest = "cd" * 32                                                     # the stored history changed since the seal
        self.refused("exposed", "changed since the seal")
        self.digest = self.DIGEST
        NF.AFTER_VC = True
        self.refused("exposed", "VC's xau-holdout read")                            # the ordering guard, exposed read only
        NF.AFTER_VC = False
        saved = sys.pycache_prefix
        sys.pycache_prefix = "/tmp/elsewhere"
        try:
            self.refused("exposed", "pycache_prefix")
        finally:
            sys.pycache_prefix = saved
        self.assertEqual(self.calls, [])
        out = self.run_read("exposed")                                              # every guard passes: one read
        self.assertEqual(self.calls, ["exposed"])
        res = json.load(open(out))
        m = res["meta"]
        self.assertEqual((m["read"], m["tag"], m["preregistration"]), ("exposed", NF.TAG, NF.PREREG))
        self.assertEqual(m["calendar_sha256"], NF.G.file_sha256(os.path.join(self.root, NF.CALENDAR)))
        self.assertEqual(m["ledger"]["sha256"], NF.G.file_sha256(os.path.join(self.root, NF.LEDGER)))
        self.assertEqual(set(m["code_sha256"]), set(NF.CODE))
        self.assertEqual(m["calendar_history_before"], NF.HISTORY_BEFORE)
        self.assertEqual((m["exposed_end"], m["margin_r"]), (NF.EXPOSED_END, NF.MARGIN_R))
        self.assertEqual(m["pinned_dataset"], {"key": "XAUUSD|5m", "before": NF.EXPOSED_END, "sha256": self.DIGEST})
        self.assertTrue(m["after_vc"] is False)
        self.commit("the exposed read")
        self.refused("exposed", "already ran", day="2026-10-07")                    # read-once, to any other date
        self.write(NF.CODE[0], "# edited after the seal\n")                         # code changed after the seal
        self.commit("code edit")
        self.refused("forward", "code changed since the seal")

    def test_the_forward_read_takes_its_start_from_the_seal_commit(self):
        self.write(NF.PREREG, self.sealed_text(dataset=False))                     # the forward read needs no dataset pin
        self.commit("sealed")
        out = self.run_read("forward", day="2026-10-08")
        m = json.load(open(out))["meta"]
        self.assertEqual(m["first_forward_day"], str(NF.G.first_forward_day(self.root, NF.PREREG, RC.server_zone("mt5_bridge_ftmo")[1])))
        self.assertIn("seal_commit", m)
        self.assertNotIn("pinned_dataset", m)

    def test_ledger_guard_directly(self):
        meta, entry = NF.require_ledger(self.root)
        self.assertEqual((meta["entry"], entry["tag"]), (NF.LEDGER_KEY, NF.TAG))
        self.write(NF.LEDGER, json.dumps({NF.LEDGER_KEY: {"preregistration": "docs/plans/other.md", "tag": NF.TAG,
                                                             "policies": 3, "reads": 2}}))
        with self.assertRaises(SystemExit):
            NF.require_ledger(self.root)                                            # uncommitted change
        self.commit("other")
        with self.assertRaises(SystemExit) as cm:
            NF.require_ledger(self.root)
        self.assertIn(NF.PREREG, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
