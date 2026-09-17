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

    def test_every_analysable_symbol_has_a_market(self):
        """Replaces test_no_forex_anywhere, deleted 2026-09-17 when the user lifted the Forex prohibition.

        That test asserted no six-letter currency pair could appear in the allowlist. It was also quietly
        arbitrary: XAUUSD and XAGUSD passed only because "XAU"/"XAG" were missing from its own hard-coded
        currency set, not because gold is structurally different from EURUSD in this system.

        The invariant that actually protects anything survives and is asserted here instead: every symbol on an
        analysis list resolves to exactly one market, so no symbol can be allowlisted into a market the rest of
        the system cannot route (market_of returns None -> automation.py refuses, DATA_DIR has no entry, no style
        exists). That is the check the FX test was standing in front of."""
        for sym in I.analysis():
            m = I.market_of(sym)
            self.assertIsNotNone(m, f"{sym} is on an analysis list but market_of() cannot place it")
            self.assertIn(sym, I.analysis(m), f"{sym} resolves to {m} but is not on that market's list")

    def test_derived_schema_enums_in_sync(self):
        """scripts/sync-instruments.py --check must pass; if it fails, run it with --write."""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-instruments.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_automation_allowlist_comes_from_the_source(self):
        m = _load("automation", "automation.py")
        self.assertEqual(m.MARKET_INSTRUMENTS, {k: I.analysis(k) for k in I.MARKETS})

    def test_pilot_universe_is_the_execution_list(self):
        """The pilot must never widen to the analysis allowlist."""
        self.assertEqual(_load("strategy_runner", "strategy-runner.py").CRYPTO, I.execution("crypto"))

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

    def test_no_script_hardcodes_the_mt5_symbol_set_or_the_feed_directories(self):
        """The twin of the test above, for the set it never covered.

        `MT5 = {"XAUUSD","XAGUSD","USOIL","UKOIL"}` lived in build-artifact.py, ict-scan.py, event-ledger.py,
        measure-spring-ict.py and local-eval-brief.py (plus check-narrative.py via import), and
        `{"crypto": "market-data", "cfd": "mt5-bridge"}` in automation.py and method-panel.py -- eight copies of
        two facts, in a repo whose rule is that symbol lists have one source. The test above did not catch them
        because it only looks for the crypto triple, and four of those eight files are on its exempt list.
        Both facts are now properties of the MARKET (instruments.DATA_DIR / TICK_VOLUME_MARKETS), so adding a
        symbol to an existing market requires no code edit at all.

        instruments.py is the author and is exempt. fetch-history-cfd.py is exempt for a different reason: its
        dict maps each symbol to a YAHOO contract code ("XAUUSD" -> "GC=F"), which is provider knowledge no
        registry here can derive, and it refuses an unmapped symbol rather than guessing one.

        Comments and docstrings are stripped, so explaining the removal (as several of those files now do) is
        allowed; re-introducing the literal is not."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import srcscan
        cfd = set(I.analysis("cfd"))
        offenders = []
        for f in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
            if not f.endswith(".py") or f in ("instruments.py", "fetch-history-cfd.py"):
                continue
            for n, line in srcscan.code_lines(os.path.join(ROOT, "scripts", f)):
                syms = set(re.findall(r'"([A-Z0-9]{4,10})"', line)) | set(re.findall(r"'([A-Z0-9]{4,10})'", line))
                if len(cfd & syms) >= 3:
                    offenders.append(f"{f}:{n} re-lists the MT5 symbol set (use I.data_dir / I.is_tick_volume)")
                if '"mt5-bridge"' in line and '"market-data"' in line:
                    offenders.append(f"{f}:{n} re-lists the feed directories (use I.DATA_DIR)")
        self.assertEqual(offenders, [], "market facts belong in instruments.py:\n  " + "\n  ".join(offenders))


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
