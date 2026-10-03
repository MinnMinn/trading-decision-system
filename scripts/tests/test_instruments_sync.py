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
        self.assertEqual(m.MARKET_INSTRUMENTS, {k: I.live_analysis(k) for k in I.MARKETS})   # research-only symbols are not live

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
        allowed; re-introducing the literal is not.

        One explicit, per-line exception: a line whose source carries the comment marker `pinned-universe` is a
        FROZEN research universe -- a pre-registered set that is part of a plan hash or a recorded measurement
        (fund-search FUND_SYMBOLS / DEV_BARS, the diagnose-methods audit slice). Deriving those from the live registry
        would silently change a sealed design whenever instruments.json changes (CLAUDE.md §10/§46). The marker names
        the reason in the file itself and is visible in review; an unmarked re-listing still fails."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import srcscan
        cfd = set(I.analysis("cfd"))
        offenders = []
        for f in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
            if not f.endswith(".py") or f in ("instruments.py", "fetch-history-cfd.py"):
                continue
            raw = open(os.path.join(ROOT, "scripts", f), encoding="utf-8").read().split("\n")
            for n, line in srcscan.code_lines(os.path.join(ROOT, "scripts", f)):
                if 0 < n <= len(raw) and "pinned-universe" in raw[n - 1]:
                    continue
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




class ResearchOnlySymbolsStayOffTheLiveAndOrderPaths(unittest.TestCase):
    """Owner 2026-10-01 (symbol universe): XPTUSD XPDUSD UK100 EU50 JP225 HK50 US2000 SPN35 N25 are on analysis.cfd ONLY so the
    fund search can import their history and read their cost specs. `research_only` (instruments.json) is the registry's marker;
    they must never be orderable and the live surfaces read live_analysis() (analysis minus research-only). AUS200 predates
    the list (it is on execution.cfd already) and is not on it. No forex market or FX symbol was re-added (the guard above)."""
    NEW = ["XPTUSD", "XPDUSD", "UK100", "EU50", "JP225", "HK50", "US2000", "SPN35", "N25"]

    def test_the_marker_lists_exactly_the_new_symbols(self):
        self.assertEqual(I.research_only("cfd"), self.NEW)
        self.assertEqual(I.research_only("crypto"), [])
        self.assertEqual(I.research_only(), self.NEW)

    def test_they_are_analysable_but_never_orderable_nor_backtested_nor_live(self):
        for sym in self.NEW:
            self.assertEqual(I.market_of(sym), "cfd")
            self.assertIn(sym, I.analysis("cfd"))
            self.assertNotIn(sym, I.execution())
            self.assertNotIn(sym, I.backtested())
            self.assertNotIn(sym, I.live_analysis())
        self.assertEqual(I.live_analysis("cfd"), ["XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200"])
        self.assertEqual(I.execution("cfd"), ["XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200"])

    def test_the_live_surfaces_do_not_list_them(self):
        auto = _load("automation", "automation.py")
        self.assertTrue(set(self.NEW).isdisjoint(s for m in auto.MARKETS for s in auto.MARKET_INSTRUMENTS[m]))
        bridge = _load("mt5_bridge", "mt5-order-bridge.py")
        self.assertTrue(bridge.ALLOWED.isdisjoint(self.NEW))

    def test_an_orderable_or_unregistered_research_only_symbol_is_refused_at_load(self):
        import copy
        import json
        base = json.load(open(I.PATH, encoding="utf-8"))
        for bad in ("XAUUSD", "NOTASYMBOL"):          # XAUUSD is on execution.cfd; the other is not on analysis.cfd
            d = copy.deepcopy(base)
            d["research_only"]["cfd"].append(bad)
            saved = I._DATA
            try:
                I._DATA = d
                with self.assertRaises(ValueError, msg=bad):
                    I._load()
            finally:
                I._DATA = saved


class ForexWasRemovedCleanly(unittest.TestCase):
    """The 7 majors went onto BOTH allowlists on 2026-09-17 (user decision, lifting the blanket prohibition)
    and were removed 2026-09-27 (owner decision, "xoa han"): in its whole ten days on the registry, `forex`
    fed no candle (no MetaTrader chart was ever attached for any pair), so its removal is a registry edit
    with nothing live to migrate -- see docs/architecture/instruments.json history for both entries.

    Was ForexIsWiredEndToEnd, asserting the four places a third market could have been half-ADDED and nothing
    would have failed. These assert the same four places could not have been half-REMOVED: a stale `forex`
    entry anywhere in the style vocabulary, the dimension routing, the order venue or the order-path allowlist
    would raise at import/load time, not linger as a silent copy."""
    MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

    def test_forex_is_gone_from_the_market_registry(self):
        self.assertNotIn("forex", I.MARKETS)
        with self.assertRaises(KeyError):
            I.analysis("forex")
        with self.assertRaises(KeyError):
            I.execution("forex")
        with self.assertRaises(KeyError):
            I.backtested("forex")

    def test_no_major_has_a_canonical_id_or_a_market(self):
        for sym in self.MAJORS:
            with self.assertRaises(KeyError):
                I.canonical(sym)
            self.assertIsNone(I.market_of(sym))

    def test_no_style_routes_to_forex(self):
        """market_of_style tested a `cfd-` prefix and returned "crypto" for everything else, so a surviving
        fx- style would have quietly obeyed CRYPTO's dimension flags rather than raising. It is a table
        lookup now, and the table has no fx- entries left at all."""
        auto = _load("automation", "automation.py")
        fx = [s for (m, _tf), s in auto.STYLE.items() if m == "forex"]
        self.assertEqual(fx, [])
        for style in ("fx-day", "fx-scalping", "fx-swing"):
            self.assertNotIn(style, auto.STYLE.values())
            with self.assertRaises(KeyError):
                auto.market_of_style(style)

    def test_methods_has_no_forex_market(self):
        M = _load("methods", "methods.py")
        self.assertNotIn("forex", M.markets())

    def test_the_order_venue_no_longer_resolves_a_major(self):
        runner = _load("strategy_runner", "strategy-runner.py")
        for sym in self.MAJORS:
            with self.assertRaises(ValueError):
                runner.venue_of(sym)
        bridge = _load("mt5_bridge", "mt5-order-bridge.py")
        self.assertEqual(bridge.ALLOWED, set(I.execution("cfd")))
        self.assertTrue(bridge.ALLOWED.isdisjoint(self.MAJORS))

    def test_the_compiled_ea_allowlist_matches_the_mt5_execution_lists(self):
        """integrations/mt5/OrderBridge.mq5 InpAllowedSymbols is a COMPILED input -- the EA cannot read
        instruments.json, so this is the one hand-kept copy in the system and the only thing that can catch it
        drifting is this test. A symbol here that the registry does not list means the EA would accept an order
        the Python side refuses; the reverse means a silent refusal at the terminal. Must be recompiled and
        re-attached in MetaTrader before this trimmed list takes effect on the actual EA."""
        src = open(os.path.join(ROOT, "integrations", "mt5", "OrderBridge.mq5"), encoding="utf-8").read()
        m = re.search(r'InpAllowedSymbols\s*=\s*"([^"]*)"', src)
        self.assertIsNotNone(m, "InpAllowedSymbols not found")
        want = [s for mk in I.MARKETS if I.DATA_DIR[mk] == "mt5-bridge" for s in I.execution(mk)]
        self.assertEqual(sorted(m.group(1).split(",")), sorted(want))
        self.assertTrue(set(m.group(1).split(",")).isdisjoint(self.MAJORS))


class SessionHookStaysLive(unittest.TestCase):
    """The SessionStart hook text lists the analysis allowlist; research-only symbols are not part of it (owner 2026-10-01)."""
    def test_hook_lists_only_the_live_analysis_symbols(self):
        out = subprocess.run(["bash", os.path.join(ROOT, "scripts", "session-safety-rules.sh")],
                             capture_output=True, text=True).stdout
        want = "/".join(I.live_analysis())
        self.assertIn("analysis allowlist = " + want, out)
        for sym in I.research_only():
            self.assertNotIn(sym, out)
        self.assertEqual(want, "BTCUSDT/ETHUSDT/SOLUSDT/ASTERUSDT/VIRTUALUSDT/SUIUSDT/TAOUSDT/RENDERUSDT/ONDOUSDT/"
                               "XAUUSD/XAGUSD/US500/US30/USTEC/DE40/FRA40/AUS200")

    def test_bash_reader_excludes_research_only(self):
        out = subprocess.run(["bash", "-c", f'source "{ROOT}/scripts/instruments.sh"; instruments_live_analysis cfd'],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, I.live_analysis("cfd"))


if __name__ == "__main__":
    unittest.main()
