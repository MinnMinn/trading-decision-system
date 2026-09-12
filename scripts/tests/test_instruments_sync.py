"""The instrument allowlist has ONE source: docs/architecture/instruments.json. These tests fail the build
the moment a second copy drifts from it, which is the whole point of the single-source refactor
(SYSTEM-DESIGN.md §1; the user's single-source-of-truth rule)."""
import importlib.util, json, os, re, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSingleSource(unittest.TestCase):
    def test_execution_is_subset_of_analysis(self):
        """The invariant that makes 'watch-only' mean anything: nothing orderable is off the analysis list."""
        for m in I.MARKETS:
            self.assertTrue(set(I.execution(m)) <= set(I.analysis(m)),
                            f"execution.{m} escapes analysis.{m}")

    def test_backtested_is_subset_of_execution(self):
        """You cannot claim backtest validation for a symbol that cannot even be traded -- instruments.py
        raises on load if this is violated; this test is the regression guard for that invariant."""
        for m in I.MARKETS:
            self.assertTrue(set(I.backtested(m)) <= set(I.execution(m)),
                            f"backtested.{m} escapes execution.{m}")

    def test_no_forex_anywhere(self):
        """SYSTEM-DESIGN.md §1: Forex is prohibited outright and can never appear in the allowlist."""
        fx = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "SGD", "HKD"}
        for sym in I.analysis():
            if re.fullmatch(r"[A-Z]{6}", sym):
                self.assertFalse(sym[:3] in fx and sym[3:] in fx, f"{sym} is a Forex pair")

    def test_derived_schema_enums_in_sync(self):
        """scripts/sync-instruments.py --check must pass; if it fails, run it with --write."""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-instruments.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_automation_allowlist_comes_from_the_source(self):
        m = _load("automation", "automation.py")
        self.assertEqual(m.MARKET_INSTRUMENTS, {k: I.analysis(k) for k in I.MARKETS})

    def test_pilot_universe_is_the_execution_list(self):
        """The pilot and the demo pilot must never widen to the analysis allowlist."""
        self.assertEqual(_load("strategy_runner", "strategy-runner.py").CRYPTO, I.execution("crypto"))
        self.assertEqual(_load("demo_pilot", "demo-pilot.py").SYMBOLS, I.execution("crypto"))

    def test_futures_connector_allowlist_is_the_execution_list(self):
        out = subprocess.run(["bash", "-c",
                              f'source "{ROOT}/scripts/instruments.sh"; instruments_execution crypto'],
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.split(), I.execution("crypto"))

    def test_no_script_hardcodes_the_core_triple(self):
        """A literal BTCUSDT+ETHUSDT+SOLUSDT list in a script is exactly the duplication this refactor removed.
        Argparse --symbols defaults and research/backtest tools are exempt: they are per-run inputs, not policy."""
        exempt = {"instruments.py", "sync-instruments.py", "asia-session-eval.py", "stability-report.py",
                  "measure-spring-ict.py", "rank-setups.py", "scalping-events-since.py", "backtest-methods.py",
                  "ict-scan.py", "local-eval-brief.py", "build-artifact.py", "fetch-binance-klines.sh",
                  "scan-loop.sh"}
        pat = re.compile(r'BTCUSDT["\',\s]+ETHUSDT["\',\s]+SOLUSDT')
        offenders = []
        for f in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
            if not f.endswith((".py", ".sh")) or f in exempt:
                continue
            with open(os.path.join(ROOT, "scripts", f), encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if pat.search(line):
                        offenders.append(f"{f}:{n}")
        self.assertEqual(offenders, [], f"hard-coded symbol list -- read it from instruments.py instead: {offenders}")


class DisplayMetadata(unittest.TestCase):
    def test_every_allowlisted_symbol_has_display_metadata(self):
        """build-artifact.py used to keep a parallel hand-kept CRYPTO_META dict and index it directly, so a
        symbol added to instruments.json crashed the build with a KeyError."""
        for sym in I.analysis():
            d = I.display(sym)
            self.assertTrue(d["id"] and d["label"])
            self.assertIsInstance(d["price_decimals"], int)

    def test_display_falls_back_without_an_entry(self):
        d = I.display("ZZZUSDT")
        self.assertEqual(d["id"], "zzz")
        self.assertEqual(d["price_decimals"], 2)

    def test_build_artifact_has_no_parallel_symbol_table(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn("CRYPTO_META = {", src)


if __name__ == "__main__":
    unittest.main()
