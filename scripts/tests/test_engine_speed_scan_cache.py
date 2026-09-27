"""engine-speed branch: scripts/stability-report.py's bt.scan() memoization + parallel pre-computation.

The FIRST cut of `_SCAN_RELEVANT_KEYS` omitted `mgmt` on the belief that scan() never reads it (mgmt reads
like a simulate()-only trade-management knob). The acceptance run against the unmodified engine (D:/tmp-tests/
speed/accept.log) caught this immediately: `walk()` -- called from INSIDE scan(), both for the
WYCKOFF-BOOK/COMBINED-BOOK leg and from ict_setups_live() -- applies config B/C's breakeven-at-+1R rule to the
bar-by-bar outcome (backtest-methods.py:364), so a trade's R/outcome/exit_time already differ before the
record ever reaches simulate(). `_SCAN_RELEVANT_KEYS` now includes `mgmt`, and for CONFIGS' actual three rows
(A: mgmt=none/htf=False, B: mgmt=be/htf=False, C: mgmt=be/htf=True) no two configs share a full key -- the
build_scan_tasks() dedup is correct, general-purpose infrastructure that happens to be a no-op for these three
specific rows; the real, unaffected speed win is the parallel pool across the three distinct scans. This file
tests the pieces that make the call site correct AND pins the corrected (mgmt matters) behaviour so a future
edit cannot silently reintroduce the dropped-`mgmt` bug:

  * `config_opts()` builds the SAME overlay the old inline `bt.OPTS.update(...)` call used to construct by hand
  * `_scan_cache_key()` gives every one of CONFIGS' three real rows its OWN key (mgmt now included) -- and,
    separately, proves the underlying MECHANISM (two overlays that genuinely agree on every relevant key DO
    collapse) using a synthetic overlay pair, so the dedup logic itself stays covered even though it happens
    not to fire for the shipped CONFIGS values today
  * `build_scan_tasks()` is a pure function: same inputs, same deterministic task list, zero scans dispatched
  * `run_scans()` merges results by the KEY captured at submission time, not by completion order -- exercised
    with a deliberately out-of-order ThreadPoolExecutor stand-in so a fast task finishing after a slow one
    cannot land under the wrong key
  * `run_scans()` RETRIES a task that raised (BrokenProcessPool or an ordinary worker exception) against a
    fresh pool, up to `max_retries` times, leaving already-succeeded sibling tasks alone -- fix round 1, after
    a real segfault took down a 27-task run mid-flight (D:/tmp-tests/speed-full/run.attempt1.log)
  * `_worker_scan()` calls bt.scan() with `opts=`, never touching the module-global bt.OPTS, and suppresses
    the "DATA-QUALITY FLAG ..." line a worker's own bt.load() would otherwise reprint (fix round 1: the main
    process's dataset_last_bar() already printed it once -- see that function's own docstring for the
    invariant) while passing any OTHER stderr line through unchanged

No history file is read and no real scan() runs in this file -- bt.scan is monkeypatched throughout, so this
is a fast, hermetic test of the call-site plumbing, not of scan()'s own trade-detection logic (that is
scan()/ict_setups_live()'s own test files' job).
"""
import concurrent.futures
import concurrent.futures.process
import contextlib
import functools
import importlib.util
import io
import os
import sys
import time
import unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SR = _load("stability_report_speedtest", "stability-report.py")


class ConfigOptsMatchesConfigsShape(unittest.TestCase):
    def test_every_scan_relevant_key_is_present(self):
        """A KeyError here means a future scan()-relevant OPTS key was added to backtest-methods.py but not
        threaded into config_opts()'s overlay -- exactly the failure _SCAN_RELEVANT_KEYS' docstring warns
        about, caught at import/test time instead of silently mis-caching a real run."""
        overlay = SR.config_opts(SR.CONFIGS["A"], "range")
        for k in SR._SCAN_RELEVANT_KEYS:
            self.assertIn(k, overlay)

    def test_htf_and_mgmt_come_from_the_config(self):
        overlay = SR.config_opts(SR.CONFIGS["C"], "range")
        self.assertTrue(overlay["htf"])
        self.assertEqual(overlay["mgmt"], "be")
        overlay_a = SR.config_opts(SR.CONFIGS["A"], "range")
        self.assertFalse(overlay_a["htf"])
        self.assertEqual(overlay_a["mgmt"], "none")


class ScanCacheKeyCollapsesEquivalentConfigs(unittest.TestCase):
    """The dedup mechanism, checked against the REAL CONFIGS dict (where it currently never fires -- see
    module docstring) AND against a synthetic pair that genuinely agrees on every relevant key (so the
    mechanism itself stays covered)."""

    def setUp(self):
        self.overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        self.methods = ("wyckoff", "ict")

    def test_every_real_config_pair_has_its_own_key(self):
        """CONFIGS' A/B/C differ in (mgmt, htf) pairwise (A: none/False, B: be/False, C: be/True) -- mgmt
        matters to scan() via walk()'s breakeven rule (backtest-methods.py:364), so none of the three may
        collide. A regression here (two configs colliding again) is exactly the bug the acceptance run caught
        during development."""
        keys = {c: SR._scan_cache_key("BTCUSDT", "1H", self.overlays[c], self.methods) for c in SR.CONFIGS}
        self.assertEqual(len(keys), len(set(keys.values())), f"expected 3 distinct keys, got {keys}")

    def test_two_overlays_agreeing_on_every_relevant_key_do_collapse(self):
        """The dedup MECHANISM itself: an overlay differing from A only in a key scan() never reads (here,
        `combined_entry`, a dead/simulate()-only key -- see _SCAN_RELEVANT_KEYS' docstring) must still share
        A's cache key. This is what build_scan_tasks() relies on to collapse two configs WHEN they genuinely
        agree on every relevant key; CONFIGS' shipped rows just do not happen to, today."""
        overlay_a = self.overlays["A"]
        overlay_a_prime = dict(overlay_a, combined_entry="hindsight")  # scan()-irrelevant key changed only
        key_a = SR._scan_cache_key("BTCUSDT", "1H", overlay_a, self.methods)
        key_a_prime = SR._scan_cache_key("BTCUSDT", "1H", overlay_a_prime, self.methods)
        self.assertEqual(key_a, key_a_prime)

    def test_mgmt_alone_changes_the_key(self):
        overlay_a = self.overlays["A"]
        overlay_be = dict(overlay_a, mgmt="be")
        self.assertNotEqual(SR._scan_cache_key("BTCUSDT", "1H", overlay_a, self.methods),
                            SR._scan_cache_key("BTCUSDT", "1H", overlay_be, self.methods))

    def test_key_varies_by_symbol_timeframe_and_methods(self):
        base = SR._scan_cache_key("BTCUSDT", "1H", self.overlays["A"], self.methods)
        self.assertNotEqual(base, SR._scan_cache_key("ETHUSDT", "1H", self.overlays["A"], self.methods))
        self.assertNotEqual(base, SR._scan_cache_key("BTCUSDT", "4H", self.overlays["A"], self.methods))
        self.assertNotEqual(base, SR._scan_cache_key("BTCUSDT", "1H", self.overlays["A"], ("ict",)))

    def test_hashable_converts_lists_only(self):
        self.assertEqual(SR._hashable([1, 2, 3]), (1, 2, 3))
        self.assertEqual(SR._hashable((1, 2, 3)), (1, 2, 3))
        self.assertEqual(SR._hashable("book"), "book")
        self.assertIsNone(SR._hashable(None))


class BuildScanTasksIsPureAndDeduped(unittest.TestCase):
    def test_three_configs_one_symbol_currently_stay_three_tasks(self):
        """Pinned to CONFIGS' actual, current values: A/B/C disagree on (mgmt, htf) pairwise, so all three
        need their own scan -- see module docstring for why this is not a dedup failure."""
        cfg_overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        methods_by_sym = {"BTCUSDT": ("wyckoff", "ict")}
        tasks = SR.build_scan_tasks(["1H"], ["BTCUSDT"], cfg_overlays, methods_by_sym)
        self.assertEqual(len(tasks), 3)
        keys = [t[3] for t in tasks]
        self.assertEqual(len(keys), len(set(keys)), "build_scan_tasks must not emit duplicate keys")

    def test_two_configs_that_genuinely_agree_do_collapse(self):
        """Uses a synthetic third overlay (not CONFIGS) that agrees with A on every scan()-relevant key, to
        prove the dedup mechanism itself still collapses when its precondition actually holds."""
        cfg_overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        cfg_overlays["A2"] = dict(cfg_overlays["A"], combined_entry="hindsight")  # scan()-irrelevant tweak
        methods_by_sym = {"BTCUSDT": ("wyckoff", "ict")}
        tasks = SR.build_scan_tasks(["1H"], ["BTCUSDT"], cfg_overlays, methods_by_sym)
        # A and A2 collapse to one task; B and C each keep their own -- 3 distinct scans for 4 configs.
        self.assertEqual(len(tasks), 3)

    def test_two_symbols_two_timeframes_three_configs(self):
        cfg_overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        methods_by_sym = {"BTCUSDT": ("wyckoff", "ict"), "ETHUSDT": ("wyckoff", "ict")}
        tasks = SR.build_scan_tasks(["1H", "4H"], ["BTCUSDT", "ETHUSDT"], cfg_overlays, methods_by_sym)
        # 2 tf x 3 configs (none collapse for the real CONFIGS values) x 2 symbols = 12.
        self.assertEqual(len(tasks), 12)

    def test_deterministic_across_calls(self):
        cfg_overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        methods_by_sym = {"BTCUSDT": ("wyckoff", "ict"), "ETHUSDT": ("wyckoff", "ict")}
        t1 = SR.build_scan_tasks(["1H", "4H"], ["BTCUSDT", "ETHUSDT"], cfg_overlays, methods_by_sym)
        t2 = SR.build_scan_tasks(["1H", "4H"], ["BTCUSDT", "ETHUSDT"], cfg_overlays, methods_by_sym)
        self.assertEqual(t1, t2)

    def test_pure_no_scan_dispatched(self):
        """build_scan_tasks must not itself call bt.scan() -- it only plans the work."""
        cfg_overlays = {c: SR.config_opts(cfg, "range") for c, cfg in SR.CONFIGS.items()}
        methods_by_sym = {"BTCUSDT": ("wyckoff", "ict")}
        with mock.patch.object(SR.bt, "scan", side_effect=AssertionError("must not be called")) as m:
            SR.build_scan_tasks(["1H"], ["BTCUSDT"], cfg_overlays, methods_by_sym)
            m.assert_not_called()


class RunScansMergesByKeyNotOrder(unittest.TestCase):
    """The pool-merge-order property: a task submitted FIRST but finishing LAST must still land under its own
    key, never under a faster task's key. ThreadPoolExecutor stands in for ProcessPoolExecutor here (same
    Future/submit interface, no OS process spawn, so the test is fast and deterministic) -- run_scans()
    accepts `executor_cls` for exactly this."""

    def test_sequential_path_calls_scan_with_opts(self):
        calls = []

        def fake_scan(sym, tf, opts=None, only=None):
            calls.append((sym, tf, opts))
            return {"symbol": sym, "tf": tf, "trades": {}}

        with mock.patch.object(SR.bt, "scan", side_effect=fake_scan):
            tasks = [("BTCUSDT", "1H", {"htf": False}, ("BTCUSDT", "1H", False)),
                     ("BTCUSDT", "1H", {"htf": True}, ("BTCUSDT", "1H", True))]
            cache = SR.run_scans(tasks, workers=1)
        self.assertEqual(len(calls), 2)
        for sym, tf, opts in calls:
            self.assertIsNotNone(opts)  # every call isolated via opts=, never bare bt.scan(sym, tf)
        self.assertEqual(set(cache), {("BTCUSDT", "1H", False), ("BTCUSDT", "1H", True)})

    def test_out_of_order_completion_still_merges_correctly(self):
        # Task 0 ("slow") is submitted first but finishes LAST; task 1 ("fast") is submitted second but
        # finishes FIRST. A position-based or completion-order-based merge would swap their results.
        def slow_worker(sym, tf, overlay):
            time.sleep(0.15)
            return {"symbol": sym, "tf": tf, "marker": "slow-result"}

        def fast_worker(sym, tf, overlay):
            return {"symbol": sym, "tf": tf, "marker": "fast-result"}

        tasks = [("BTCUSDT", "1H", {"tag": "slow"}, "key-slow"),
                 ("ETHUSDT", "1H", {"tag": "fast"}, "key-fast")]

        def dispatch(sym, tf, overlay):
            return (slow_worker if overlay.get("tag") == "slow" else fast_worker)(sym, tf, overlay)

        with mock.patch.object(SR, "_worker_scan", side_effect=dispatch):
            cache = SR.run_scans(tasks, workers=2, executor_cls=concurrent.futures.ThreadPoolExecutor)
        self.assertEqual(cache["key-slow"]["marker"], "slow-result")
        self.assertEqual(cache["key-fast"]["marker"], "fast-result")

    def test_single_task_never_uses_the_pool(self):
        """workers>1 with exactly one task must take the sequential branch (run_scans' own guard,
        `len(tasks) > 1`) -- a one-task run should never pay pool-startup cost."""
        with mock.patch.object(SR.bt, "scan", return_value={"trades": {}}) as scan_mock:
            tasks = [("BTCUSDT", "1H", {"htf": False}, "only-key")]
            cache = SR.run_scans(tasks, workers=4)
        scan_mock.assert_called_once_with("BTCUSDT", "1H", opts={"htf": False})
        self.assertIn("only-key", cache)


class WorkerScanIsOptsIsolated(unittest.TestCase):
    def test_worker_scan_passes_opts_never_mutates_global_opts(self):
        before = dict(SR.bt.OPTS)
        with mock.patch.object(SR.bt, "scan", return_value={"trades": {}}) as scan_mock:
            SR._worker_scan("BTCUSDT", "1H", {"htf": True, "sides": ("long", "short")})
        scan_mock.assert_called_once_with("BTCUSDT", "1H", opts={"htf": True, "sides": ("long", "short")})
        self.assertEqual(before, dict(SR.bt.OPTS))


class WorkerScanSuppressesDuplicateQualityFlag(unittest.TestCase):
    """Fix round 1: baseline (one sequential process) prints "DATA-QUALITY FLAG ..." exactly once per
    (sym, tf); before this fix, every worker re-ran bt.load()'s §20/§38 assessment fresh (empty bt._ASSESSED
    in its own process) and reprinted it -- 4 lines instead of 1 for crypto_1h_noacct's 3-config run
    (D:/tmp-tests/speed/accept.log). See dataset_last_bar()'s and _worker_scan()'s own docstrings for the
    invariant that makes suppressing the PRINT (not the assessment) safe."""

    def test_data_quality_flag_lines_are_suppressed_other_lines_pass_through(self):
        def fake_scan(sym, tf, opts=None):
            print("DATA-QUALITY FLAG (CLAUDE.md §20/§38): BTCUSDT 1H history is PARTIAL: 1 bar(s) missing",
                  file=sys.stderr)
            print("some unrelated stderr line", file=sys.stderr)
            return {"trades": {}}

        captured = io.StringIO()
        with mock.patch.object(SR.bt, "scan", side_effect=fake_scan):
            with contextlib.redirect_stderr(captured):
                SR._worker_scan("BTCUSDT", "1H", {})
        out = captured.getvalue()
        self.assertNotIn("DATA-QUALITY FLAG", out)
        self.assertIn("some unrelated stderr line", out)

    def test_no_stderr_output_is_fine_too(self):
        with mock.patch.object(SR.bt, "scan", return_value={"trades": {}}):
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                result = SR._worker_scan("BTCUSDT", "1H", {})
        self.assertEqual(result, ({"trades": {}}, []))
        self.assertEqual(captured.getvalue(), "")


class _FlakyExecutor:
    """Stand-in for ProcessPoolExecutor exercising run_scans()'s retry path (fix round 1, after a real
    segfault took down a 27-task run mid-flight: D:/tmp-tests/speed-full/run.attempt1.log). `fail_counts` maps
    (sym, tf) -> how many times submitting that task should raise a simulated BrokenProcessPool before it
    succeeds. A plain dict passed in by the test and mutated IN PLACE, so the remaining-failure count persists
    correctly across run_scans() recreating a fresh executor instance each retry round -- exactly mirroring
    why a real broken pool cannot simply be reused."""

    def __init__(self, fail_counts, max_workers=None):
        self.fail_counts = fail_counts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def submit(self, fn, sym, tf, overlay):
        fut = concurrent.futures.Future()
        key = (sym, tf)
        if self.fail_counts.get(key, 0) > 0:
            self.fail_counts[key] -= 1
            fut.set_exception(concurrent.futures.process.BrokenProcessPool("simulated dead worker"))
        else:
            fut.set_result(fn(sym, tf, overlay))
        return fut


class RunScansRetriesOnFailure(unittest.TestCase):
    def test_retries_and_recovers_within_budget(self):
        fail_counts = {("BTCUSDT", "1H"): 1}  # fails once, succeeds on the 1st retry
        factory = functools.partial(_FlakyExecutor, fail_counts)
        with mock.patch.object(SR, "_worker_scan", side_effect=lambda sym, tf, overlay: {"symbol": sym, "tf": tf}):
            tasks = [("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")]
            cache = SR.run_scans(tasks, workers=2, executor_cls=factory)
        self.assertEqual(cache["k1"], {"symbol": "BTCUSDT", "tf": "1H"})
        self.assertEqual(cache["k2"], {"symbol": "ETHUSDT", "tf": "1H"})

    def test_a_genuinely_successful_sibling_task_is_not_recomputed(self):
        """Only the task WITHOUT a result is resubmitted -- a sibling that already succeeded must not be
        recomputed (bt.scan() is exactly the expensive call this optimization exists to avoid repeating)."""
        fail_counts = {("BTCUSDT", "1H"): 1}
        factory = functools.partial(_FlakyExecutor, fail_counts)
        calls = []

        def recording_worker(sym, tf, overlay):
            calls.append((sym, tf))
            return {"symbol": sym}

        with mock.patch.object(SR, "_worker_scan", side_effect=recording_worker):
            tasks = [("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")]
            SR.run_scans(tasks, workers=2, executor_cls=factory)
        self.assertEqual(calls.count(("ETHUSDT", "1H")), 1)
        self.assertEqual(calls.count(("BTCUSDT", "1H")), 1)

    def test_logs_each_retry_to_stderr(self):
        fail_counts = {("BTCUSDT", "1H"): 1}
        factory = functools.partial(_FlakyExecutor, fail_counts)
        captured = io.StringIO()
        with mock.patch.object(SR, "_worker_scan", side_effect=lambda sym, tf, overlay: {"symbol": sym}):
            with contextlib.redirect_stderr(captured):
                SR.run_scans([("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")], workers=2,
                            executor_cls=factory)
        self.assertIn("retrying", captured.getvalue())
        self.assertIn("BTCUSDT", captured.getvalue())

    def test_succeeds_exactly_at_the_retry_boundary(self):
        fail_counts = {("BTCUSDT", "1H"): 2}  # fails twice; the 3rd attempt (1 + max_retries=2) succeeds
        factory = functools.partial(_FlakyExecutor, fail_counts)
        with mock.patch.object(SR, "_worker_scan", side_effect=lambda sym, tf, overlay: {"symbol": sym}):
            tasks = [("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")]
            cache = SR.run_scans(tasks, workers=2, executor_cls=factory, max_retries=2)
        self.assertIn("k1", cache)

    def test_exceeds_retry_budget_fails_loudly(self):
        fail_counts = {("BTCUSDT", "1H"): 99}  # never succeeds
        factory = functools.partial(_FlakyExecutor, fail_counts)
        with mock.patch.object(SR, "_worker_scan", side_effect=lambda sym, tf, overlay: {"symbol": sym}):
            tasks = [("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")]
            with self.assertRaises(concurrent.futures.process.BrokenProcessPool):
                SR.run_scans(tasks, workers=2, executor_cls=factory, max_retries=2)

    def test_sequential_fallback_also_retries(self):
        """When only one task remains (or workers==1), run_scans() takes the sequential bt.scan() branch --
        that branch must retry too, not just the pooled one."""
        attempts = {"n": 0}

        def flaky_scan(sym, tf, opts=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("simulated transient failure")
            return {"trades": {}}

        with mock.patch.object(SR.bt, "scan", side_effect=flaky_scan):
            tasks = [("BTCUSDT", "1H", {}, "k1")]
            cache = SR.run_scans(tasks, workers=1)
        self.assertIn("k1", cache)
        self.assertEqual(attempts["n"], 2)


class WorkerScanReportsEveryLoadForReplay(unittest.TestCase):
    """The §38 half of the parallel path: a series a scan loads ON ITS OWN (e.g. the HTF companion) must be
    reported back so the main process can replay its bt.load() -- otherwise its quality flag would exist only
    in a worker's discarded memory and the run's verdict would read clean."""

    def test_loads_are_reported_once_in_first_call_order_and_bt_load_is_restored(self):
        real = SR.bt.load

        def fake_scan(sym, tf, opts=None):
            SR.bt.load(sym, tf); SR.bt.load(sym, "4H"); SR.bt.load(sym, tf)
            return {"trades": {}}

        with mock.patch.object(SR.bt, "scan", side_effect=fake_scan), \
                mock.patch.object(SR.bt, "_read_history", return_value={"candles": []}), \
                mock.patch.object(SR.bt.os.path, "exists", return_value=True):
            _result, loads = SR._worker_scan("BTCUSDT", "1H", {})
        self.assertEqual(loads, [("BTCUSDT", "1H"), ("BTCUSDT", "4H")])
        self.assertIs(SR.bt.load, real)

    def test_stderr_printed_before_an_exception_still_surfaces(self):
        def dying_scan(sym, tf, opts=None):
            print("diagnostic line printed BEFORE the crash", file=sys.stderr)
            print("DATA-QUALITY FLAG (CLAUDE.md §20/§38): suppressed as always", file=sys.stderr)
            raise RuntimeError("boom")

        captured = io.StringIO()
        with mock.patch.object(SR.bt, "scan", side_effect=dying_scan), contextlib.redirect_stderr(captured):
            with self.assertRaises(RuntimeError):
                SR._worker_scan("BTCUSDT", "1H", {})
        self.assertIn("diagnostic line printed BEFORE the crash", captured.getvalue())
        self.assertNotIn("DATA-QUALITY FLAG", captured.getvalue())

    def test_bt_load_is_restored_even_when_the_scan_raises(self):
        real = SR.bt.load
        with mock.patch.object(SR.bt, "scan", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                SR._worker_scan("BTCUSDT", "1H", {})
        self.assertIs(SR.bt.load, real)


if __name__ == "__main__":
    unittest.main()
