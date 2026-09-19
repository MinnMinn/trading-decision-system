"""A3/A4 (docs/plans/2026-09-18-close-feature-gaps.md §0.3) -- `--account` / `--account-file` on the main
backtest report, and `simulate()`'s admission-time news/session refusal.

§0.3: "Refusal happens in simulate() at admission time using entry_time only (PIT: ER.blocked(sym,
at=entry_time, decision_time=entry_time, cal=cal), S.primary(entry_time) in sessions). A profile's own
session_restrictions / news_restrictions apply on top." These tests drive `simulate()` directly for the fast,
deterministic cases and `main()` once for the CLI wiring, per CLAUDE.md §37 (event-driven, PIT, same system as
live) and §33 (a personal and a prop account do not lose the same way).
"""
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP
import sessions as S


def _bt():
    spec = importlib.util.spec_from_file_location("bt_gates", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _calendar(events, pre=10, post=10):
    return {
        "snapshot": {"id": "test-cal-2026-03-02", "covers_through": "2099-01-01T00:00:00Z"},
        "policy": {"pre_minutes": pre, "post_minutes": post,
                  "by_impact": {"HIGH": {"restricted": True}, "MEDIUM": {"restricted": False},
                                "LOW": {"restricted": False}, "UNKNOWN": {"restricted": False}}},
        "events": events,
    }


def _high_event(scheduled):
    # currencies: ["USDT"] matches BTCUSDT's own canonical quote currency directly (instruments.canonical ->
    # {"BTC", "USDT"}) so relevance does not depend on the "USD" alias table this minimal test calendar omits.
    return {"id": "ev1", "name": "Test High Impact", "impact": "HIGH", "status": "scheduled",
           "scheduled_event_time": scheduled, "actual_release_time": None,
           "available_time": "2026-01-01T00:00:00Z", "currencies": ["USDT"], "countries": [], "asset_classes": []}


def _trade(entry_time, exit_time, event="e", entry=100.0, stop=99.0, R=1.0, R_planned=10.0, symbol="BTCUSDT",
          side="long"):
    return dict(symbol=symbol, side=side, entry=entry, stop=stop, target=entry + 3 * (entry - stop),
               R=R, R_planned=R_planned, entry_time=entry_time, exit_time=exit_time, event=event)


class NewsAdmissionRefusal(unittest.TestCase):
    """(a) a calendar with one HIGH event at T refuses [T-10', T+10'], admits outside it."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()

    def test_inside_the_window_is_refused_outside_is_admitted(self):
        cal = _calendar([_high_event("2026-03-02T10:00:00Z")])
        trades = [_trade("2026-03-02T10:00:00Z", "2026-03-02T11:00:00Z", event="inside"),
                 _trade("2026-03-02T10:11:00Z", "2026-03-02T12:00:00Z", event="outside")]
        eq, curve, taken = self.bt.simulate(trades, 0.00001, calendar=cal)
        self.assertEqual(self.bt.SIM_LAST["refused"]["news"], 1)
        self.assertEqual([t["event"] for t in taken], ["outside"])

    def test_exactly_at_the_boundary_is_still_refused(self):
        """§30: the window is closed, not open -- a boundary instant is inside it."""
        cal = _calendar([_high_event("2026-03-02T10:00:00Z")])
        trades = [_trade("2026-03-02T10:10:00Z", "2026-03-02T11:00:00Z", event="boundary")]
        eq, curve, taken = self.bt.simulate(trades, 0.00001, calendar=cal)
        self.assertEqual(self.bt.SIM_LAST["refused"]["news"], 1)
        self.assertEqual(taken, [])

    def test_no_calendar_supplied_refuses_nothing_on_news(self):
        trades = [_trade("2026-03-02T10:00:00Z", "2026-03-02T11:00:00Z", event="e1")]
        eq, curve, taken = self.bt.simulate(trades, 0.00001)
        self.assertEqual(self.bt.SIM_LAST["refused"]["news"], 0)
        self.assertEqual(len(taken), 1)


class SessionAdmissionRefusal(unittest.TestCase):
    """(b) --sessions refuses an entry outside the allowed set; (c) an account's own session_restrictions
    refuses WITHOUT --sessions."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()
        cls.asia_time = "2026-03-02T02:30:00Z"     # S.primary -> 'asia'
        cls.london_time = "2026-03-02T09:30:00Z"   # S.primary -> 'london'
        assert S.primary(cls.asia_time) == "asia"
        assert S.primary(cls.london_time) == "london"

    def test_sessions_flag_refuses_outside_the_allowed_set(self):
        trades = [_trade(self.asia_time, "2026-03-02T03:00:00Z", event="asia"),
                 _trade(self.london_time, "2026-03-02T10:00:00Z", event="london")]
        eq, curve, taken = self.bt.simulate(trades, 0.00001, sessions=("london",))
        self.assertEqual(self.bt.SIM_LAST["refused"]["session"], 1)
        self.assertEqual([t["event"] for t in taken], ["london"])

    def test_account_session_restrictions_refuse_without_a_sessions_flag(self):
        prof = copy.deepcopy(AP.get("ftmo-challenge-phase1"))
        prof["rules"]["session_restrictions"] = {"allowed_sessions": ["london"], "action": "BLOCK_ENTRY"}
        trades = [_trade(self.asia_time, "2026-03-02T03:00:00Z", event="asia")]
        eq, curve, taken = self.bt.simulate(trades, 0.00001, account=prof)
        self.assertEqual(self.bt.SIM_LAST["refused"]["session"], 1)
        self.assertEqual(taken, [])

    def test_account_restriction_narrows_an_already_narrower_sessions_flag(self):
        """The account may only TIGHTEN (§33): the effective set is the intersection."""
        prof = copy.deepcopy(AP.get("ftmo-challenge-phase1"))
        prof["rules"]["session_restrictions"] = {"allowed_sessions": ["asia"], "action": "BLOCK_ENTRY"}
        trades = [_trade(self.london_time, "2026-03-02T10:00:00Z", event="london")]
        # --sessions london,asia is wider than the CLI alone would need, but the account only allows asia
        eq, curve, taken = self.bt.simulate(trades, 0.00001, account=prof, sessions=("london", "asia"))
        self.assertEqual(taken, [], "the account's own session_restrictions must still bind")


class RefusedTradesNeverTouchTheAccount(unittest.TestCase):
    """(d) refused trades never appear in `taken` and the equity curve is unchanged by them."""

    def test_an_all_refused_population_leaves_equity_and_curve_untouched(self):
        bt = _bt()
        cal = _calendar([_high_event("2026-03-02T10:00:00Z")])
        trades = [_trade("2026-03-02T10:00:00Z", "2026-03-02T11:00:00Z", event="e1"),
                 _trade("2026-03-02T10:05:00Z", "2026-03-02T12:00:00Z", event="e2")]
        eq, curve, taken = bt.simulate(trades, 0.00001, calendar=cal)
        self.assertEqual(taken, [])
        self.assertEqual(curve, [])
        self.assertEqual(eq, bt.START)
        self.assertEqual(bt.SIM_LAST["refused"]["news"], 2)


class SnapshotRecordsNewsAndSessionRules(unittest.TestCase):
    """(e) snapshot records news_rules / session when calendar/sessions were supplied."""

    def test_news_rules_and_session_are_reported_not_not_applicable(self):
        import snapshot
        bt = _bt()
        cal = _calendar([_high_event("2026-03-02T10:00:00Z")])
        fields = snapshot.backtest_config_snapshot(
            bt, timeframes=["15m"], methods={"ICT"}, market="crypto",
            calendar=cal, sessions=("london", "ny_am"))["fields"]
        self.assertNotIn("unavailable", fields["news_rules"])
        self.assertNotIn("not_applicable", fields["news_rules"])
        self.assertEqual(fields["news_rules"]["calendar_snapshot_id"], "test-cal-2026-03-02")
        self.assertNotIn("not_applicable", fields["session"])
        self.assertEqual(fields["session"]["allowed_sessions"], ["london", "ny_am"])

    def test_without_either_flag_both_stay_not_applicable(self):
        import snapshot
        bt = _bt()
        fields = snapshot.backtest_config_snapshot(bt, timeframes=["15m"], methods={"ICT"}, market="crypto")["fields"]
        self.assertIn("not_applicable", fields["news_rules"])
        self.assertIn("not_applicable", fields["session"])


class AssessRunStopsDeclaringNotApplicableWithACalendar(unittest.TestCase):
    """(f) assess_run no longer marks future_calendar_state not-applicable when a calendar is supplied."""

    def test_a_calendar_flips_the_condition_from_not_applicable_to_checked(self):
        bt = _bt()
        cal = _calendar([_high_event("2026-03-02T10:00:00Z")])
        block = bt.assess_run(calendar=cal).stamp()
        self.assertNotIn("future_calendar_state", block["not_applicable"])
        self.assertIn("future_calendar_state", block["checked"])

    def test_without_a_calendar_the_condition_stays_not_applicable(self):
        bt = _bt()
        self.assertIn("future_calendar_state", bt.assess_run().stamp()["not_applicable"])


class AccountOnTheMainReport(unittest.TestCase):
    """A3: `--account` on `main()`'s report."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()
        series, _src = cls.bt.load("BTCUSDT", "15m")
        if not series:
            raise unittest.SkipTest("no BTCUSDT 15m history on this machine")

    def test_account_flag_names_the_account_and_carries_failed_by(self):
        out_path = tempfile.NamedTemporaryFile(suffix=".md", delete=False).name
        argv = ["backtest-methods.py", "--tf", "15m", "--symbols", "BTCUSDT",
               "--account", "ftmo-challenge-phase1", "--out", out_path]
        try:
            with mock.patch.object(sys, "argv", argv):
                self.bt.main()
            self.assertEqual(self.bt.SIM_LAST["account"], "ftmo-challenge-phase1")
            md = open(out_path, encoding="utf-8").read()
            self.assertIn("ftmo-challenge-phase1", md)
            self.assertIn("Fail theo luật", md)
        finally:
            os.unlink(out_path)

    def test_account_and_account_file_together_is_refused(self):
        argv = ["backtest-methods.py", "--account", "ftmo-challenge-phase1", "--account-file", "x.json"]
        with mock.patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit):
                self.bt.main()

    def test_load_account_is_the_one_loader_stability_report_also_calls(self):
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("bt.load_account(", src)


if __name__ == "__main__":
    unittest.main()
