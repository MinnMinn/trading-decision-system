"""1m timeframe params (owner decision 2026-09-29, docs/plans/2026-09-28-methodology-improvement-plan.md §6
item 7): fund setups are now searched on 1m/5m/15m/30m. Several per-timeframe tables on the research/analysis
path had a "5m" row but no "1m" row -- a pre-existing gap this task closes, one table at a time
(docs/architecture/analysis-params.json project_defined.fund_1m_timeframe_params/fund_scan_window_30m record
the project-defined numbers this file pins).

What this file defends, one test class per claim:
  * every per-timeframe table on the research/analysis path that has a "5m" row also has a "1m" row, with the
    OWNER-APPROVED values -- or is explicitly exempted here with a reason (never silently skipped).
  * normalized.available_time() for a 1m bar is open + 60s (it already read automation.TF_MINUTES, which
    already had "1m" -- this pins that it keeps working, not that it was broken).
  * automation.SCAN_WINDOW keeps 1m=360/5m=576 UNCHANGED and gains a 30m=480 entry.
  * a 1m scan against a real (if tiny/possibly-empty) history slice does not raise -- P["1m"] existing is what
    makes scan() reach that code at all; the exact slice this pins is the one named in the task dispatch.

Exempted from the "5m implies 1m" rule, with reasons, rather than silently left out:
  * scripts/strategy-runner.py fetch_candles()'s MT5 branch `{"2H": "1H", "30m": "15m"}.get(tf, tf)` -- the
    MT5 export EA writes 5m/15m/1H/4H/1D/1W natively (comment at that line) and has NO 1m export to aggregate
    from; inventing a 1m aggregation source for CFDs is out of this task's scope (no owner decision, no data).
  * scripts/measure-spring-ict.py's own R/K/H table gains "1m" here (mirrors bt.P["1m"]) but is NOT extended
    with "30m" -- that script is a standalone research tool the plan's fund-search decision never named, and
    inventing 30m R/K/H values for it would be a project parameter nobody approved (CLAUDE.md §57 YAGNI).
"""
import datetime
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N  # noqa: E402

UTC = datetime.timezone.utc


def _load(relpath, name=None, env=None):
    """importlib load of a dashed-filename module, optionally with an env var set for the duration of the
    exec -- backtest-methods.HISTORY_ROOT (and history_store.history_root()) are read at exec time, matching
    the pattern scripts/tests/test_ftmo_history.py and test_prop_search.py already use."""
    old = {}
    try:
        if env:
            for k, v in env.items():
                old[k] = os.environ.get(k)
                os.environ[k] = v
        spec = importlib.util.spec_from_file_location(name or relpath, os.path.join(ROOT, "scripts", relpath))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


FUND_1M = {"R": 60, "K": 20, "T": 24, "H": 144, "sob": 10}   # analysis-params.json project_defined.fund_1m_timeframe_params


class EveryTableWithA5mRowAlsoHasA1mRow(unittest.TestCase):
    """One assertion per table named in the task dispatch, plus the tables the dispatch's own grep found.
    Each check loads the module fresh so this file has no import-order dependency on the others."""

    def test_normalized_snap_to_grid_has_1m(self):
        """The `secs` lookup inside normalized.snap_to_grid() (line ~94) is local, not exported -- tested
        through its behaviour: before this task, ANY "1m" input returned unchanged (secs=None short-circuit)
        regardless of jitter; now a jittered 1m timestamp snaps to the grid exactly like 1H/15m already do."""
        self.assertEqual(N.snap_to_grid("2026-09-18T09:00:01Z", "1m"), "2026-09-18T09:00:00Z")
        self.assertEqual(N.snap_to_grid("2026-09-18T08:59:59Z", "1m"), "2026-09-18T09:00:00Z")
        # outside GRID_TOLERANCE_S (2s): left alone, same as every other timeframe already behaves
        self.assertEqual(N.snap_to_grid("2026-09-18T09:00:05Z", "1m"), "2026-09-18T09:00:05Z")

    def test_backtest_methods_P_has_1m_with_the_approved_values(self):
        bt = _load("backtest-methods.py", "bt_tftables")
        self.assertIn("1m", bt.P)
        self.assertEqual(bt.P["1m"], FUND_1M)

    def test_backtest_methods_rungs_has_1m_and_its_htf_is_5m(self):
        bt = _load("backtest-methods.py", "bt_tftables2")
        self.assertIn("1m", bt._RUNGS)
        self.assertEqual(bt.HTF_OF.get("1m"), "5m")

    def test_measure_spring_ict_P_has_1m(self):
        m = _load("measure-spring-ict.py", "msi_tftables")
        self.assertIn("1m", m.P)
        self.assertEqual(m.P["1m"], {"R": 60, "K": 20, "H": 144})

    def test_event_ledger_TF_SEC_has_1m(self):
        el = _load("event-ledger.py", "el_tftables")
        self.assertIn("1m", el.TF_SEC)
        self.assertEqual(el.TF_SEC["1m"], 60)

    def test_strategy_runner_RUNNER_TFS_and_TF_SEC_have_1m(self):
        sr = _load("strategy-runner.py", "sr_tftables")
        self.assertIn("1m", sr.RUNNER_TFS)
        self.assertIn("1m", sr.TF_SEC)
        self.assertEqual(sr.TF_SEC["1m"], 60)
        # due()'s fast-tick whitelist: a 1m setup must be evaluated every tick, same as 5m/15m/30m already are.
        # This does NOT enable live 1m trading by itself -- load_setups() (docs/architecture/pilot-selection.json)
        # is the one gate on what actually runs, and this task does not touch that file.
        self.assertTrue(sr.due("1m", datetime.datetime(2026, 1, 1, 0, 1, tzinfo=UTC)))

    def test_feed_health_and_fetch_history_and_build_artifact_already_had_1m(self):
        """Not a fix -- a guard against regression. These three already carried "1m" before this task
        (task dispatch context); pinned here so the "every 5m table has 1m" claim covers the whole grep, not
        just the tables this task edited."""
        fh = _load("feed_health.py", "fh_tftables")
        self.assertIn("1m", fh.TF_SECONDS)
        fetch = _load("fetch-history.py", "fetch_tftables")
        self.assertIn("1m", fetch.INTERVAL)
        self.assertIn("1m", fetch.MS)
        ba = _load("build-artifact.py", "ba_tftables")
        self.assertIn("1m", ba.TF_MIN)
        self.assertIn("1m", ba.TF_SPEC)
        self.assertIn("1m", ba.TF_LABEL)


class AvailableTimeFor1mIsOpenPlus60Seconds(unittest.TestCase):
    def test_available_time_1m(self):
        candle = {"time": "2026-01-01T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1}
        got = N.available_time(candle, "1m")
        want = datetime.datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
        self.assertEqual(got, want)


class ScanWindowUnchangedFor1mAnd5mNewFor30m(unittest.TestCase):
    def setUp(self):
        self.a = _load("automation.py", "auto_tftables")

    def test_1m_and_5m_unchanged(self):
        self.assertEqual(self.a.SCAN_WINDOW["1m"], {"bars": 360, "recent": 4})
        self.assertEqual(self.a.SCAN_WINDOW["5m"], {"bars": 576, "recent": 4})

    def test_30m_added(self):
        self.assertEqual(self.a.SCAN_WINDOW["30m"], {"bars": 480, "recent": 2})

    def test_live_rules_scan_spec_reads_the_same_30m_entry(self):
        lr = _load("live_rules.py", "lr_tftables")
        self.assertEqual(lr.scan_spec("30m"), (480, 2))


class OneMinuteScanAgainstFtmoHistoryDoesNotRaise(unittest.TestCase):
    """CLAUDE.md §55 adversarial-testing spirit: prove bt.scan(sym, "1m", ...) does not crash, including the
    literal small/possibly-empty slice named in the task dispatch (BT_HISTORY_ROOT=data/history/ftmo,
    pit_cutoff("2020-01-02T00:00:00Z"), a small limit_bars) -- and, for real confidence that P["1m"]'s
    R/K/T/H/sob actually work (not just "scan() returned None before touching them"), a second, denser slice
    that exercises the engine on real 1m bars."""

    FTMO_ROOT = os.path.join(ROOT, "data", "history", "ftmo")

    def setUp(self):
        if not os.path.isdir(self.FTMO_ROOT):
            self.skipTest("data/history/ftmo not present in this checkout (uncommitted local import)")

    def _bt(self):
        return _load("backtest-methods.py", "bt_ftmo_1m_scan", env={"BT_HISTORY_ROOT": self.FTMO_ROOT})

    def test_tiny_slice_named_in_the_dispatch_does_not_raise(self):
        bt = self._bt()
        bt.limit_bars(300)
        bt.pit_cutoff("2020-01-02T00:00:00Z")
        try:
            result = bt.scan("US30", "1m")
        except Exception as exc:  # pragma: no cover - the whole point of this test is that this does NOT fire
            self.fail(f"bt.scan('US30', '1m') raised {exc!r} on a tiny/possibly-empty 1m slice")
        # This exact combination (a small tail of the FULL merged history, then filtered to before 2020-01-02)
        # is expected to leave few or zero candles -- None (scan()'s own "no data" return) is a legitimate,
        # non-crashing result here, not a test failure.
        self.assertIsInstance(result, (dict, type(None)))

    def test_a_denser_1m_slice_actually_scans(self):
        bt = self._bt()
        # `limit_bars` trims the TAIL of the full merged multi-year series (before any pit_cutoff is applied
        # -- see load()'s own ordering), so leaving pit_cutoff unset and only capping bars keeps the most
        # recent (dense) end of the real US30 1m history -- unlike the tiny-slice test above, which combines
        # both and is expected to land on a thin/empty edge.
        direct, _src = bt.load("US30", "1m")
        if not direct:
            self.skipTest("no US30 1m under data/history/ftmo")
        bt.limit_bars(400)
        result = bt.scan("US30", "1m", only=("ICT",))
        self.assertIsNotNone(result, "a 400-bar real 1m slice must not come back empty")
        self.assertIn("trades", result)
        self.assertIn("ICT", result["trades"])


if __name__ == "__main__":
    unittest.main()
