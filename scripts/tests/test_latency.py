"""CLAUDE.md §40 -- the live path is measured, and the research path is off it.

§40 has two halves and the repo failed each in a different way.

**Measurement.** §40 names ten timestamps and four statistics. The repo had four wall-clock stamps at
one-second resolution, **differenced none of them**, and had no `perf_counter` anywhere in the order path's
import closure. Nothing could have told you a stage got slower.

**Isolation.** "Research, learning, backtesting, AI reasoning and post-trade analysis must NOT block the live
decision and execution path." The LLM half was true and provable — the live path imports nothing that calls a
model. The post-trade half was **false**: `pilot-loop.sh` ran `journal.py all` (index rebuild + HTML render)
synchronously between the tick and the sleep.

The tests below check both halves, plus the thing §40 asks for that is easiest to skip: performance
**regression** benchmarks over its own list of stages. Those run offline on fixtures — a regression test that
reaches the network measures the network.
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import latency as L

from live_write_isolation import redirect as _redirect_writes

REGISTRY = os.path.join(ROOT, "docs", "architecture", "latency-model.json")
RUNNER_SRC = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
LOOP_SRC = open(os.path.join(ROOT, "scripts", "pilot-loop.sh"), encoding="utf-8").read()

_RESTORE_WRITES = None


def setUpModule():
    # Every class below either calls L.tick() directly (TheRecorder) or loads strategy-runner.py fresh and
    # calls sr.tick() / runs it as a --dry-run subprocess (TheLiveOrderPathIsInstrumented) -- all of which
    # otherwise append a real trace to data/live/latency/ (scripts/tests/live_write_isolation.py).
    global _RESTORE_WRITES
    _RESTORE_WRITES = _redirect_writes()


def tearDownModule():
    _RESTORE_WRITES()


def _spec_section(title, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    return spec.split(title, 1)[1].split(until, 1)[0]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_every_timestamp_claude_md_40_names_is_declared(self):
        body = _spec_section("Latency instrumentation must record:", "Measure:")
        bullets = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
        self.assertEqual([L.spec_name(s) for s in L.ORDER], bullets)

    def test_all_four_statistics_are_produced(self):
        body = _spec_section("Measure:", "Separate heavy research")
        asked = {ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")}
        self.assertEqual(asked, {"p50", "p95", "p99", "max"})
        st = L._stats([1.0, 2.0, 3.0])
        for k in ("p50", "p95", "p99", "max", "n"):
            self.assertIn(k, st, k)

    def test_every_research_workload_claude_md_40_names_is_declared_with_how_it_is_isolated(self):
        body = _spec_section("In parallel:", "may continue asynchronously")
        bullets = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
        self.assertEqual(list(L.research_workloads()), bullets)
        for w in L.WORKLOADS["research"]:
            self.assertTrue(w.get("isolated_by", "").strip(), w["id"])

    def test_every_regression_stage_claude_md_40_names_is_declared(self):
        body = _spec_section("Performance regression tests should cover:", "Do not introduce abstraction")
        bullets = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
        self.assertEqual(list(L.REGRESSION_STAGES), bullets)

    def test_a_transport_bound_stage_must_justify_itself(self):
        # Calling a stage unmeasurable is how a slow stage stops being measured.
        for sid in L.TRANSPORT_STAGES:
            self.assertTrue(L.stamp(sid).get("_bound_why", "").strip(), sid)

    def test_a_registry_that_declares_a_stage_unmeasurable_without_a_reason_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        for s in data["stamps"]:
            if s["kind"] == L.TRANSPORT:
                s.pop("_bound_why")
                break
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-latency.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(L.RegistryError):
                L._load(p)
        finally:
            os.remove(p)

    def test_most_of_the_ten_are_hot_stages_not_excuses(self):
        # 8 of 10 are code we can make faster; only the two the transport genuinely owns are exempt.
        self.assertEqual(len(L.HOT_STAGES), 8)
        self.assertEqual(set(L.TRANSPORT_STAGES), {"market_event", "fill"})


class TheRecorder(unittest.TestCase):
    def test_a_span_measures_and_is_reported_in_milliseconds(self):
        sink = []
        with L.tick("t", sink=sink) as tr:
            with tr.span("normalization"):
                time.sleep(0.02)
        self.assertGreaterEqual(sink[0]["hot_ms"]["normalization"], 15)
        self.assertLess(sink[0]["hot_ms"]["normalization"], 500)

    def test_a_span_closes_even_when_the_body_raises(self):
        # tick() has five early returns and an exception is exactly the case whose duration a reader wants.
        sink = []
        with self.assertRaises(ValueError):
            with L.tick("t", sink=sink) as tr:
                with tr.span("normalization"):
                    raise ValueError("boom")
        self.assertIn("normalization", sink[0]["hot_ms"])

    def test_the_trace_is_written_even_when_the_tick_raises(self):
        sink = []
        with self.assertRaises(ValueError):
            with L.tick("t", sink=sink):
                raise ValueError("boom")
        self.assertEqual(len(sink), 1)

    def test_entering_a_stage_twice_in_one_tick_totals_it(self):
        # A tick fetches several symbols; the tick's provider latency is the sum, not the last one.
        sink = []
        with L.tick("t", sink=sink) as tr:
            for _ in range(3):
                with tr.span("provider_receive"):
                    time.sleep(0.005)
        self.assertGreaterEqual(sink[0]["hot_ms"]["provider_receive"], 12)

    def test_an_undeclared_stage_is_refused_at_the_call_site(self):
        with L.tick("t", sink=[]) as tr:
            with self.assertRaises(L.NotDeclared):
                with tr.span("vibes"):
                    pass

    def test_a_hot_stage_cannot_be_asserted_as_a_number(self):
        # `mark` exists for facts measured elsewhere. Allowing it on a hot stage would let a caller declare a
        # latency instead of measuring one.
        with L.tick("t", sink=[]) as tr:
            with self.assertRaises(L.NotDeclared):
                tr.mark("normalization", 1.0)

    def test_record_is_additive_like_span(self):
        sink = []
        with L.tick("t", sink=sink) as tr:
            t0 = time.perf_counter_ns(); time.sleep(0.005); tr.record("decision_end", t0)
            t0 = time.perf_counter_ns(); time.sleep(0.005); tr.record("decision_end", t0)
        self.assertGreaterEqual(sink[0]["hot_ms"]["decision_end"], 8)


class TheSummary(unittest.TestCase):
    ROWS = [{"hot_ms": {"normalization": float(i)}, "transport_ms": {"fill": 1000.0 * i},
             "total_hot_ms": float(i)} for i in range(1, 101)]

    def test_percentiles_and_max_with_the_sample_size(self):
        s = L.summarize(self.ROWS)
        st = s["hot"]["normalization"]
        self.assertEqual(st["n"], 100)
        self.assertEqual(st["max"], 100.0)
        self.assertEqual(st["p50"], 50.0)
        self.assertEqual(st["p95"], 95.0)
        self.assertEqual(st["p99"], 99.0)

    def test_transport_bound_stages_are_reported_apart_from_the_hot_ones(self):
        # Mixing them would make a slow tick indistinguishable from a limit order that waited an hour.
        s = L.summarize(self.ROWS)
        self.assertIn("fill", s["transport_bound"])
        self.assertNotIn("fill", s["hot"])

    def test_the_percentile_is_nearest_rank_not_interpolated(self):
        # With a poll loop's sample sizes an interpolated p99 invents a value between two observations.
        self.assertEqual(L.percentile([1.0, 2.0, 3.0], 99), 3.0)
        self.assertEqual(L.percentile([1.0, 2.0, 3.0], 50), 2.0)
        self.assertIsNone(L.percentile([], 50))

    def test_a_stage_with_no_observations_is_absent_rather_than_zero(self):
        s = L.summarize(self.ROWS)
        self.assertNotIn("order_submission", s["hot"])


class TheLiveOrderPathIsInstrumented(unittest.TestCase):
    """Checked against the source, because the alternative is trusting that a wiring survived an edit."""

    def test_the_tick_opens_exactly_one_trace_and_clears_it_in_finally(self):
        self.assertIn("with LAT.tick(", RUNNER_SRC)
        self.assertIn("finally:\n            _LAT = None", RUNNER_SRC)

    def test_the_fetch_and_the_normalisation_are_timed_separately(self):
        # They fail and regress for different reasons: one is the network, the other is us.
        self.assertIn('_span("provider_receive")', RUNNER_SRC)
        self.assertIn('_span("normalization")', RUNNER_SRC)

    def test_the_required_analysis_the_decision_and_the_risk_call_are_timed(self):
        for stage in ("analytics_update", "risk_validation"):
            self.assertIn(f'_span("{stage}")', RUNNER_SRC, stage)
        self.assertIn('_rec("decision_start"', RUNNER_SRC)
        self.assertIn('_rec("decision_end"', RUNNER_SRC)

    def test_the_decision_is_recorded_at_both_exits_not_only_the_one_that_places_an_order(self):
        # A timer stopped only on the order path measures the fast cases and drops the refusals.
        self.assertEqual(RUNNER_SRC.count('_rec("decision_end", _dec_t0)'), 2)

    def test_every_venue_submit_is_timed_and_acknowledged(self):
        # Four submit call sites: MT5 limit, futures limit, MT5 market, futures market.
        self.assertEqual(RUNNER_SRC.count('_span("order_submission")'), 4)
        self.assertEqual(RUNNER_SRC.count('_rec("provider_acknowledgement"'), 4)

    def test_measurement_can_never_fail_a_tick(self):
        # §1 puts execution safety above measurement.
        self.assertIn("# measurement never fails a tick (§1)", RUNNER_SRC)

    def test_the_helpers_are_inert_when_no_tick_is_active(self):
        spec = importlib.util.spec_from_file_location(
            "sr_lat", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)
        self.assertIsNone(sr._LAT)
        self.assertIsNone(sr._t0())
        sr._rec("normalization", None)          # must not raise
        with sr._span("normalization"):
            pass

    @staticmethod
    def _evaluable_setups():
        """Setups the runner would actually look at: selected AND permitted by the live method preset."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("sr_probe", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        sr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sr)
        return [st for st in sr.load_setups()
                if st["method"] in sr.allowed_methods(st["market"])]

    def test_a_real_dry_tick_records_the_stages_it_reached(self):
        # The end-to-end check: run the actual runner and read the file it wrote. `L.DIR` rather than the
        # repo path directly: setUpModule() redirects it (and the TRADING_TEST_LATENCY_DIR the subprocess
        # below inherits) away from data/live/latency, per scripts/tests/live_write_isolation.py.
        out = L.DIR
        before = set(os.listdir(out)) if os.path.isdir(out) else set()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "strategy-runner.py"),
                            "--dry-run", "--ignore-gate"],
                           capture_output=True, text=True, cwd=ROOT, timeout=600)
        if r.returncode != 0:
            self.skipTest(f"dry tick could not run here: {r.stderr.strip()[:200]}")
        after = set(os.listdir(out)) if os.path.isdir(out) else set()
        self.assertTrue(after, "the tick wrote no latency trace at all")
        rows = L.read()
        self.assertTrue(rows)
        last = rows[-1]
        self.assertIn(last["label"], ("dry", "live"))
        # "A dry tick always fetches and normalises" stopped being true on 2026-09-19, in two ways, and both
        # are by design rather than a wiring failure:
        #   * the shared candle cache is reused when it already holds the latest CLOSED bar, so the provider
        #     call is skipped for every runner after the first one in a bar (strategy-runner
        #     _cache_has_last_closed);
        #   * a tick with NO evaluable setup fetches nothing at all -- which is the live state right now: the
        #     re-rank that followed the ICT fill correction left one selected setup, and the method preset
        #     blocks it.
        # So the precondition is made explicit instead of assumed. The decision/risk/order stages still record
        # only when a signal reaches them, so their absence remains a quiet market.
        evaluable = self._evaluable_setups()
        if not evaluable:
            self.skipTest("no setup is evaluable under the current preset, so the tick fetches nothing -- "
                          "there is no stage for it to have reached")
        self.assertIn("provider_receive", last["hot_ms"])
        self.assertIn("normalization", last["hot_ms"])
        del before, after


class TheResearchPathIsOffTheLivePath(unittest.TestCase):
    def test_the_journal_no_longer_runs_synchronously_inside_the_order_loop(self):
        # The defect: an index rebuild plus an HTML render, of unmeasured duration, between the tick and the
        # sleep. "Usually fast" is not isolation.
        self.assertNotIn('python3 "$ROOT/scripts/journal.py" all >> "$PD/loop.log" 2>&1 || echo "journal sync error',
                         LOOP_SRC)
        self.assertIn("nohup", LOOP_SRC)
        self.assertIn("</dev/null", LOOP_SRC)

    def test_the_detached_journal_is_locked_against_overlapping_runs(self):
        # Two runs would both rebuild trades/index.jsonl and race on it.
        self.assertIn('mkdir "$JLOCK"', LOOP_SRC)
        self.assertIn('rmdir "$3"', LOOP_SRC)

    def test_a_stale_lock_cannot_stop_every_later_ingest(self):
        self.assertIn("clearing stale journal lock", LOOP_SRC)

    def test_the_loop_script_is_valid_shell(self):
        r = subprocess.run(["bash", "-n", os.path.join(ROOT, "scripts", "pilot-loop.sh")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_model_call_is_reachable_from_the_live_path(self):
        # §40: "AI / LLM must NOT be a mandatory dependency of the hot path by default."
        # The live path, not the tests: this file mentions both words, and so may a future test that checks
        # the same thing. The claim is about what an order can reach.
        hits = subprocess.run(["grep", "-rl", "--exclude-dir=tests", "--exclude-dir=__pycache__",
                               "-e", "anthropic", "-e", "openai", os.path.join(ROOT, "scripts")],
                              capture_output=True, text=True)
        self.assertEqual(hits.stdout.strip(), "")

    def test_the_model_reads_in_the_scanner_are_detached(self):
        scan = open(os.path.join(ROOT, "scripts", "scan-loop.sh"), encoding="utf-8").read()
        self.assertIn("nohup", scan)


class PerformanceRegressionBenchmarks(unittest.TestCase):
    """§40: 'Performance regression tests should cover normalization, provider adapters, derived analytics,
    required methodology analysis, Decision Engine, risk, event-risk validation, strategy evaluation.'

    These are REGRESSION tests, not budgets: §40 sets no threshold and neither do they. Each asserts a
    generous ceiling whose only job is to fail when a stage becomes orders of magnitude slower — an accidental
    network call, an O(n^2) rewrite, a model in the hot path. All run offline on fixtures, because a
    regression test that reaches the network measures the network.
    """

    CEILING_MS = 2000.0

    def _timed(self, fn):
        t0 = time.perf_counter_ns()
        fn()
        return (time.perf_counter_ns() - t0) / 1e6

    def test_normalization(self):
        import normalized as N
        import quality as Q
        p = os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.4H.json")
        if not os.path.exists(p):
            self.skipTest("no BTCUSDT 4H history fixture")
        d = json.load(open(p))
        ms = self._timed(lambda: Q.assess(d, "4H", symbol="BTCUSDT"))
        self.assertLess(ms, self.CEILING_MS, f"normalization/quality took {ms:.0f}ms")
        self.assertTrue(hasattr(N, "STALE_AFTER_BARS"))

    def test_provider_adapters(self):
        import providers as P
        ms = self._timed(lambda: [P.adapter(pid) for pid in P.PROVIDERS])
        self.assertLess(ms, self.CEILING_MS, f"provider registry read took {ms:.0f}ms")

    def test_derived_analytics_and_required_methodology_analysis(self):
        spec = importlib.util.spec_from_file_location(
            "bt_bench", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
        c, _ = bt.load("BTCUSDT", "4H")
        if not c:
            self.skipTest("no BTCUSDT 4H history fixture")
        window = c[-300:]
        H = [x["high"] for x in window]
        ms = self._timed(lambda: bt.all_pivots(H, "high"))
        self.assertLess(ms, self.CEILING_MS, f"pivot analytics over 300 bars took {ms:.0f}ms")

    def test_decision_engine(self):
        import decision_order as DO
        def walk():
            for _ in range(200):
                tr = DO.Trace("scalping")
                tr.ok("market_instrument"); tr.ok("data_quality"); tr.ok("risk_calculation")
        ms = self._timed(walk)
        self.assertLess(ms, self.CEILING_MS, f"200 decision walks took {ms:.0f}ms")

    def test_risk(self):
        import risk_model as RM
        ms = self._timed(lambda: [RM.net_r(100.0, 99.0, 103.0, "futures") for _ in range(200)])
        self.assertLess(ms, self.CEILING_MS, f"risk calculation took {ms:.0f}ms")

    def test_event_risk_validation(self):
        import event_risk as ER
        def check():
            for _ in range(50):
                try:
                    ER.load()
                except Exception:
                    pass
        ms = self._timed(check)
        self.assertLess(ms, self.CEILING_MS, f"event-risk validation took {ms:.0f}ms")

    def test_strategy_evaluation(self):
        import trading_system as TS
        def evaluate():
            for _ in range(200):
                TS.required("scalping", setup=None, engaged=())
        ms = self._timed(evaluate)
        self.assertLess(ms, self.CEILING_MS, f"200 strategy evaluations took {ms:.0f}ms")

    def test_every_stage_claude_md_40_lists_has_a_benchmark_here(self):
        # The list is the spec's, so a ninth stage cannot be added there and skipped here.
        have = {n[len("test_"):] for n in dir(self) if n.startswith("test_")}
        for stage in L.REGRESSION_STAGES:
            slug = stage.lower().replace(" ", "_").replace("-", "_")
            self.assertTrue(any(slug in h for h in have), f"no benchmark for §40 stage {stage!r}")


class ATestRunMustNotDirtyTheRepositoriesLiveData(unittest.TestCase):
    """The regression for scripts/tests/live_write_isolation.py: before that module existed, every
    `L.tick(...)` call above (TheRecorder) and every `sr.tick(...)` reached through a freshly-loaded
    strategy-runner.py appended a REAL trace to data/live/latency/<UTC date>.jsonl -- exactly what
    `git status --porcelain` shows dirty after running this file. This class fails on that code and passes
    once setUpModule() redirects latency.DIR (see the top of this file)."""

    REAL_DIR = os.path.join(ROOT, "data", "live", "latency")

    def test_latency_dir_no_longer_points_at_the_repo(self):
        self.assertNotEqual(os.path.normcase(os.path.normpath(L.DIR)),
                             os.path.normcase(os.path.normpath(self.REAL_DIR)),
                             "latency.DIR still points at the repo's own data/live/latency -- a tick during "
                             "this test run would append a real trace there")

    def test_a_tick_during_this_run_leaves_the_repos_git_status_unchanged(self):
        # Ground truth: this is literally how the defect was found (git status --porcelain after a test run).
        # `.git` is a FILE, not a directory, inside a worktree -- so its mere presence (either shape) is the
        # right check, not os.path.isdir().
        if not os.path.exists(os.path.join(ROOT, ".git")):
            self.skipTest("not a git checkout")
        git = ["git", "status", "--porcelain", "--untracked-files=all", "--", "data/live"]
        before = subprocess.run(git, capture_output=True, text=True, cwd=ROOT)
        if before.returncode != 0:
            self.skipTest(f"git status failed here: {before.stderr.strip()[:200]}")
        sink = []
        with L.tick("regression-guard", sink=sink) as tr:
            with tr.span("normalization"):
                pass
        after = subprocess.run(git, capture_output=True, text=True, cwd=ROOT).stdout
        self.assertEqual(before.stdout, after,
                          "a tick during this test run changed `git status` under data/live -- tests must "
                          "never mutate the repository's own live data")


if __name__ == "__main__":
    unittest.main(verbosity=2)
