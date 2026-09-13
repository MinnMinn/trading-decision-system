"""Bash-side coverage for scripts/scan-loop.sh's scan-window resolution (docs/plans/2026-09-13-unify-backtest-with-live-rules.md).

Code-review finding on the first cut of this refactor: a per-call `scan_window()` subshell could fail silently
(automation.py raising, an unknown tf, python3 missing) and, under `set -u`, abort the WHOLE tick -- not just
one style. The fix moved the SCAN_WINDOW lookup into the existing GATE eval (which already loads automation.py
once, in a try/except, and already emits shell assignments) and made run_style fail CLOSED per style instead.

These tests run the REAL bash/python fragments extracted from the file via subprocess, not a reimplementation
of the logic -- same precedent as scripts/tests/test_automation_integrity.py's subprocess.run of automation.py.
"""
import os, re, shutil, stat, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_LOOP = os.path.join(ROOT, "scripts", "scan-loop.sh")

# The pre-task hardcoded numbers (git history of scan-loop.sh before this refactor). A pure refactor must
# resolve every timeframe to exactly these -- see also test_timeframe_ladder.py's SCAN_WINDOW pin.
EXPECTED = {"1m": (360, 4), "5m": (576, 4), "15m": (576, 2), "1H": (480, 2), "4H": (360, 2), "1D": (240, 1)}


def _extract_gate_fragment(text):
    m = re.search(r"eval \"\$\(python3 - <<'GATE'\n(.*?)\nGATE\n\)\"", text, re.S)
    assert m, "GATE heredoc not found in scan-loop.sh -- this test needs updating alongside the script"
    return m.group(1)


def _extract_run_style(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("run_style() {"))
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start:
            return "\n".join(lines[start:i + 1])
    raise AssertionError("run_style() closing brace not found -- this test needs updating alongside the script")


class ScanLoopWindowResolution(unittest.TestCase):
    def setUp(self):
        self.text = open(SCAN_LOOP).read()

    def test_gate_emits_the_pre_task_hardcoded_numbers_for_every_timeframe(self):
        """The GATE eval is now the ONLY place that resolves the window; it must still land on exactly what
        scan-loop.sh hardcoded per call site before this task -- a pure refactor, not a retune."""
        fragment = _extract_gate_fragment(self.text)
        r = subprocess.run([sys.executable], input=fragment, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        env = dict(re.findall(r"^(SCANWIN_\w+)=(\d+)$", r.stdout, re.M))
        for tf, (bars, recent) in EXPECTED.items():
            self.assertEqual(int(env[f"SCANWIN_BARS_{tf}"]), bars, f"tf={tf} bars")
            self.assertEqual(int(env[f"SCANWIN_RECENT_{tf}"]), recent, f"tf={tf} recent")

    def test_run_style_fails_closed_on_a_missing_window_and_the_next_style_still_runs(self):
        """Critical-1 regression test: an unresolved timeframe (unknown tf, or automation.py unreadable --
        simulated here the same way the real script sees it: SCANWIN_BARS_<tf>/RECENT_<tf> simply absent) must
        log a line naming the style+timeframe and return 1 -- it must NOT abort the script via `set -u`, and
        every OTHER style in the same tick must still run."""
        tmp = tempfile.mkdtemp()
        try:
            scripts_dir = os.path.join(tmp, "scripts")
            data_dir = os.path.join(tmp, "data", "live")
            os.makedirs(scripts_dir); os.makedirs(data_dir)
            calls_log = os.path.join(data_dir, "stub-calls.log")
            # Stubs stand in for the network/model calls run_style makes once past the window guard --
            # this test is about argument resolution and fail-closed behaviour, not live scanning.
            with open(os.path.join(scripts_dir, "fetch-binance-klines.sh"), "w") as f:
                f.write("#!/usr/bin/env bash\nexit 0\n")
            with open(os.path.join(scripts_dir, "ict-scan.py"), "w") as f:
                f.write(
                    "#!/usr/bin/env python3\n"
                    "import sys\n"
                    "open(%r, 'a').write(' '.join(sys.argv[1:]) + chr(10))\n"
                    "sys.exit(0)\n" % calls_log
                )
            for name in ("fetch-binance-klines.sh", "ict-scan.py"):
                p = os.path.join(scripts_dir, name)
                os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)

            run_style_src = _extract_run_style(self.text)
            harness = os.path.join(tmp, "harness.sh")
            with open(harness, "w") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("set -uo pipefail\n")               # same guard the real script runs under
                f.write('ROOT="%s"; cd "$ROOT"\n' % tmp)
                f.write('LOG="data/live/test.log"\n')
                f.write('AUTO_STYLES="scalping,daytrade"\nAUTO_CRYPTO="BTCUSDT"\nAUTO_INSTRUMENTS="BTCUSDT"\n')
                f.write('now() { date -u +%FT%TZ; }\n')
                f.write('model_read() { :; }\n')            # not under test here; keep it a no-op
                f.write(run_style_src + "\n")
                # Unknown timeframe "2H": no SCANWIN_BARS_2H/RECENT_2H is ever emitted for it by the real GATE
                # (it is not in SCAN_WINDOW), so the call site's "${SCANWIN_BARS_2H:-}" is exactly the empty
                # string a broken/missing automation.py would also produce.
                f.write('run_style 2H scalping "${SCANWIN_BARS_2H:-}" "${SCANWIN_RECENT_2H:-}"; echo "AFTER_BAD rc=$?"\n')
                # A real timeframe right after it must still run -- this is the actual Critical-1 assertion.
                f.write('run_style 1m scalping "${SCANWIN_BARS_1m:-}" "${SCANWIN_RECENT_1m:-}"; echo "AFTER_GOOD rc=$?"\n')
            os.chmod(harness, os.stat(harness).st_mode | stat.S_IEXEC)
            env = dict(os.environ); env.update({"SCANWIN_BARS_1m": "360", "SCANWIN_RECENT_1m": "4"})
            # SCANWIN_BARS_2H/RECENT_2H are deliberately absent from env -- the harness's "${...:-}" reads that
            # as empty, exactly like the real GATE never emitting a var for a timeframe outside SCAN_WINDOW.

            r = subprocess.run(["bash", harness], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, "the tick aborted instead of failing closed per style: " + r.stderr)
            self.assertIn("AFTER_BAD rc=1", r.stdout)
            self.assertIn("AFTER_GOOD rc=0", r.stdout)
            log = open(os.path.join(data_dir, "test.log")).read()
            self.assertIn("2H", log, "the missing timeframe must be named in the MONITORED log")
            self.assertTrue(os.path.exists(calls_log), "the good style after the bad one never ran ict-scan.py")
            calls = open(calls_log).read()
            self.assertIn("--n 360", calls)
            self.assertIn("--recent 4", calls)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_style_arg_count_guard_fails_loudly_without_relying_on_set_u(self):
        """Defence in depth: a call site with the wrong arity must be caught explicitly, not by `set -u`
        aborting on the first unbound positional."""
        tmp = tempfile.mkdtemp()
        try:
            data_dir = os.path.join(tmp, "data", "live")
            os.makedirs(data_dir)
            run_style_src = _extract_run_style(self.text)
            harness = os.path.join(tmp, "harness.sh")
            with open(harness, "w") as f:
                f.write("#!/usr/bin/env bash\nset -uo pipefail\n")
                f.write('ROOT="%s"; cd "$ROOT"\n' % tmp)
                f.write('LOG="data/live/test.log"\n')
                f.write('AUTO_STYLES="scalping"\nAUTO_CRYPTO="BTCUSDT"\nAUTO_INSTRUMENTS="BTCUSDT"\n')
                f.write('now() { date -u +%FT%TZ; }\n')
                f.write('model_read() { :; }\n')
                f.write(run_style_src + "\n")
                f.write('run_style 1m scalping; echo "AFTER rc=$?"\n')   # only 2 of the required 4-5 args
            os.chmod(harness, os.stat(harness).st_mode | stat.S_IEXEC)
            r = subprocess.run(["bash", harness], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "wrong arity crashed the script instead of failing loudly: " + r.stderr)
            self.assertIn("AFTER rc=1", r.stdout)
            log = open(os.path.join(data_dir, "test.log")).read()
            self.assertIn("wrong arg count", log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
