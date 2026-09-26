"""scripts/rank-setups.py per-horizon coverage invariants, restated for ADR 0008's criteria selection.

History: this file pinned the 2026-09-13 "one setup per (horizon, method)" ranking and the 2026-09-19 prop-pass
ranking. ADR 0008 (owner decision 2026-09-26) removed ranking altogether -- every system that passes its
horizon's criteria on in-sample AND OOS is enabled -- so the invariants that still mean something are kept here
in their criteria form, and the ranking-order tests (prop-pass key, small-sample lower bound, one winner per
slot) were deleted with the behaviour they pinned:

  * two RUNNABLE methods passing at the same horizon are BOTH enabled (the crowding-out bug cannot return:
    there is no winner to crowd anyone out);
  * setup ids are unique;
  * a retired timeframe is never a candidate (HORIZONS maps one timeframe per horizon, compared with `==`);
  * a gap at one (horizon, method) does not remove other horizons;
  * a losing or ruined row is never enabled, and a window under three months is not evidence;
  * the committed selection file names only RUNNABLE methods at horizon timeframes.
"""
import importlib.util, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import selection_criteria as SC

_spec = importlib.util.spec_from_file_location("rank_setups", os.path.join(ROOT, "scripts", "rank-setups.py"))
RS = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(RS)
CRIT = SC.load()


def _blk(since, until, **kw):
    b = dict(n=40, since=since, until=until, m_mean_geo=6.0, m_losing=0, m_worst=-1.0, dd=3.0, q_worst=-0.5, ruin=None)
    b.update(kw)
    return b


def _row(tf, method, cfg="A", target="live", is_kw=None, oos_kw=None):
    return {"tf": tf, "cfg": cfg, "method": method, "target": target if method == "ICT" else "border",
            "file": "test-fixture.json", "first": "2023-01-01", "last": "2026-09-11",
            "oos6m": {"cutoff": "2026-03-11T00:00:00Z", "dataset_last_bar": "2026-09-11T00:00:00Z",
                      "in_sample": _blk(**{"since": "2025-03-11", "until": "2026-03-11", **(is_kw or {})}),
                      "oos": _blk(**{"since": "2026-03-11", "until": "2026-09-11", "n": 20, **(oos_kw or {})})}}


def _enabled(rows, market="crypto"):
    judged, _o, _b = RS.select_criteria(rows, market, CRIT)
    return [j for j in judged if j["decision"] == RS.ENABLED]


class SelectionCoversEveryMethodPerHorizon(unittest.TestCase):
    def setUp(self):
        self.runnable = sorted(M.runnable())
        self.assertGreaterEqual(len(self.runnable), 2, "need >=2 runnable methods for this test to be meaningful")
        self.a, self.b = self.runnable[0], self.runnable[1]

    def test_two_methods_same_horizon_both_enabled(self):
        en = _enabled([_row("15m", self.a, is_kw=dict(m_mean_geo=20.0)), _row("15m", self.b)])
        self.assertEqual({j["row"]["method"] for j in en if j["horizon"] == "scalping"}, {self.a, self.b})

    def test_setup_ids_unique(self):
        en = _enabled([_row("15m", self.a), _row("15m", self.b), _row("1H", self.a), _row("4H", self.b)])
        ids = [j["id"] for j in en]
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_a_retired_timeframe_is_never_selectable(self):
        for retired in ("5m", "30m", "2H", "1D"):
            self.assertEqual(_enabled([_row(retired, self.a)]), [], retired)

    def test_missing_method_at_one_horizon_does_not_drop_others(self):
        en = _enabled([_row("15m", self.a), _row("15m", self.b), _row("4H", self.b)])
        pairs = {(j["horizon"], j["row"]["method"]) for j in en}
        self.assertIn(("swing", self.b), pairs); self.assertNotIn(("swing", self.a), pairs)


class LosersAreNeverSelected(unittest.TestCase):
    def test_a_ruined_row_is_never_enabled(self):
        self.assertEqual(_enabled([_row("1H", "WYCKOFF-BOOK", is_kw=dict(ruin="2026-01-29", m_mean_geo=-30.0,
                                                                            dd=92.0, m_worst=-60.0))]), [])

    def test_a_losing_row_is_never_enabled(self):
        self.assertEqual(_enabled([_row("1H", "WYCKOFF-BOOK", oos_kw=dict(m_mean_geo=-1.0))]), [])

    def test_a_profitable_row_meeting_the_criteria_is_enabled(self):
        self.assertEqual(len(_enabled([_row("1H", "WYCKOFF-BOOK")])), 1)

    def test_a_window_shorter_than_three_months_is_not_evidence(self):
        self.assertEqual(RS.MIN_WINDOW_DAYS, 90)
        self.assertEqual(_enabled([_row("1H", "WYCKOFF-BOOK", is_kw=dict(since="2026-01-01"))]), [])   # 69 days
        self.assertEqual(len(_enabled([_row("1H", "WYCKOFF-BOOK", is_kw=dict(since="2025-12-11"))])), 1)  # 90 days

    def test_the_note_no_longer_claims_negative_rows_are_kept(self):
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertNotIn("kể cả khi lợi thế backtest yếu hoặc âm", src)
        self.assertNotIn("negative_backtest", src)


class CommittedSelectionIsRunnable(unittest.TestCase):
    def test_every_selected_setup_is_a_runnable_method_at_a_horizon_timeframe(self):
        path = os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")
        setups = json.load(open(path, encoding="utf-8"))["setups"]
        for s in setups:
            self.assertIn(s["method"], M.runnable(), s["id"])
            self.assertIn(s["tf"], RS.HORIZON_OF_TF, s["id"])


if __name__ == "__main__":
    unittest.main()
