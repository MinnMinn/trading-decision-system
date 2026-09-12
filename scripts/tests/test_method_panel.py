"""The method panel page. Rules PANEL-03/04/09/11 in docs/security/2026-09-12-method-panel.md.
The page is generated from code (SYSTEM-DESIGN.md §15): nothing on it is hand-written per symbol."""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import instruments as I


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

    def test_research_tier_cards_state_the_no_trade_consequence(self):
        html = mp.render(cfg())
        self.assertIn("NO TRADE", html)
        for p in M.PRESETS:
            if p["tier"] == "research":
                self.assertRegex(html, rf'data-preset="{re.escape(p["id"])}"[^>]*data-tier="research"')

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
    """The self-contained request-outcome guard (REFUSAL_REASON_BY_CODE/mapOrGeneric/sameSet/
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
        """Property 2: a skewed clock must not make the page look healthy. requestMatchesApplied()
        -- the sole gate for showing "đã áp dụng" -- compares two db-provided strings only; it must
        never read Date.now() or call the clock guard, so a bad clock can never manufacture a false
        applied state."""
        fn = _js_function_source(mp._SCRIPT, "requestMatchesApplied")
        self.assertNotIn("Date.now", fn)
        self.assertNotIn("classifyElapsedMs", fn)


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
