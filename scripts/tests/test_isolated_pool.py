"""scripts/isolated_pool.py -- one process per task, so a crash costs that task and nothing else.

Real processes here (spawn), not stand-ins: the whole point is what happens when a child process dies, and a
thread-based double cannot die that way. Functions run in the children are module-level so spawn can import
them.
"""
import concurrent.futures, functools, io, contextlib, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import isolated_pool as IP  # noqa: E402


def square(x):
    return {"x": x, "sq": x * x}


def die_first_time(marker):
    """Hard-exits (like a segfault: no exception, no result) the first time; succeeds once the marker exists."""
    if not os.path.exists(marker):
        open(marker, "w").close()
        os._exit(3)
    return "survived"


def raise_value_error():
    raise ValueError("an ordinary task failure")


class OneProcessPerTask(unittest.TestCase):
    def test_results_come_back_unchanged_and_in_the_right_future(self):
        with IP.IsolatedExecutor(max_workers=3) as ex:
            futs = {x: ex.submit(square, x) for x in range(6)}
        for x, f in futs.items():
            self.assertEqual(f.result(), {"x": x, "sq": x * x})

    def test_a_crash_fails_only_its_own_future(self):
        marker = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMP")), "crashed-once")
        with IP.IsolatedExecutor(max_workers=2) as ex:
            dying = ex.submit(die_first_time, marker)
            siblings = [ex.submit(square, x) for x in range(3)]
        with self.assertRaises(IP.WorkerCrashed):
            dying.result()
        self.assertEqual([f.result()["sq"] for f in siblings], [0, 1, 4])
        with IP.IsolatedExecutor(max_workers=1) as ex:      # a fresh process for the retry succeeds
            self.assertEqual(ex.submit(die_first_time, marker).result(), "survived")

    def test_an_ordinary_exception_is_delivered_as_itself(self):
        with IP.IsolatedExecutor(max_workers=1) as ex:
            f = ex.submit(raise_value_error)
        with self.assertRaises(ValueError):
            f.result()


class RunScansWorksInAFreshInterpreter(unittest.TestCase):
    """The except-clauses in run_scans() name concurrent.futures.process.BrokenProcessPool; that submodule is
    loaded lazily, and this test module imports it itself, so an in-process test can never see it missing.
    A fresh interpreter can: a real run died with AttributeError on its first WorkerCrashed (2026-09-27)."""

    def test_stability_report_loads_the_submodule_it_names(self):
        import subprocess
        code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('sr', r'%s'); "
                "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "print('concurrent.futures.process' in sys.modules)"
                % os.path.join(ROOT, "scripts", "stability-report.py"))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=300)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "True", r.stderr[-2000:])


class _CrashingExecutor:
    """Thread-free stand-in for run_scans(): `crash_counts[(sym, tf)]` submissions end in WorkerCrashed."""

    def __init__(self, crash_counts, max_workers=None):
        self.crash_counts = crash_counts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def submit(self, fn, sym, tf, overlay):
        fut = concurrent.futures.Future()
        if self.crash_counts.get((sym, tf), 0) > 0:
            self.crash_counts[(sym, tf)] -= 1
            fut.set_exception(IP.WorkerCrashed("simulated segfault"))
        else:
            fut.set_result(fn(sym, tf, overlay))
        return fut


class RunScansHandlesIsolatedCrashes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("stability_report_iso", os.path.join(ROOT, "scripts", "stability-report.py"))
        cls.SR = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.SR)

    def _run(self, crash_counts, **kw):
        factory = functools.partial(_CrashingExecutor, crash_counts)
        with mock.patch.object(self.SR, "_worker_scan", side_effect=lambda sym, tf, overlay: {"symbol": sym}):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                cache = self.SR.run_scans([("BTCUSDT", "1H", {}, "k1"), ("ETHUSDT", "1H", {}, "k2")], workers=2,
                                          executor_cls=factory, **kw)
        return cache, err.getvalue()

    def test_crashes_are_retried_per_task_without_touching_the_other_task(self):
        cache, err = self._run({("BTCUSDT", "1H"): 4}, max_crashes_per_task=5)
        self.assertEqual(sorted(cache), ["k1", "k2"])
        self.assertEqual(err.count("worker crashed"), 4)
        self.assertNotIn("ETHUSDT 1H worker crashed", err)

    def test_a_task_that_always_crashes_ends_the_run_loudly(self):
        with self.assertRaises(IP.WorkerCrashed):
            self._run({("BTCUSDT", "1H"): 99}, max_crashes_per_task=5)

    def test_the_default_executor_is_the_isolated_one(self):
        import inspect
        self.assertIs(inspect.signature(self.SR.run_scans).parameters["executor_cls"].default, IP.IsolatedExecutor)


if __name__ == "__main__":
    unittest.main()
