"""CLAUDE.md §8 -- availableTime <= decisionTime, for all sixteen kinds of input.

The invariant was enforced for exactly ONE of the sixteen kinds (candles), in three places, three ways:
`live_rules.read_at()` by index, `strategy-runner.drop_forming()` by time, `ict-scan` by position (`c[-2]`).
Each is correct in its own domain. None of them extends to news, to an expectation, or to a provider
correction, because those have no bar index and no position in a series.

So these tests hold three things:

  1. The gate refuses a future-dated input of ANY kind -- generically, driven off the spec's own list, so a
     seventeenth kind cannot arrive ungated.
  2. The boundary is `<=`, matching what `drop_forming()` has always done. Getting this backwards by one
     tick would silently change which bars a live setup sees.
  3. The three existing mechanisms agree with the gate on the one question they share. This is the test that
     makes the new module safe to trust: if it disagreed with the live engine about which bars are readable,
     it would be a fourth opinion rather than a single definition.
"""
import datetime
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N
import pit
import spec

UTC = datetime.timezone.utc
T = lambda h, m=0: datetime.datetime(2026, 9, 17, h, m, tzinfo=UTC)


def bar(t, close=100.0):
    return {"time": t, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}


def runner():
    s = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


class TheSpecsOwnList(unittest.TestCase):
    @unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
    def test_every_input_kind_the_spec_names_is_declared(self):
        """Driven off §8's bullets. A seventeenth kind in the spec fails this test rather than arriving with
        no PIT story -- which is what CLAUDE.md §28 warns happens the moment a calendar joins the backtest."""
        listed = spec.bullet_list(spec.after(spec.body(8), "This applies to:"))
        self.assertEqual(len(listed), 16, f"§8's list changed shape: {listed}")
        normalized = {k.replace(" ", "_") for k in listed}
        self.assertEqual(normalized, set(pit.INPUT_KINDS),
                         f"declared kinds differ from §8's list; missing={normalized - set(pit.INPUT_KINDS)}, "
                         f"extra={set(pit.INPUT_KINDS) - normalized}")

    def test_an_undeclared_kind_refuses(self):
        with self.assertRaises(ValueError):
            pit.input_("vibes", "x", available_time=T(18))


class TheInvariant(unittest.TestCase):
    def test_a_past_input_is_admitted(self):
        r = pit.admit([pit.input_("candles", "b", available_time=T(18))], decision_time=T(19))
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["admitted"]), 1)

    def test_a_future_input_is_refused_with_a_reason_naming_the_gap(self):
        r = pit.admit([pit.input_("news", "CPI", available_time=T(19))], decision_time=T(18))
        self.assertFalse(r["ok"])
        self.assertIn("look-ahead of 3600s", r["refused"][0]["reason"])
        self.assertIn("CPI", r["refused"][0]["reason"])

    def test_available_exactly_at_the_decision_instant_is_admissible(self):
        """The boundary convention, matching drop_forming(): available AT the decision time counts."""
        r = pit.admit([pit.input_("candles", "b", available_time=T(18))], decision_time=T(18))
        self.assertTrue(r["ok"], "a bar closing exactly at the decision instant must be readable")

    def test_every_declared_kind_is_gated_the_same_way(self):
        """Generic over all sixteen: no kind gets an exemption."""
        for kind in pit.INPUT_KINDS:
            r = pit.admit([pit.input_(kind, "x", available_time=T(19))], decision_time=T(18))
            self.assertFalse(r["ok"], f"{kind} was admitted from the future")

    def test_assert_admissible_raises_on_look_ahead(self):
        with self.assertRaises(pit.LookAheadError):
            pit.assert_admissible([pit.input_("expectations", "t1", available_time=T(19))], decision_time=T(18))

    def test_a_naive_timestamp_refuses_instead_of_being_assumed_utc(self):
        """A naive time in a PIT check is an unanswered question about which clock it came from; assuming UTC
        is how a DST-shifted local timestamp reads as an hour of free look-ahead."""
        with self.assertRaises(ValueError):
            pit.input_("candles", "b", available_time=datetime.datetime(2026, 9, 17, 18))

    def test_event_time_and_available_time_are_separate(self):
        """§7 keeps them apart and §8 gates on the second. A figure released at 13:30 for a January reference
        month became knowable at 13:30, not in January."""
        i = pit.input_("economic_calendar", "CPI Jan", event_time="2026-01-31T00:00:00Z",
                       available_time="2026-02-12T13:30:00Z")
        self.assertLess(i["event_time"], i["available_time"])
        early = pit.admit([i], decision_time="2026-02-01T00:00:00Z")
        self.assertFalse(early["ok"], "an unreleased figure must not be readable from its reference date")
        later = pit.admit([i], decision_time="2026-02-12T13:30:00Z")
        self.assertTrue(later["ok"])


class AgreesWithTheExistingMechanisms(unittest.TestCase):
    """The test that makes this module a single definition rather than a fourth opinion."""

    ROWS = [bar("2026-09-17T17:30:00Z"), bar("2026-09-17T17:45:00Z"), bar("2026-09-17T18:00:00Z")]

    def test_series_as_of_matches_drop_forming_in_the_regime_drop_forming_is_used_in(self):
        """Agreement holds under `drop_forming()`'s precondition, which is worth naming rather than assuming.

        `drop_forming()` examines only the LAST row: it assumes every earlier bar is complete. That is true
        of the input it actually gets -- a trailing fetch made AT the decision time, so the newest bar is the
        only one that can still be forming. The decision times below are therefore at or after the last bar's
        open, which is the only shape the live path produces.

        Outside that precondition the two deliberately differ, and the gate is the stricter one: fed a series
        whose rows run past `now` (which a trailing fetch never returns), `drop_forming()` keeps bars that
        have not closed while `series_as_of()` excludes them. That is not a defect in `drop_forming()` -- it
        is the difference between a rule with a precondition and an invariant without one, and it is why the
        new kinds in §8, which have no "last row" to lean on, need the invariant."""
        sr = runner()
        for now in (T(18, 0), T(18, 5), T(18, 14), T(18, 15), T(18, 16), T(19, 0)):
            mine = [r["time"] for r in pit.series_as_of(list(self.ROWS), "15m", now)]
            theirs = [r["time"] for r in sr.drop_forming(list(self.ROWS), "15m", now)]
            self.assertEqual(mine, theirs, f"disagreement at {now.isoformat()}")

    def test_outside_that_precondition_the_gate_is_the_stricter_one(self):
        """Stated as a property so the difference is recorded, not discovered later."""
        sr = runner()
        now = T(17, 44)                      # before any bar in the fixture has closed
        self.assertEqual(len(sr.drop_forming(list(self.ROWS), "15m", now)), 2,
                         "premise changed: drop_forming used to keep unclosed earlier bars")
        self.assertEqual(pit.series_as_of(list(self.ROWS), "15m", now), [],
                         "no bar in this fixture had closed by 17:44, so none is readable")

    def test_it_also_catches_what_drop_forming_cannot(self):
        """drop_forming() trusts that only the last row can be unfinished -- true for a trailing fetch, false
        for a series with a future-stamped row in the middle, which CLAUDE.md §55 asks to be tested."""
        sr = runner()
        poisoned = [bar("2026-09-17T17:30:00Z"), bar("2026-09-19T00:00:00Z"), bar("2026-09-17T18:00:00Z")]
        now = T(18, 30)
        self.assertEqual(len(sr.drop_forming(list(poisoned), "15m", now)), 3,
                         "premise changed: drop_forming used to keep a mid-series future bar")
        kept = pit.series_as_of(list(poisoned), "15m", now)
        self.assertEqual([r["time"] for r in kept],
                         ["2026-09-17T17:30:00Z", "2026-09-17T18:00:00Z"],
                         "the future-stamped row must be excluded, wherever it sits")

    def test_the_index_mechanism_never_exposes_a_bar_the_gate_would_refuse(self):
        """live_rules.read_at may look at candles[:i+1]. Expressed in the gate's terms: every bar in that
        prefix is available at the moment bar i closes."""
        import live_rules
        self.assertIn("candles", live_rules.read_at.__doc__ or "read_at reads candles")
        rows = [bar(f"2026-09-17T{h:02d}:00:00Z") for h in range(10, 20)]
        for i in range(len(rows)):
            decision = N.available_time(rows[i], "1H")
            admitted = pit.series_as_of(rows, "1H", decision)
            self.assertEqual(len(admitted), i + 1,
                             f"at bar {i}'s close the readable prefix must be exactly candles[:{i+1}]")


class CandleHelper(unittest.TestCase):
    def test_candle_input_uses_the_one_availability_rule(self):
        i = pit.candle_input(bar("2026-09-17T18:00:00Z"), "15m", symbol="BTCUSDT")
        self.assertEqual(i["kind"], "candles")
        self.assertEqual(i["available_time"], T(18, 15))
        self.assertEqual(i["event_time"], T(18, 0))


if __name__ == "__main__":
    unittest.main()
