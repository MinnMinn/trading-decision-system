"""Leakage probe for EVERY research event detector: truncating the future must never change a past event.

Why (docs/audits/2026-10-03-e5-lookahead-erratum.md §4): the E5 selection kept an earlier-formed gap touched LATER over a
later gap already filled -- a choice that needs future bars -- and only E1 had a "truncate and re-detect" test. This probe
runs every detector of the census, F3, F4, AMD and F6 on a seeded random-walk series and on prefixes of it, and requires
that the events whose entry (and exit, when the detector fixes one) lies before the cut are IDENTICAL. Hand-built bars only.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_detector_leakage_probe
"""
import datetime
import importlib.util
import os
import random
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", "research", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EC, F3, F4, AMD, F6 = (_load(n) for n in ("edge_census", "edge_f3", "edge_f4", "edge_amd", "edge_f6"))
UTC = datetime.timezone.utc


def walk(seed=7, weekdays=75):
    """5m bars around the clock on weekdays: a random walk with occasional displacement bars (FVGs, big bars, breakouts)."""
    rng = random.Random(seed)
    out, p, t = [], 2000.0, datetime.datetime(2023, 1, 2, tzinfo=UTC)
    days = 0
    while days < weekdays:
        if t.weekday() < 5:
            for k in range(288):
                o = p
                jump = rng.random() < 0.02
                p = o * (1 + (rng.choice((-1, 1)) * 0.006 if jump else rng.gauss(0, 0.0008)))
                wick = abs(rng.gauss(0, 0.0003)) * o
                out.append({"time": (t + datetime.timedelta(minutes=5 * k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "open": o, "high": max(o, p) + (0.0 if jump else wick), "low": min(o, p) - (0.0 if jump else wick),
                            "close": p})
            days += 1
        t += datetime.timedelta(days=1)
    return out


def detectors():
    d = {f"census:{k}": (v, "XAUUSD") for k, v in EC.DETECTORS.items()}
    d["census:E6_opening_range_breakout"] = (EC.DETECTORS["E6_opening_range_breakout"], "US500")
    d["census:E7_intraday_momentum"] = (EC.DETECTORS["E7_intraday_momentum"], "US500")
    d.update({f"F3:{k}": (v, "XAUUSD") for k, v in F3.DETECTORS.items()})
    d.update({f"F4:{k}": (v, "US500" if k == "G7_turn_of_month_long" else "XAUUSD") for k, v in F4.DETECTORS.items()})
    d.update({f"AMD:{k}": (v, "XAUUSD") for k, v in AMD.DETECTORS.items()})
    d["F6:events"] = (F6.events, "US500")
    return d


# Detectors whose research version keeps an event only if something about the SAME server day or the next one turns out
# complete -- known, disclosed, and NOT the E5 kind of look-ahead (they can only DROP events on an incomplete day, never pick
# a different one). The probe still checks every complete day for them, and that they never ADD an event.
KNOWN_COMPLETENESS = {
    "F3:H3_hour_shock_fade": "sigma exists only on days that turn out dense (docs/audits/2026-10-02-fvg-book-sim.md §6)",
    "F3:H7_breakout_with_trend": "momentum keyed on dense days only (edge_f3.ev_breakout_trend comment; live uses sigma_every_day)",
    "F4:G3_h7_new_symbols": "same detector as H7",
    "F4:G1_tsmom_overnight": "the next day's density is an outcome-side filter (docs/plans/2026-10-02-edge-f4-preregistration.md §1)",
    "F6:events": "an event needs its exit bar (09:00 Berlin / 09:30 New York) to exist: an outcome-side availability filter "
                 "(docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md §2)",
}


def key(ev):
    """The ENTRY decision: signal bar, side, entry bar, entry price, window. Exits are outcomes, not decisions."""
    return (ev.get("i"), ev.get("side"), ev.get("entry_i"),
            None if ev.get("entry_px") is None else round(ev["entry_px"], 9), ev.get("window"))


def entries(evs, cut):
    return {key(ev) for ev in evs if ev.get("entry_i") is not None and ev["entry_i"] < cut}


def check(tc, name, s_full, full, part, cut):
    """Complete days (before the cut bar's server day): identical. The cut day: the truncated run may only MISS events that
    the full run takes (and only for KNOWN_COMPLETENESS), never take one the full run does not."""
    cut_day = s_full.sday[cut]
    day = lambda k: s_full.sday[k[2]]
    f_done = {k for k in full if day(k) < cut_day}
    p_done = {k for k in part if day(k) < cut_day}
    if name in ("F4:G1_tsmom_overnight",):           # entry on day d's last bar, exit on d+1: d+1 complete is the filter
        prev = max((d for d in s_full.day_rows if d < cut_day), default=None)
        f_done = {k for k in f_done if day(k) != prev}
        p_done = {k for k in p_done if day(k) != prev}
    tc.assertEqual(p_done, f_done, "complete days")
    f_cut = {k for k in full if day(k) == cut_day}
    p_cut = {k for k in part if day(k) == cut_day}
    tc.assertLessEqual(p_cut, f_cut, "the truncated run took an event the full run does not take (look-ahead)")
    if name not in KNOWN_COMPLETENESS:
        tc.assertEqual(p_cut, f_cut, "the truncated run missed an event on the cut day")


SERIES = lambda sym, bars: EC.Series(sym, bars, UTC, end="9999-12-31T00:00:00Z")


class Probe(unittest.TestCase):
    def test_no_detector_changes_a_past_event_when_the_future_is_cut(self):
        bars = walk()
        n = len(bars)
        cuts = (n // 3 + 101, n // 2 + 37, 2 * n // 3 + 200, n - 150, 288 * 50)       # mid-day cuts and a day boundary
        for name, (det, sym) in detectors().items():
            s_full = SERIES(sym, bars)
            full_evs = det(s_full)
            for cut in cuts:
                with self.subTest(detector=name, cut=cut):
                    check(self, name, s_full, entries(full_evs, cut), entries(det(SERIES(sym, bars[:cut])), cut), cut)

    def test_the_probe_catches_the_old_e5_selection(self):
        """The pre-2026-10-03 rule (first in FORMATION order) must FAIL this probe -- otherwise the probe proves nothing. The
        cut is placed where the old and the new rule disagree (between the later gap's fill and the earlier gap's touch)."""
        def old_first_per_day(events):
            seen, out = set(), []
            for ev in events:
                k = (ev["day"], ev["side"])
                if k not in seen:
                    seen.add(k)
                    out.append(ev)
            return out
        bars = walk()
        s_full = SERIES("XAUUSD", bars)
        new = {(e["day"], e["side"]): e for e in EC.ev_fvg(s_full)}
        real = EC._first_per_day
        EC._first_per_day = old_first_per_day
        try:
            old = {(e["day"], e["side"]): e for e in EC.ev_fvg(s_full)}
            diff = [(old[k]["entry_i"], new[k]["entry_i"]) for k in old if k in new and old[k]["entry_i"] != new[k]["entry_i"]]
            self.assertTrue(diff, "the random walk must contain a two-gap day where the rules disagree")
            cut = diff[0][0]                                   # the old rule's (later) entry: not yet happened
            full = entries(EC.ev_fvg(s_full), cut)
            part = entries(EC.ev_fvg(SERIES("XAUUSD", bars[:cut])), cut)
            with self.assertRaises(AssertionError):
                check(self, "census:E5_fvg_retrace", s_full, full, part, cut)
        finally:
            EC._first_per_day = real


if __name__ == "__main__":
    unittest.main()
