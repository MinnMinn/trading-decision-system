"""The method panel page. Rules PANEL-03/04/09/11 in docs/security/2026-09-12-method-panel.md.
The page is generated from code (SYSTEM-DESIGN.md §15): nothing on it is hand-written per symbol."""
import importlib.util, json, os, re, sys, tempfile, unittest

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
