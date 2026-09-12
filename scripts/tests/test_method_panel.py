"""The method panel page. Rules PANEL-03/04/09/11 in docs/security/2026-09-12-method-panel.md.
The page is generated from code (SYSTEM-DESIGN.md §15): nothing on it is hand-written per symbol."""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import instruments as I

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


mp = load("mp", os.path.join(ROOT, "scripts", "method-panel.py"))


def cfg(crypto_dims=None, cfd_dims=None, crypto_syms=None, cfd_syms=None, env="demo"):
    return {"enabled": True, "execution": {"environment": env},
            "markets": {
                "crypto": {"enabled": True,
                           "instruments": crypto_syms if crypto_syms is not None else ["BTCUSDT"],
                           "dimensions": crypto_dims or {d: True for d in M.dimensions("crypto")}},
                "cfd": {"enabled": True,
                        "instruments": cfd_syms if cfd_syms is not None else ["XAUUSD"],
                        "dimensions": cfd_dims or {d: True for d in M.dimensions("cfd")}}}}


class Presets(unittest.TestCase):
    def test_every_preset_in_the_registry_has_a_card(self):
        html = mp.render(cfg())
        for p in M.PRESETS:
            self.assertIn(f'data-preset="{p["id"]}"', html, f"{p['id']} has no card")

    def test_cfd_column_locks_the_coinglass_presets_with_a_reason(self):
        html = mp.render(cfg())
        for p in M.PRESETS:
            if p not in M.presets_for("cfd"):
                self.assertRegex(html, rf'data-market="cfd"[^>]*data-preset="{re.escape(p["id"])}"[^>]*disabled')
        self.assertIn("CoinGlass", html)

    def test_no_research_group_renders_when_every_preset_is_trade_tier(self):
        """docs/architecture/methods.json 2026-09-12 SOLO addition: no preset is tagged research any more now
        that SOLO makes the single-dimension presets tradeable. A heading with an empty grid under it is a
        rendering bug, not a harmless empty group -- assert the group is omitted entirely."""
        html = mp.render(cfg())
        self.assertFalse(any(p["tier"] == "research" for p in M.PRESETS),
                          "fixture assumption stale: a research-tier preset exists again -- revisit this test")
        self.assertNotIn(mp._TIER_LABEL["research"], html)

    def test_solo_mode_cards_state_the_higher_threshold_consequence(self):
        """wyckoff/ict are SOLO-mode presets (tier: trade) since the 2026-09-12 SOLO addition -- the stale
        'always NO TRADE' research copy is gone; the card must instead say it runs SOLO, on one dimension, at
        a higher score threshold than NORMAL, because nothing else confirms it (SYSTEM-DESIGN.md section 6.2)."""
        html = mp.render(cfg())
        solo_presets = [p for p in M.PRESETS if p["mode"] == "SOLO"]
        self.assertTrue(solo_presets, "fixture assumption stale: no SOLO preset in the registry")
        normal_threshold = M.MODES["NORMAL"]["threshold"]
        solo_threshold = M.MODES["SOLO"]["threshold"]
        checked = 0
        for p in solo_presets:
            for market in ("crypto", "cfd"):
                if p not in M.presets_for(market):
                    continue
                card = _preset_card_html(html, market, p["id"])
                self.assertIn("SOLO", card)
                self.assertIn(str(solo_threshold), card)
                self.assertIn(str(normal_threshold), card)
                self.assertNotIn("NO TRADE", card, f"{market}/{p['id']} still carries the stale research copy")
                checked += 1
        self.assertTrue(checked, "no SOLO preset had an unlocked card in either market")

    def test_card_mode_and_threshold_never_disagree_with_the_registry(self):
        """A card that ever claims a mode or threshold other than the registry's own is worse than no claim at
        all -- this is the invariant test, pinned to scripts/methods.py's MODES table via M.mode_of(), not to
        today's numbers, so it still fails if a future registry edit and the page's copy ever drift apart."""
        html = mp.render(cfg())
        checked = 0
        for market in ("crypto", "cfd"):
            for p in M.presets_for(market):
                card = _preset_card_html(html, market, p["id"])
                mode = M.mode_of(p["id"])
                info = M.MODES[mode]
                self.assertRegex(card, rf'data-mode="{re.escape(mode)}"',
                                  f"{market}/{p['id']}: card does not declare registry mode {mode}")
                self.assertRegex(card, rf'data-mode-minimum="{info["minimum"]}"',
                                  f"{market}/{p['id']}: card minimum disagrees with registry")
                self.assertRegex(card, rf'data-mode-threshold="{info["threshold"]}"',
                                  f"{market}/{p['id']}: card threshold disagrees with registry")
                checked += 1
        self.assertTrue(checked, "no unlocked card was found to check")

    def test_the_applied_preset_is_marked_selected(self):
        html = mp.render(cfg(crypto_dims={"wyckoff": True, "ict": True, "footprint": False, "heatmap": False}))
        self.assertRegex(html, r'data-market="crypto"[^>]*data-preset="wyckoff\+ict"[^>]*aria-pressed="true"')

    def test_custom_flag_set_selects_no_card_and_shows_the_four_booleans(self):
        html = mp.render(cfg(crypto_dims={"wyckoff": False, "ict": True, "footprint": True, "heatmap": False}))
        self.assertNotRegex(html, r'data-market="crypto"[^>]*aria-pressed="true"')
        self.assertIn("custom", html)


class Instruments(unittest.TestCase):
    def test_every_allowlisted_symbol_has_a_chip_in_its_market(self):
        html = mp.render(cfg())
        for m in ("crypto", "cfd"):
            for sym in I.analysis(m):
                self.assertRegex(html, rf'data-market="{m}"[^>]*data-symbol="{sym}"')

    def test_selected_symbols_are_ticked(self):
        html = mp.render(cfg(crypto_syms=["BTCUSDT", "ETHUSDT"]))
        self.assertRegex(html, r'data-symbol="BTCUSDT"[^>]*aria-pressed="true"')
        self.assertRegex(html, r'data-symbol="SOLUSDT"[^>]*aria-pressed="false"')

    def test_a_symbol_with_no_data_on_disk_is_badged(self):
        html = mp.render(cfg(), data_present={"XAUUSD"})
        self.assertRegex(html, r'data-symbol="USOIL"[^>]*data-nodata="1"')
        self.assertRegex(html, r'data-symbol="XAUUSD"[^>]*data-nodata="0"')

    def test_unbacktested_symbols_carry_the_caveat(self):
        """instruments.json records that the pilot rules were backtested on BTC/ETH/SOL only."""
        html = mp.render(cfg(), backtested={"BTCUSDT", "ETHUSDT", "SOLUSDT"})
        self.assertRegex(html, r'data-symbol="TAOUSDT"[^>]*data-unvalidated="1"')
        self.assertRegex(html, r'data-symbol="BTCUSDT"[^>]*data-unvalidated="0"')

    def test_default_backtested_reads_the_registry_field_not_a_regex(self):
        """No injected backtested= -- exercises the real docs/architecture/instruments.json 'backtested' field
        via scripts/instruments.py, not a parsed sentence."""
        html = mp.render(cfg())
        self.assertRegex(html, r'data-symbol="BTCUSDT"[^>]*data-unvalidated="0"')
        self.assertRegex(html, r'data-symbol="TAOUSDT"[^>]*data-unvalidated="1"')

    def test_missing_backtested_data_badges_every_symbol_fail_loud(self):
        """The warning must fail loud, not fail silent: if we do not know who was backtested (equivalent to
        instruments.json's backtested{} field being absent), assume NOBODY was, and badge every allowlisted
        symbol in both markets -- no exceptions."""
        html = mp.render(cfg(), backtested=set())
        for m in ("crypto", "cfd"):
            for sym in I.analysis(m):
                self.assertRegex(html, rf'data-symbol="{sym}"[^>]*data-unvalidated="1"',
                                 f"{sym} was not badged when backtested data was unavailable")

    def test_empty_selection_renders_as_a_chosen_state_not_an_error(self):
        """PANEL-11: no instruments is a legitimate narrowing, and must look deliberate."""
        html = mp.render(cfg(cfd_syms=[]))
        self.assertIn("không mở lệnh mới", html)


def _preset_card_html(html, market, pid):
    """The single <button class="preset-card" ...>...</button> chunk for one market/preset -- so a
    rendered-copy assertion can be scoped to one card instead of the whole page (buttons never nest here,
    so the next literal "</button>" after the opening tag is always the matching close)."""
    marker = f'data-market="{market}" data-preset="{pid}"'
    start = html.index(marker)
    tag_start = html.rindex("<button", 0, start)
    end = html.index("</button>", start) + len("</button>")
    return html[tag_start:end]


class PilotHonesty(unittest.TestCase):
    def test_each_preset_card_names_the_runner_methods_it_permits(self):
        html = mp.render(cfg())
        self.assertIn("WYCKOFF-BOOK", html)
        self.assertIn("COMBINED", html)

    def test_the_page_says_the_runner_wyckoff_is_not_the_wyckoff_dimension(self):
        html = mp.render(cfg())
        self.assertIn("wyckoff_rules.py", html)

    def test_real_environment_replaces_the_pilot_column(self):
        """strategy-runner.py:167 refuses every top5 tick when environment is real."""
        self.assertIn("pilot không chạy ở REAL", mp.render(cfg(env="real")))
        self.assertNotIn("pilot không chạy ở REAL", mp.render(cfg(env="demo")))

    def test_wyckoff_honesty_line_appears_iff_the_permitted_set_has_a_wyckoff_runner(self):
        """The honesty line claims the mechanical Wyckoff rule engine ran. Printing it on a card whose
        permitted runner set has no WYCKOFF/WYCKOFF-BOOK (e.g. the bare ICT preset) claims machinery
        that never engaged -- the opposite failure from the one the line exists to prevent."""
        html = mp.render(cfg())
        seen_present, seen_absent = False, False
        for market in ("crypto", "cfd"):
            for p in M.presets_for(market):
                pid = p["id"]
                card = _preset_card_html(html, market, pid)
                permitted = M.runner_methods(M.flags_for(pid))
                expected = bool(permitted & {"WYCKOFF", "WYCKOFF-BOOK"})
                actual = "wyckoff_rules.py" in card
                self.assertEqual(actual, expected,
                                  f"{market}/{pid}: permitted={sorted(permitted)}, "
                                  f"honesty line present={actual}, expected={expected}")
                seen_present = seen_present or actual
                seen_absent = seen_absent or not actual
        # Sanity: the registry must actually produce both outcomes, or this test cannot distinguish
        # "correctly gated" from "always shows" / "never shows".
        self.assertTrue(seen_present, "no preset triggered the honesty line at all")
        self.assertTrue(seen_absent, "every preset triggered the honesty line -- gate is not selective")

    def test_no_card_lists_a_non_runnable_method_under_runner(self):
        """COMBINED-BOOK and PARTIAL are runnable: false in methods.json -- backtest-only
        (scripts/backtest-methods.py:528) -- and strategy-runner.py's METHODS is methods.runnable(),
        which excludes them. A card must never claim the pilot can fire a method it cannot."""
        html = mp.render(cfg())
        non_runnable = set(M.RUNNER_METHODS) - M.runnable()
        self.assertTrue(non_runnable, "registry fixture has no non-runnable method to guard against")
        checked_a_runner_line = False
        for market in ("crypto", "cfd"):
            for p in M.presets_for(market):
                pid = p["id"]
                card = _preset_card_html(html, market, pid)
                m = re.search(r'runner: ([^<]*)</div>', card)
                if not m:
                    continue
                checked_a_runner_line = True
                listed = {x.strip() for x in m.group(1).split(",") if x.strip() and x.strip() != "(không có)"}
                self.assertFalse(listed & non_runnable,
                                  f"{market}/{pid}: runner line lists non-runnable {listed & non_runnable}")
        self.assertTrue(checked_a_runner_line, "no card's runner line was found to check")


class DbWiring(unittest.TestCase):
    def test_capability_declaration_is_owner_only(self):
        """PANEL-01: the bare {db:{}} default lets every viewer WRITE the control docs, and declaring db makes
        the artifact organization-internal. The `user` capability is unavailable, so no viewer identity exists
        and attribution is impossible -- the only control left is the write rule."""
        src = open(os.path.join(ROOT, "scripts", "method-panel.py"), encoding="utf-8").read()
        self.assertIn('"path": ""', src)
        self.assertIn('"write": "owner"', src)
        self.assertIn('"read": "owner"', src)

    def test_page_reads_applied_state_from_db_not_from_baked_html(self):
        html = mp.render(cfg())
        self.assertIn("control/applied.crypto", html)
        self.assertIn("control/applied.cfd", html)

    def test_request_doc_is_written_with_exactly_three_keys(self):
        """PANEL-10: closed shape -- preset, instruments, requested_at. A missing key is an error, never a default."""
        html = mp.render(cfg())
        self.assertIn("control/request.crypto", html)
        self.assertRegex(html, r"preset\s*:|['\"]preset['\"]")
        self.assertRegex(html, r"instruments\s*:|['\"]instruments['\"]")
        self.assertRegex(html, r"requested_at\s*:|['\"]requested_at['\"]")

    def test_db_values_never_reach_the_page_as_markup(self):
        """PANEL-03: textContent only. innerHTML with db content is the XSS sink."""
        html = mp.render(cfg())
        js = html[html.index("<script"):]
        self.assertNotIn("innerHTML", js)

    def test_page_degrades_when_db_is_unavailable(self):
        """claude.use() resolves null when the capability is not granted; the page must still render."""
        html = mp.render(cfg())
        self.assertIn("claude.use", html)
        self.assertRegex(html, r"null|!db")

    def test_stale_applier_banner_exists(self):
        """PANEL-07: without a heartbeat check, 'live applied state' is a promise the page cannot keep --
        with no Claude session open, taps go nowhere forever and the page would look fine."""
        html = mp.render(cfg())
        self.assertIn("control/heartbeat", html)
        self.assertIn("12", html)


NODE = shutil.which("node")


def _guard_block_source():
    """The self-contained PANEL-05 guard (IMPLAUSIBLE_PENDING_MS + classifyElapsedMs), extracted by
    its comment markers in scripts/method-panel.py so it can be executed for real under Node --
    it is a pure function with no DOM/db dependency, so this is honest execution, not a grep."""
    src = mp._SCRIPT
    start = src.index("// PANEL-05_GUARD_START")
    end = src.index("// PANEL-05_GUARD_END") + len("// PANEL-05_GUARD_END")
    return src[start:end]


def _js_function_source(js, name):
    """One top-level function's full source, matching braces (robust to nested blocks) -- used for
    structural assertions on functions that DO touch the DOM/db and so cannot be run under Node."""
    marker = "function " + name
    start = js.index(marker)
    open_brace = js.index("{", start)
    depth, i = 0, open_brace
    while True:
        ch = js[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[start:i + 1]
        i += 1


def _run_node(js_snippet):
    result = subprocess.run(["node", "-e", js_snippet], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise AssertionError("node failed: " + result.stderr)
    return result.stdout.strip()


@unittest.skipUnless(NODE, "node not installed -- the PANEL-05 guard is executed for real, not just grepped")
class PendingDurationGuard(unittest.TestCase):
    """PANEL-05 (docs/security/2026-09-12-method-panel.md), closed without detecting clock skew --
    there is no server time in the db contract, and comparing the device clock to the heartbeat's
    own timestamp would conflate skew with 'the cron has not ticked yet'. Instead the page flags an
    IMPLAUSIBLE pending duration: negative (a future requested_at for this viewer) or on the order of
    a day or more. classifyElapsedMs() is a pure function extracted from the real script and run
    under Node -- these are browser-JS branches pytest cannot import and execute directly."""

    def _classify(self, elapsed_ms):
        snippet = _guard_block_source() + f"\nconsole.log(JSON.stringify(classifyElapsedMs({elapsed_ms})));"
        return json.loads(_run_node(snippet))

    def test_a_future_timestamp_is_flagged_implausible_not_a_negative_number(self):
        """A device minutes ahead writes a requested_at this viewer sees as being in the future."""
        self.assertEqual(self._classify(-5 * 60 * 1000), "implausible")

    def test_an_absurdly_old_timestamp_is_flagged_implausible(self):
        """Days old: either a genuinely stuck request or a clock off by that much -- either way not
        a number worth displaying as a real wait time."""
        self.assertEqual(self._classify(3 * 24 * 60 * 60 * 1000), "implausible")

    def test_a_normal_pending_duration_is_not_flagged(self):
        """Regression guard: the check must not swallow ordinary values -- the applier's own cadence
        (every 5 minutes, CRON-05/step 4's own 60-minute staleness cap) means a real pending wait
        under matching clocks is minutes, not hours."""
        self.assertEqual(self._classify(5 * 60 * 1000), 5)

    def test_threshold_is_on_the_order_of_a_day(self):
        """Pins the chosen IMPLAUSIBLE_PENDING_MS boundary (24h) so a future change to it is a
        visible test change, not a silent drift."""
        just_under = 24 * 60 * 60 * 1000 - 1
        just_over = 24 * 60 * 60 * 1000
        self.assertNotEqual(self._classify(just_under), "implausible")
        self.assertEqual(self._classify(just_over), "implausible")


def _request_outcome_guard_source():
    """The self-contained request-outcome guard (REFUSAL_REASON_BY_CODE/mapOrGeneric/sameInstrumentSet/
    refusalReasonText/resolveRequestOutcome), extracted by its comment markers in scripts/method-panel.py
    so it can be executed for real under Node -- same technique as _guard_block_source() above. It is the
    fourth status the applier's write shape (integrations/crons/method-switch.md steps 4 and 8) forces the
    page to model: a request the applier RESOLVED (requested_at advanced) but did not adopt (preset/
    instruments left unchanged) is a refusal, not a still-pending request."""
    src = mp._SCRIPT
    start = src.index("// REQUEST_OUTCOME_GUARD_START")
    end = src.index("// REQUEST_OUTCOME_GUARD_END") + len("// REQUEST_OUTCOME_GUARD_END")
    return src[start:end]


@unittest.skipUnless(NODE, "node not installed -- the request-outcome guard is executed for real, not just grepped")
class RequestOutcomeGuard(unittest.TestCase):
    """resolveRequestOutcome(req, doc) is the pure decision that replaces requestMatchesApplied()'s
    boolean with the three real outcomes: pending (unresolved), applied (resolved, adopted), refused
    (resolved, not adopted -- the fourth state the cron's write shape produces and the old code missed)."""

    def _resolve(self, req, doc):
        snippet = (_request_outcome_guard_source() + "\nconsole.log(JSON.stringify(resolveRequestOutcome("
                   + json.dumps(req) + ", " + json.dumps(doc) + ")));")
        return json.loads(_run_node(snippet))

    def _req(self, preset="wyckoff", instruments=None, requested_at="2026-09-12T10:05:00Z"):
        return {"preset": preset, "instruments": instruments if instruments is not None else ["BTCUSDT"],
                "requested_at": requested_at}

    def test_request_not_yet_resolved_is_pending(self):
        req = self._req(requested_at="2026-09-12T10:05:00Z")
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z",
               "preset_result": "applied", "instruments_result": "no-op", "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["reason"])

    def test_resolved_with_preset_and_instruments_equal_is_applied(self):
        req = self._req()
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": "applied", "instruments_result": "no-op", "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "applied")
        self.assertIsNone(result["reason"])

    def test_resolved_with_a_different_preset_is_refused(self):
        """The applier left preset unchanged (still the configuration actually in force) while
        advancing requested_at -- PANEL rule for this page: never show 'đang chờ áp dụng' forever."""
        req = self._req(preset="ict")
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": "refused: unknown_or_wrong_market_preset", "instruments_result": "no-op",
               "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "refused")
        self.assertIsInstance(result["reason"], str)
        self.assertGreater(len(result["reason"]), 0)

    def test_resolved_with_different_instruments_is_refused(self):
        req = self._req(instruments=["BTCUSDT", "ETHUSDT"])
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": "applied", "instruments_result": "refused: invalid_instrument", "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "refused")
        self.assertIsInstance(result["reason"], str)
        self.assertGreater(len(result["reason"]), 0)

    def test_unknown_result_code_gets_generic_copy_the_raw_code_is_not_echoed(self):
        req = self._req(preset="ict")
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": "refused: some_new_reason_the_page_has_never_seen", "instruments_result": "no-op",
               "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "refused")
        self.assertNotIn("some_new_reason_the_page_has_never_seen", result["reason"])

    def test_a_very_long_result_string_is_truncated_never_echoed(self):
        req = self._req(preset="ict")
        long_code = "x" * 5000
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": long_code, "instruments_result": "no-op", "error": None}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "refused")
        self.assertLess(len(result["reason"]), 300)
        self.assertNotIn(long_code, result["reason"])

    def test_a_step4_error_field_is_refused_even_if_fields_happen_to_match(self):
        """A malformed/stale-or-skewed rejection (step 4) records only `error`, never per-half results,
        and leaves preset/instruments at whatever was already in force -- which could coincidentally
        equal the rejected request. `error` must still win: this was declined, not adopted."""
        req = self._req()
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": req["requested_at"],
               "preset_result": None, "instruments_result": None, "error": "stale_or_skewed_requested_at"}
        result = self._resolve(req, doc)
        self.assertEqual(result["status"], "refused")
        self.assertNotIn("stale_or_skewed_requested_at", result["reason"])


def _pending_reconcile_guard_source():
    """pendingStillOutstanding (PENDING_RECONCILE_GUARD) calls sameInstrumentSet/resolveRequestOutcome,
    which live in REQUEST_OUTCOME_GUARD -- concatenated so the pure function runs standalone under Node,
    same technique as the other guard extractions in this file."""
    src = mp._SCRIPT
    start = src.index("// PENDING_RECONCILE_GUARD_START")
    end = src.index("// PENDING_RECONCILE_GUARD_END") + len("// PENDING_RECONCILE_GUARD_END")
    return _request_outcome_guard_source() + "\n" + src[start:end]


@unittest.skipUnless(NODE, "node not installed -- pendingStillOutstanding is executed for real, not just grepped")
class PendingSurvivesWriteSuccess(unittest.TestCase):
    """Defect 1 (reported: a tap that looks like nothing happened): pendingDesired must mean 'desired but
    not yet applied', not 'not yet written'. A write ack landing in request[market] must not, by itself,
    clear the pending indicator -- only the applied snapshot confirming the exact match, or the tied
    request resolving as a refusal, may. pendingStillOutstanding() is the pure decision renderMarket()
    calls on every repaint; these test it directly under Node, the same technique already used for
    resolveRequestOutcome() and classifyElapsedMs()."""

    def _outstanding(self, pending, doc, req):
        snippet = (_pending_reconcile_guard_source() + "\nconsole.log(JSON.stringify(pendingStillOutstanding("
                   + json.dumps(pending) + ", " + json.dumps(doc) + ", " + json.dumps(req) + ")));")
        return json.loads(_run_node(snippet))

    def test_pending_survives_once_written_but_the_applier_has_not_caught_up(self):
        pending = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"]}
        req = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z"}
        self.assertTrue(self._outstanding(pending, None, req),
                         "a successful write (request doc now matches) must not by itself end the pending state")

    def test_pending_clears_once_the_applied_snapshot_confirms_the_match(self):
        pending = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"]}
        req = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z"}
        doc = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z",
               "applied_at": "2026-09-12T10:01:00Z", "preset_result": "applied", "instruments_result": "no-op",
               "error": None}
        self.assertFalse(self._outstanding(pending, doc, req))

    def test_pending_clears_on_a_resolved_refusal(self):
        pending = {"preset": "ict", "instruments": ["BTCUSDT"]}
        req = {"preset": "ict", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z"}
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z",
               "preset_result": "refused: unknown_or_wrong_market_preset", "instruments_result": "no-op",
               "error": None}
        self.assertFalse(self._outstanding(pending, doc, req))

    def test_pending_survives_while_the_tied_request_has_not_itself_resolved(self):
        """The applied doc still reflects an OLDER request (its requested_at differs from the pending
        edit's own request) -- the applier has not gotten to this one yet, so it must keep showing pending."""
        pending = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"]}
        req = {"preset": "wyckoff+ict", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:05:00Z"}
        doc = {"preset": "wyckoff", "instruments": ["BTCUSDT"], "requested_at": "2026-09-12T10:00:00Z",
               "preset_result": "applied", "instruments_result": "no-op", "error": None}
        self.assertTrue(self._outstanding(pending, doc, req))

    def test_no_pending_edit_is_never_outstanding(self):
        self.assertFalse(self._outstanding(None, None, None))


class FlushWriteDoesNotClearPendingOnSuccess(unittest.TestCase):
    """Structural regression pin for Defect 1's root cause: the fix is worthless if a future edit
    reintroduces `pendingDesired[market] = null` inside flushWrite's success handler."""

    def test_the_success_handler_never_nulls_pending_desired(self):
        fn = _js_function_source(mp._SCRIPT, "flushWrite")
        then_start = fn.index(".then(function ()")
        catch_start = fn.index(".catch(function (err)")
        then_body = fn[then_start:catch_start]
        self.assertNotIn("pendingDesired[market] = null", then_body,
                          "a successful write must not clear the pending indicator -- only "
                          "reconcilePending()/pendingStillOutstanding() may")
        self.assertIn("request[market] = doc", then_body)


class DesiredBaseUsesInitialBakedSnapshot(unittest.TestCase):
    """Defect 2's root cause (reported): bakedState() re-reads the DOM at call time, and a null applied
    snapshot has already repainted every chip aria-pressed=false by the time desiredBase() falls through
    to it. The fix captures the true baked selection once, before boot()/any subscription can mutate the
    DOM, and desiredBase() must fall back to that frozen snapshot instead of a live re-read."""

    def test_desired_base_does_not_call_baked_state_live(self):
        fn = _js_function_source(mp._SCRIPT, "desiredBase")
        self.assertNotIn("bakedState(market)", fn)
        self.assertIn("INITIAL_BAKED", fn)

    def test_initial_baked_is_captured_before_boot_runs(self):
        src = mp._SCRIPT
        baked_idx = src.index("var INITIAL_BAKED = {};")
        boot_call_idx = src.rindex("boot();")
        self.assertLess(baked_idx, boot_call_idx,
                         "the baked snapshot must be captured before boot()/any db subscription can "
                         "repaint the DOM from a live (possibly null) applied snapshot")


class AriaPressedSourceOfTruth(unittest.TestCase):
    """A request can never be mistaken for something already in force: aria-pressed on both preset cards
    and instrument chips must be set exclusively from the live control/applied.<market> snapshot, never
    from a locally-tapped/pending value -- a tap only ever toggles the separate `is-desired` class. Pinned
    to paintMarket(), the sole function that writes aria-pressed (renderMarket() delegates to it after
    reconciling), so a future change routing aria-pressed through `pending` anywhere fails this test."""

    def test_aria_pressed_is_set_only_from_the_applied_doc_never_from_pending(self):
        fn = _js_function_source(mp._SCRIPT, "paintMarket")
        set_pressed_lines = [line for line in fn.splitlines() if 'setAttribute("aria-pressed"' in line]
        self.assertEqual(len(set_pressed_lines), 2,
                          "expected exactly one aria-pressed assignment for cards and one for chips")
        for line in set_pressed_lines:
            self.assertNotIn("pending", line,
                              f"aria-pressed must never be derived from the pending/desired value: {line!r}")
            self.assertTrue("doc" in line or "appliedSymbols" in line,
                             f"aria-pressed must be derived from the applied doc: {line!r}")
        # is-desired (the pending indicator) is a separate class toggle, never folded into aria-pressed.
        self.assertIn('classList.toggle("is-desired"', fn)


def _wrap_with_db_stub(panel_html, seed_docs):
    """Wraps rendered panel HTML with a stub window.claude whose db.doc().onSnapshot() fires once,
    synchronously, with the seeded doc (or exists:false if unseeded) -- and whose .set() records every
    write instead of performing one. Mirrors exactly what the bug report's own reproduction harness did."""
    stub = ("<script>\n"
            "window.__seedDocs = " + json.dumps(seed_docs) + ";\n"
            "window.__writes = [];\n"
            "window.claude = {\n"
            "  use: function () {\n"
            "    return Promise.resolve({\n"
            "      doc: function (path) {\n"
            "        return {\n"
            "          set: function (data) {\n"
            "            window.__writes.push({path: path, data: JSON.parse(JSON.stringify(data))});\n"
            "            return Promise.resolve();\n"
            "          },\n"
            "          onSnapshot: function (onNext) {\n"
            "            var seed = window.__seedDocs[path];\n"
            "            if (seed && seed.exists) {\n"
            "              onNext({exists: true, data: function () { return seed.data; }});\n"
            "            } else {\n"
            "              onNext({exists: false, data: function () { return {}; }});\n"
            "            }\n"
            "            return function () {};\n"
            "          }\n"
            "        };\n"
            "      }\n"
            "    });\n"
            "  }\n"
            "};\n"
            "</script>")
    return "<!doctype html><html><head><meta charset='utf-8'></head><body>" + stub + "\n" + panel_html + "\n</body></html>"


def _wrap_with_db_stub_rejecting_writes(panel_html, seed_docs, error_code):
    """Same contract as _wrap_with_db_stub, except every .set() call rejects with {code: error_code} --
    for reproducing handleWriteError's branches in a real browser instead of only grepping its source."""
    stub = ("<script>\n"
            "window.__seedDocs = " + json.dumps(seed_docs) + ";\n"
            "window.__writes = [];\n"
            "window.claude = {\n"
            "  use: function () {\n"
            "    return Promise.resolve({\n"
            "      doc: function (path) {\n"
            "        return {\n"
            "          set: function (data) {\n"
            "            window.__writes.push({path: path, data: JSON.parse(JSON.stringify(data))});\n"
            "            return Promise.reject({code: " + json.dumps(error_code) + "});\n"
            "          },\n"
            "          onSnapshot: function (onNext) {\n"
            "            var seed = window.__seedDocs[path];\n"
            "            if (seed && seed.exists) {\n"
            "              onNext({exists: true, data: function () { return seed.data; }});\n"
            "            } else {\n"
            "              onNext({exists: false, data: function () { return {}; }});\n"
            "            }\n"
            "            return function () {};\n"
            "          }\n"
            "        };\n"
            "      }\n"
            "    });\n"
            "  }\n"
            "};\n"
            "</script>")
    return "<!doctype html><html><head><meta charset='utf-8'></head><body>" + stub + "\n" + panel_html + "\n</body></html>"


@unittest.skipUnless(_PLAYWRIGHT_AVAILABLE, "playwright not installed -- browser reproduction skipped")
class BrowserOverTimeBehaviour(unittest.TestCase):
    """Reproduces, in a real browser, the exact two defects reported against the published panel: a tap
    that ends up looking like nothing happened once the write succeeds (Defect 1), and a missing applied
    snapshot silently turning a preset tap into an instruments:[] write even though the page was baked
    with real symbols selected (Defect 2). Attribute/structure assertions never caught either -- both only
    show up over time, in a browser, which is what this class drives."""

    @classmethod
    def setUpClass(cls):
        if not _PLAYWRIGHT_AVAILABLE:
            return
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        if not _PLAYWRIGHT_AVAILABLE:
            return
        cls._browser.close()
        cls._pw.stop()

    def _open(self, config, applied_seed):
        html = mp.render(config)
        seed = {}
        if applied_seed is not None:
            seed["control/applied.crypto"] = {"exists": True, "data": applied_seed}
        page_html = _wrap_with_db_stub(html, seed)
        path = tempfile.mktemp(suffix=".html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page_html)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        page = self._browser.new_page()
        self.addCleanup(page.close)
        page.goto("file://" + path)
        page.wait_for_timeout(150)
        return page

    def test_pending_card_state_survives_a_successful_write_before_the_applier_catches_up(self):
        """Defect 1: previously, flushWrite's success handler nulled pendingDesired, so the card lost its
        'is-desired' class the moment the write landed -- 400ms after the tap, well before the applier
        (which runs on its own ~5-minute cron) could ever confirm anything."""
        nine = I.analysis("crypto")
        page = self._open(cfg(crypto_syms=nine), applied_seed={
            "preset": "wyckoff", "instruments": nine,
            "applied_at": "2026-09-12T09:00:00Z", "requested_at": "2026-09-12T08:59:00Z"})
        card_sel = '.preset-card[data-market="crypto"][data-preset="wyckoff+ict"]'
        page.click(card_sel)
        page.wait_for_timeout(600)  # past the 400ms debounce -- the write has landed
        classes = page.eval_on_selector(card_sel, "el => el.className")
        self.assertIn("is-desired", classes,
                       "the card must still show its own pending state once the write succeeds -- "
                       "it must not revert to looking untouched")
        status = page.eval_on_selector('.request-status[data-market="crypto"]', "el => el.textContent")
        self.assertIn("đang chờ áp dụng", status)

    def test_preset_tap_with_no_applied_doc_does_not_empty_the_instruments(self):
        """Defect 2: with the applied doc reported exists:false (its snapshot fires once, synchronously,
        like the real db contract), a preset tap must not send instruments:[] even though the page was
        baked with real symbols selected and the null snapshot has already repainted every chip
        aria-pressed=false."""
        nine = I.analysis("crypto")
        page = self._open(cfg(crypto_syms=nine), applied_seed=None)
        selected_before = page.eval_on_selector_all(
            '.chip-item[data-market="crypto"] .chip[aria-pressed="true"]', "els => els.length")
        self.assertEqual(selected_before, 0,
                          "sanity check: the null applied snapshot repaints chips unselected, matching "
                          "the reported production behaviour")
        card_sel = '.preset-card[data-market="crypto"][data-preset="wyckoff+ict"]'
        page.click(card_sel)
        page.wait_for_timeout(600)
        writes = page.evaluate("window.__writes")
        self.assertEqual(len(writes), 1)
        self.assertNotEqual(writes[0]["data"]["instruments"], [],
                             "a preset tap must never write an empty instruments list by ignorance -- "
                             "an empty list must only ever be sent because the user explicitly "
                             "unticked everything")
        self.assertEqual(sorted(writes[0]["data"]["instruments"]), sorted(nine))

    def test_tapping_the_already_applied_preset_still_sends_a_write(self):
        """Browser-sweep defect (2026-09-12): a tap on the card that is ALREADY the applied preset used to
        be silently swallowed -- reconcilePending(), run as part of the old renderMarket() called
        synchronously right after the tap, saw that the freshly-set pendingDesired already matched
        applied[market] and cleared it before scheduleWrite()'s debounce timer ever fired, so flushWrite()
        found nothing pending and never wrote. The card showed zero reaction and the tap produced zero
        write -- exactly the 'a tap must never look like nothing happened' failure this file's other
        Defect-1/2 fixes already guard against, just from a local tap instead of a write success. Fixed by
        painting immediately from onPresetClick/onChipClick (paintMarket(), no reconcile) and only
        reconciling on paths that receive new information (a snapshot, or a settled write)."""
        nine = I.analysis("crypto")
        page = self._open(cfg(crypto_syms=nine), applied_seed={
            "preset": "wyckoff+ict", "instruments": nine,
            "applied_at": "2026-09-12T09:00:00Z", "requested_at": "2026-09-12T08:59:00Z"})
        card_sel = '.preset-card[data-market="crypto"][data-preset="wyckoff+ict"]'
        page.click(card_sel)
        page.wait_for_timeout(600)  # past the 400ms debounce
        writes = page.evaluate("window.__writes")
        self.assertEqual(len(writes), 1,
                          "tapping the currently-applied preset must still send the full desired set -- "
                          "PANEL-10 says every write is the full state, never a delta, and the APPLIER "
                          "(not the page) is the one that decides a resend is a no-op (CFG-13)")
        self.assertEqual(writes[0]["data"]["preset"], "wyckoff+ict")
        self.assertEqual(sorted(writes[0]["data"]["instruments"]), sorted(nine))

    def test_a_generic_write_failure_status_is_not_immediately_overwritten(self):
        """Browser-sweep defect (2026-09-12): handleWriteError's generic-failure branch used to call
        setRequestStatus(market, 'send-failed', ...) directly and then call renderMarket(market) right
        after -- renderMarket's own updateStatusLine() recomputed the line from applied/request/pending in
        that SAME synchronous call and overwrote the failure text (falling back to 'đã áp dụng...' since
        the applied doc was untouched by the failed write) before the user could ever read it. Fixed by
        routing the failure through a sendFailed[market] flag that updateStatusLine() itself checks, so
        there is exactly one write to the status line per repaint."""
        nine = I.analysis("crypto")
        page = self._open_rejecting(cfg(crypto_syms=nine), applied_seed={
            "preset": "wyckoff+ict", "instruments": nine,
            "applied_at": "2026-09-12T09:00:00Z", "requested_at": "2026-09-12T08:59:00Z"},
            error_code="some_unrecognised_code")
        card_sel = '.preset-card[data-market="crypto"][data-preset="ict"]'
        page.click(card_sel)
        page.wait_for_timeout(600)
        status = page.eval_on_selector('.request-status[data-market="crypto"]', "el => el.textContent")
        self.assertIn("gửi thất bại", status,
                       "a genuine send failure must stay visible on the status line, not be silently "
                       "reverted to the old 'applied' text by the very same repaint that set it")

    def _open_rejecting(self, config, applied_seed, error_code):
        html = mp.render(config)
        seed = {}
        if applied_seed is not None:
            seed["control/applied.crypto"] = {"exists": True, "data": applied_seed}
        page_html = _wrap_with_db_stub_rejecting_writes(html, seed, error_code)
        path = tempfile.mktemp(suffix=".html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page_html)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        page = self._browser.new_page()
        self.addCleanup(page.close)
        page.goto("file://" + path)
        page.wait_for_timeout(150)
        return page


class HeartbeatInteraction(unittest.TestCase):
    def test_pending_across_markets_excludes_resolved_refused_requests(self):
        """A refused request is resolved (requested_at advanced by the applier) and must not be
        counted as 'pending for N minutes' in the stale-heartbeat banner -- only requestMatchesApplied()
        was checked before, which is false for both pending AND refused."""
        fn = _js_function_source(mp._SCRIPT, "pendingStatusAcrossMarkets")
        self.assertIn("resolveRequestOutcome", fn)
        self.assertNotIn("requestMatchesApplied(market)", fn)


class AppliedDocShape(unittest.TestCase):
    def test_valid_doc_extracts_the_applier_result_fields(self):
        """Without these, resolveRequestOutcome() has no reason to work with -- the applied snapshot
        must carry preset_result/instruments_result/error through from db, not just preset/instruments."""
        fn = _js_function_source(mp._SCRIPT, "validDoc")
        for key in ("preset_result", "instruments_result", "error"):
            self.assertIn(key, fn)


class RefusalDisplay(unittest.TestCase):
    def test_generic_refusal_copy_is_present(self):
        html = mp.render(cfg())
        self.assertIn("bị từ chối", html)

    def test_refused_status_has_its_own_visual_treatment_distinct_from_pending_and_applied(self):
        html = mp.render(cfg())
        self.assertRegex(html, r'\.request-status\[data-status="refused"\]')


class HeartbeatBannerInvariants(unittest.TestCase):
    """The two properties the coordinator required for the PANEL-05 close, checked structurally:
    both involve live db snapshots and DOM state that need a real browser to execute end-to-end."""

    def test_staleness_warning_becomes_visible_before_any_duration_classification(self):
        """Property 1: a nonsense duration must never suppress the staleness banner -- it may only
        replace the *number* inside it, never the warning itself."""
        fn = _js_function_source(mp._SCRIPT, "renderHeartbeatBanner")
        self.assertRegex(fn, r"el\.hidden\s*=\s*false")
        hidden_idx = fn.index("el.hidden = false")
        status_idx = fn.index("pendingStatusAcrossMarkets")
        self.assertLess(hidden_idx, status_idx,
                         "the banner must become visible before it looks at the pending duration")

    def test_guard_copy_is_present(self):
        html = mp.render(cfg())
        self.assertIn("đồng hồ thiết bị lệch", html)

    def test_applied_status_is_never_a_function_of_the_device_clock(self):
        """Property 2: a skewed clock must not make the page look healthy. resolveRequestOutcome()
        -- the sole decision for "applied" vs "refused" vs "pending", and the only thing that gates
        "đã áp dụng" now -- must never read Date.now() or call the clock guard, so a bad clock can
        never manufacture a false applied (or refused) state. Checked against the WHOLE
        REQUEST_OUTCOME_GUARD block, i.e. resolveRequestOutcome's own transitive closure
        (refusalReasonText, mapOrGeneric, sameInstrumentSet), not just its own top-level body -- a
        clock read added inside a helper it calls would still be caught here.

        Pinned to resolveRequestOutcome(), not to requestMatchesApplied() (deleted: nothing called
        it once this function took over the live decision -- confirmed by
        `grep -n requestMatchesApplied scripts/method-panel.py` before removal). A test asserting
        this property against dead code would stay green forever even if the live path grew a
        clock dependency tomorrow."""
        guard_src = _request_outcome_guard_source()
        self.assertNotIn("Date.now", guard_src)
        self.assertNotIn("classifyElapsedMs", guard_src)


class PageIdentity(unittest.TestCase):
    def test_page_carries_a_title_within_the_first_8kb(self):
        """The Artifact tool scans only the first 8KB for <title> and otherwise names the artifact after the
        file, i.e. '.method-panel.html'. The title is how this page is found in a gallery."""
        html = mp.render(cfg())
        head = html[:8192]
        self.assertIn("<title>", head)
        self.assertIn(mp.TITLE, head)


class RenderedCopyStandingCheck(unittest.TestCase):
    """The words a human actually reads, tags stripped -- the check that caught the honesty-line,
    runner-list, mojibake label, and literal-backtick defects that every attribute/structure assertion
    above missed. Kept as a standing regression guard, not a one-off."""

    def _visible_text(self, html):
        no_script = re.sub(r"<script[\s\S]*?</script>", " ", html)
        no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script)
        return re.sub(r"<[^>]+>", " ", no_style)

    def test_no_raw_backticks_reach_the_visible_text(self):
        """Markdown backticks inserted as plain text render literally -- scripts/wyckoff_rules.py and
        strategy-runner.py:167 must be marked up (e.g. <code>), never shown with their backticks."""
        html = mp.render(cfg(env="real"))  # real env renders the other backtick-bearing note
        text = self._visible_text(mp.render(cfg())) + self._visible_text(html)
        self.assertNotIn("`", text)

    def test_full_preset_label_is_proper_vietnamese_not_mojibake_ascii(self):
        html = mp.render(cfg())
        self.assertIn("Đầy đủ 4 chiều", html)
        self.assertNotIn("Day du 4 chieu", html)


class NoInjection(unittest.TestCase):
    def test_no_cdn_and_no_external_fetch(self):
        html = mp.render(cfg())
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))
        for bad in ("cdnjs", "jsdelivr", "unpkg", "googleapis"):
            self.assertNotIn(bad, html)

    def test_generated_page_has_no_doctype_or_html_wrapper(self):
        """The Artifact tool wraps the file; the page must not bring its own skeleton."""
        html = mp.render(cfg())
        self.assertNotIn("<!doctype", html.lower())
        self.assertNotIn("<html", html.lower())
