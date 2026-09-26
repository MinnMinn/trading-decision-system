"""Audit round 4b, finding INT-5 (docs/audits/2026-09-24-system-audit.md): setups were selected on the same
window they were judged on. `scripts/rank-setups.py --horizons --window oos6m` now selects on an in-sample
window that ENDS at a cutoff derived from the data (last bar date - 6 calendar months, written by
`scripts/stability-report.py`), and enables an in-sample pick only if its held-out months are profitable.

Covered here:
  * the in/out split boundary (entry exactly at the cutoff -> OOS; opened before, closed after -> in-sample)
  * the cutoff is derived from the data, never typed
  * the OLD `--window 1y` ranking selected on the holdout -- pinned to PRE_ROUND4B = "c86c8e4", never HEAD
The round-4b per-slot selection (in-sample winner + OOS profitability gate), its budget and its report were
replaced by ADR 0008's criteria selection; those tests moved to test_audit_round4c_selection.py.

The old-behaviour test extracts only the pure `solvent()`/`rank()` functions from rank-setups.py AT c86c8e4
(via `git show`) and executes them in an isolated namespace. They reference no sibling module, so no mixture
of revisions is possible (the trap test_audit_round4_integrity.py's docstring describes).
"""
import ast, datetime, glob, importlib.util, json, os, subprocess, sys, tempfile, unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
PRE_ROUND4B = "c86c8e4"   # the round-4a merge commit this round started from -- NOT "HEAD"


def load(name, modname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


SR = load("stability-report.py", "stability_report_r4b")
RS = load("rank-setups.py", "rank_setups_r4b")

CUT = "2026-03-11T00:00:00Z"
IS_SINCE = "2025-03-11T00:00:00Z"


def _block(n, *, since, until, ann=10.0, ruin=None, q_pos=75.0, q_worst=-1.0, dd=3.0, net=100.0, ex=0.2, pf=1.3):
    return dict(n=n, ann=ann, ruin=ruin, q_pos=q_pos, q_worst=q_worst, dd=dd, since=since[:10], until=until[:10],
                net_pnl=net, expectancy_R=ex, profit_factor=pf, final=10000 + net)


def row(tf="15m", method="ICT", cfg="A", *, is_kw=None, oos_kw=None, file="data/history/stability/crypto-live.json",
        target="live", w1y=None):
    """A stability row carrying the round-4b `oos6m` block. `w1y` is the OLD mode's last-365-day block."""
    r = dict(tf=tf, cfg=cfg, method=method, first="2023-09-13", last="2026-09-11", n=200, ann=5.0, dd=10.0,
             final=11000.0, ruin=None, q_pos=60.0, q_worst=-3.0, stab=1.0, y_pos=2, y_n=4, years=[], market="crypto",
             target=target, file=file, research_validity="FLAGGED",
             oos6m=dict(cutoff=CUT, dataset_last_bar="2026-09-11T05:45:00Z", split="entry_time",
                        in_sample=_block(**dict(dict(n=40, since=IS_SINCE, until=CUT), **(is_kw or {}))),
                        oos=_block(**dict(dict(n=20, since=CUT, until="2026-09-11"), **(oos_kw or {})))))
    if w1y is not None:
        r["w1y"] = w1y
    return r


class SplitBoundary(unittest.TestCase):
    def t(self, entry, exit_, name):
        return dict(entry_time=entry, exit_time=exit_, name=name)

    def test_entry_exactly_at_cutoff_is_oos(self):
        ins, oos = SR.split_in_out([self.t(CUT, "2026-03-11T04:00:00Z", "at")], CUT, IS_SINCE)
        self.assertEqual([x["name"] for x in oos], ["at"]); self.assertEqual(ins, [])

    def test_opened_before_closed_after_is_in_sample(self):
        ins, oos = SR.split_in_out([self.t("2026-03-10T23:45:00Z", "2026-03-12T08:00:00Z", "straddle")], CUT, IS_SINCE)
        self.assertEqual([x["name"] for x in ins], ["straddle"]); self.assertEqual(oos, [])

    def test_in_sample_starts_at_lookback_and_nothing_is_in_both(self):
        trades = [self.t("2025-03-10T23:59:00Z", "2025-03-11T02:00:00Z", "too-old"),
                  self.t(IS_SINCE, "2025-03-11T02:00:00Z", "first-is"),
                  self.t("2026-09-10T00:00:00Z", "2026-09-10T04:00:00Z", "late-oos")]
        ins, oos = SR.split_in_out(trades, CUT, IS_SINCE)
        self.assertEqual([x["name"] for x in ins], ["first-is"]); self.assertEqual([x["name"] for x in oos], ["late-oos"])
        self.assertFalse({id(x) for x in ins} & {id(x) for x in oos})

    def test_split_ignores_exit_time_entirely(self):
        """Membership is a DECISION-time fact (CLAUDE.md §8): a trade whose exit is before the cutoff but whose
        entry is after cannot exist, and one whose exit is far in the future stays where its entry put it."""
        ins, _ = SR.split_in_out([self.t("2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "long")], CUT, IS_SINCE)
        self.assertEqual(len(ins), 1)


class CutoffDerivedFromData(unittest.TestCase):
    def test_last_bar_date_minus_six_calendar_months(self):
        self.assertEqual(SR.oos_cutoff("2026-09-11T05:45:00Z"), "2026-03-11T00:00:00Z")
        self.assertEqual(SR.oos_cutoff("2026-09-18T03:45:00Z"), "2026-03-18T00:00:00Z")
        self.assertEqual(SR.oos_cutoff("2026-01-15T00:00:00Z"), "2025-07-15T00:00:00Z")   # crosses a year

    def test_month_end_clamps(self):
        self.assertEqual(SR.oos_cutoff("2026-08-31T12:00:00Z"), "2026-02-28T00:00:00Z")
        self.assertEqual(SR.oos_cutoff("2028-08-31T12:00:00Z"), "2028-02-29T00:00:00Z")   # leap year

    def test_dataset_last_bar_is_the_latest_bar_across_series(self):
        fake = {("A", "15m"): [{"time": "2026-09-10T23:45:00Z"}], ("B", "15m"): [{"time": "2026-09-11T05:45:00Z"}],
                ("A", "1H"): [{"time": "2026-09-11T05:00:00Z"}]}
        with mock.patch.object(SR.bt, "load", lambda s, t: (fake.get((s, t)), "x")):
            last, present = SR.dataset_last_bar(["A", "B"], ["15m", "1H"])
        self.assertEqual(last, "2026-09-11T05:45:00Z")
        self.assertEqual(sorted(present), [("A", "15m"), ("A", "1H"), ("B", "15m")])   # B 1H absent, not invented

    def test_moving_the_data_moves_the_cutoff(self):
        with mock.patch.object(SR.bt, "load", lambda s, t: ([{"time": "2027-01-31T00:00:00Z"}], "x")):
            last, _ = SR.dataset_last_bar(["A"], ["4H"])
        self.assertEqual(SR.oos_cutoff(last), "2026-07-31T00:00:00Z")

    def test_regenerated_stability_files_carry_a_cutoff_matching_their_own_data(self):
        """Every non-legacy stability file: `oos_holdout.cutoff` == oos_cutoff(its dataset_last_bar), every row
        was split at it, and the last bar is the real last bar of the history files it read."""
        files = sorted(glob.glob(os.path.join(ROOT, "data", "history", "stability", "*.json")))
        self.assertTrue(files)
        for p in files:
            d = json.load(open(p, encoding="utf-8"))
            h = d.get("oos_holdout")
            self.assertIsNotNone(h, f"{p} has no oos_holdout block -- not regenerated by round 4b")
            self.assertEqual(h["cutoff"], SR.oos_cutoff(h["dataset_last_bar"]), p)
            self.assertEqual({r["oos6m"]["cutoff"] for r in d["rows"]}, {h["cutoff"]}, p)
            present = d["dataset_snapshot"].get("series") or []
            lasts = []
            for s in present:
                c = json.load(open(os.path.join(ROOT, "data", "history", f"ohlcv.{s['symbol']}.{s['timeframe']}.json")))["candles"]
                lasts.append(c[-1]["time"])
            self.assertTrue(lasts, f"{p}: no dataset snapshot series")
            self.assertEqual(max(lasts), h["dataset_last_bar"], p)


class OldModeSelectedOnTheHoldout(unittest.TestCase):
    """PRE_ROUND4B's `--window 1y` ranked on `w1y`, the LAST 365 days -- a window that contains the months the
    pick is then reported on. Pinned to c86c8e4, never HEAD."""

    def _old_rank(self):
        src = subprocess.check_output(["git", "show", f"{PRE_ROUND4B}:scripts/rank-setups.py"], cwd=ROOT, text=True)
        tree = ast.parse(src)
        wanted = {"solvent", "rank", "_num", "_pass_estimate", "prop_key"}
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        body += [n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "MIN_WINDOW_DAYS" for t in n.targets)]
        self.assertEqual({n.name for n in body if isinstance(n, ast.FunctionDef)}, wanted)
        ns = {"datetime": datetime}
        exec(compile(ast.Module(body=body, type_ignores=[]), f"{PRE_ROUND4B}:scripts/rank-setups.py", "exec"), ns)
        self.assertNotIn("oos6m", src)                         # the mode did not exist
        return ns["rank"]

    def test_old_pick_flips_when_only_the_holdout_changes(self):
        old_rank = self._old_rank()
        def w(q_pos, ann):
            return dict(n=40, ann=ann, ruin=None, q_pos=q_pos, q_worst=-1.0, dd=3.0, final=10500.0, since="2025-09-11")
        a1 = row(cfg="A", w1y=w(100.0, 20.0)); b1 = row(cfg="B", w1y=w(50.0, 10.0))
        self.assertIs(old_rank([a1, b1], 20, "1y")[0], a1)
        # Only the post-cutoff months of A get worse; its w1y (which INCLUDES them) drops, and the old mode
        # switches its pick -- selection was being made on the very months the pick is judged on.
        a2 = row(cfg="A", w1y=w(25.0, 2.0)); b2 = row(cfg="B", w1y=w(50.0, 10.0))
        self.assertIs(old_rank([a2, b2], 20, "1y")[0], b2)
        # The replacement (ADR 0008 criteria on IS AND OOS, no ranking) is pinned in test_audit_round4c_selection.py.


class SplitRefusals(unittest.TestCase):
    """The split guards survive ADR 0008 unchanged (the per-slot selection they fed was removed)."""

    def test_file_without_split_is_refused(self):
        r = row(); r.pop("oos6m")
        with self.assertRaises(SystemExit):
            RS.require_oos_blocks([r])

    def test_mixed_cutoffs_refused(self):
        a, b = row(), row(cfg="B"); b["oos6m"] = dict(b["oos6m"], cutoff="2026-03-18T00:00:00Z")
        with self.assertRaises(SystemExit):
            RS.market_cutoff([a, b], "crypto")


class DefaultPathUsesOos(unittest.TestCase):
    def test_automation_on_has_no_window_selector_and_selection_reads_the_oos_split(self):
        """Round 4b made oos6m the default; ADR 0008 made it the ONLY input -- there is no window flag left to pick."""
        src = open(os.path.join(ROOT, "scripts", "automation.py"), encoding="utf-8").read()
        self.assertNotIn('"--window"', src)
        rs_src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertIn('o.get("oos")', rs_src); self.assertIn('o.get("in_sample")', rs_src)


if __name__ == "__main__":
    unittest.main()


class MonthlyBlockForSelectionCriteria(unittest.TestCase):
    """ADR 0008: the selection gate reads calendar-month returns per window; a no-trade month is 0%, not missing."""

    @classmethod
    def setUpClass(cls):
        import importlib.util, os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stability-report.py")
        spec = importlib.util.spec_from_file_location("stability_report_mb", p)
        cls.sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.sr)
        cls.START = cls.sr.bt.START

    def test_a_month_with_no_trade_is_a_zero_month(self):
        S = self.START
        curve = [("2026-01-10T00:00:00Z", S * 1.10), ("2026-03-05T00:00:00Z", S * 1.10 * 0.95)]
        b = self.sr.monthly_block(curve, "2026-01-01T00:00:00Z", "2026-03-31T00:00:00Z", S * 1.10 * 0.95)
        self.assertEqual([m["month"] for m in b["months"]], ["2026-01", "2026-02", "2026-03"])
        self.assertAlmostEqual(b["months"][1]["ret_pct"], 0.0)
        self.assertAlmostEqual(b["months"][0]["ret_pct"], 10.0, places=6)
        self.assertAlmostEqual(b["months"][2]["ret_pct"], -5.0, places=6)
        self.assertEqual(b["m_losing"], 1)
        self.assertAlmostEqual(b["m_worst"], -5.0, places=6)

    def test_partial_first_and_last_months_are_flagged(self):
        S = self.START
        b = self.sr.monthly_block([], "2026-03-11T00:00:00Z", "2026-09-11T00:00:00Z", S)
        self.assertTrue(b["months"][0]["partial"]); self.assertTrue(b["months"][-1]["partial"])
        self.assertNotIn("partial", b["months"][1])
        self.assertEqual(len(b["months"]), 7)
        self.assertAlmostEqual(b["m_mean_geo"], 0.0)

    def test_geometric_mean_matches_compounded_window_return(self):
        S = self.START
        final = S * 1.05 ** 6
        b = self.sr.monthly_block([("2026-06-30T00:00:00Z", final)], "2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z", final)
        self.assertAlmostEqual(b["m_mean_geo"], 5.0, delta=0.1)
