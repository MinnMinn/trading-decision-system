"""Bias is a per-method reading, not a Wyckoff monopoly (user decision 2026-09-13).

Before this, htf_context.bias_of() derived bias ONLY from the Wyckoff structure/phase read, so turning Wyckoff
off in /automation left the Wyckoff narrative still deciding every verdict (and, with no narrative at all, every
tier fell to "unknown" instead of falling back to ICT). ICT has its own directional bias and always did:

  - the draw on liquidity: a body close THROUGH the previous candle's high/low means that level was the draw,
    expect continuation; a wick through with the body failing to close beyond is FAILURE TO DISPLACE, so the
    opposite level becomes the new draw (knowledge/ict/core-a.md §2.11 PCH/PCL, §2.12 PDH/PDL, §2.14, §3.2 R5-R8);
  - structural falsification: the last confirmed MSS on that timeframe, by body close (knowledge/ict/core-b.md §2.2).

Per-tier mapping (user decision): each tier reads the previous candle OF ITS OWN TIMEFRAME — which on a 1D tier
is the previous day (PDH/PDL) and on an intraday tier is the previous candle (PCH/PCL).

Cross-method rule (user decision): wyckoff+ict disagreeing is a Contradiction to RAISE, not to resolve quietly
(.claude/skills/ict-skill/SKILL.md:23) -> neutral, and the basis must say so.
"""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def facts(pch_state="intact", pcl_state="intact", mss=None, tf="1h", last=100.0):
    """A tier's facts.json entry, trimmed to what bias_of reads. `mss` here always represents a genuine,
    displaced MSS (these tests are about bias interpretation, not about ICT-4/5's displacement filtering,
    which scripts/tests/test_audit_round2_ict.py covers directly) -- so it is set on BOTH `last_mss` (display,
    ict-scan.py) and `last_displaced_mss` (the field ict_bias actually reads since ICT-5)."""
    return {"last": last, "last_mss": mss, "last_displaced_mss": mss,
            "prev_candle": {"tf": tf, "pch": 110.0, "pcl": 90.0, "pch_state": pch_state, "pcl_state": pcl_state}}


ACC_C = {"structure": "tái tích lũy", "phase": "C"}          # -> wyckoff long
DIST_C = {"structure": "phân phối", "phase": "C"}            # -> wyckoff short


class BasisRender:
    """A basis is DATA -- a list of (tag, message key, params). Tests that are about WHICH reading was chosen
    assert on the key; tests about what the sentence must contain render it in a named locale first."""

    def render(self, basis, lang="vi"):
        return self.htf.basis_text(basis, lang)


class IctBias(BasisRender, unittest.TestCase):
    def setUp(self):
        self.htf = load("htf_context.py")

    def test_body_close_through_previous_high_is_the_draw_and_reads_long(self):
        bias, basis = self.htf.ict_bias(facts(pch_state="closed_through"))
        self.assertEqual(bias, "long")
        self.assertIn("110", self.render(basis))

    def test_body_close_through_previous_low_reads_short(self):
        self.assertEqual(self.htf.ict_bias(facts(pcl_state="closed_through"))[0], "short")

    def test_wick_through_high_with_body_failing_is_failure_to_displace_and_reads_short(self):
        bias, basis = self.htf.ict_bias(facts(pch_state="swept"))
        self.assertEqual(bias, "short")
        self.assertEqual([k for _, k, _ in basis], ["bias.ict.failed_displace"])

    def test_wick_through_low_with_body_failing_reads_long(self):
        self.assertEqual(self.htf.ict_bias(facts(pcl_state="swept"))[0], "long")

    def test_both_levels_closed_through_is_neutral(self):
        self.assertEqual(self.htf.ict_bias(facts(pch_state="closed_through", pcl_state="closed_through"))[0], "neutral")

    def test_untouched_previous_candle_leaves_the_draw_unresolved(self):
        self.assertEqual(self.htf.ict_bias(facts())[0], "unknown")

    def test_mss_alone_sets_the_bias_when_the_draw_is_unresolved(self):
        self.assertEqual(self.htf.ict_bias(facts(mss={"type": "bull", "level": 99.0}))[0], "long")

    def test_draw_and_mss_disagreeing_is_neutral(self):
        bias, basis = self.htf.ict_bias(facts(pch_state="closed_through", mss={"type": "bear", "level": 99.0}))
        self.assertEqual(bias, "neutral")
        self.assertEqual(basis[0][1], "bias.ict.contradiction")

    def test_daily_tier_names_the_level_pdh_not_pch(self):
        self.assertIn("PDH", self.render(self.htf.ict_bias(facts(pch_state="closed_through", tf="1D"))[1]))

    def test_intraday_tier_names_the_level_pch(self):
        self.assertIn("PCH", self.render(self.htf.ict_bias(facts(pch_state="closed_through", tf="1h"))[1]))

    def test_no_prev_candle_at_all_is_unknown(self):
        self.assertEqual(self.htf.ict_bias({"last": 100.0})[0], "unknown")


class BiasOfPerMethod(BasisRender, unittest.TestCase):
    def setUp(self):
        self.htf = load("htf_context.py")

    def test_defaults_to_wyckoff_only_so_existing_callers_are_unchanged(self):
        # the checkers call bias_of() with two args; step 6 plumbs dims to them deliberately.
        self.assertEqual(self.htf.bias_of(ACC_C, facts(pch_state="closed_through"))[0], "long")
        self.assertEqual(self.htf.bias_of(DIST_C, facts(pch_state="closed_through"))[0], "short")

    def test_ict_only_ignores_the_wyckoff_read_entirely(self):
        # THE regression: Wyckoff says long, ICT draw says short, ICT-only mode must read short.
        bias, basis = self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=("ict",))
        self.assertEqual(bias, "short")
        self.assertNotIn("wyckoff", {tag for tag, _, _ in basis})

    def test_ict_only_with_no_wyckoff_read_still_produces_a_bias(self):
        # Previously this fell to "unknown" and silently rejected every pilot setup.
        self.assertEqual(self.htf.bias_of(None, facts(pcl_state="swept"), methods=("ict",))[0], "long")

    def test_wyckoff_only_ignores_the_ict_draw(self):
        self.assertEqual(self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=("wyckoff",))[0], "long")

    def test_both_engaged_and_agreeing_keeps_the_direction(self):
        bias, basis = self.htf.bias_of(ACC_C, facts(pcl_state="swept"), methods=("wyckoff", "ict"))
        self.assertEqual(bias, "long")

    def test_both_engaged_and_disagreeing_is_neutral_and_names_the_contradiction(self):
        bias, basis = self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=("wyckoff", "ict"))
        self.assertEqual(bias, "neutral")
        self.assertEqual(basis[0][1], "bias.contradiction_two")
        self.assertEqual({tag for tag, _, _ in basis[1:]}, {"wyckoff", "ict"})

    def test_both_engaged_but_one_silent_uses_the_other(self):
        self.assertEqual(self.htf.bias_of(ACC_C, facts(), methods=("wyckoff", "ict"))[0], "long")
        self.assertEqual(self.htf.bias_of(None, facts(pcl_state="swept"), methods=("wyckoff", "ict"))[0], "long")

    def test_no_method_engaged_is_unknown(self):
        self.assertEqual(self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=())[0], "unknown")


class IctBiasVocabularyIsPure(unittest.TestCase):
    """The basis is shown on the page and fed to the model brief; an ICT bias may not carry Wyckoff words
    (method_purity.RULES['ict']) or the method switch leaks straight back in through the explanation.

    Checked in EVERY locale since 2026-09-17. The English wording is where this is easiest to get wrong: the
    idiomatic translation of "kỳ vọng tiếp diễn tăng" is "expect continued markup", and `markup` is a Wyckoff
    term. One locale passing proves nothing about the other."""

    def setUp(self):
        self.htf = load("htf_context.py")
        self.mp = load("method_purity.py")
        self.i18n = load("i18n.py")

    def test_every_ict_basis_is_pure_ict_vocabulary_in_every_locale(self):
        cases = [facts(pch_state="closed_through"), facts(pcl_state="closed_through"), facts(pch_state="swept"),
                 facts(pcl_state="swept"), facts(mss={"type": "bull", "level": 99.0}), facts(tf="1D", pch_state="swept"),
                 facts(pch_state="closed_through", pcl_state="closed_through"), facts()]
        for f in cases:
            for lang in self.i18n.LOCALES:
                text = self.htf.basis_text(self.htf.ict_bias(f)[1], lang)
                self.assertEqual(self.mp.violations(text, "ict"), [], f"impure ICT basis [{lang}]: {text}")

    def test_every_wyckoff_basis_is_pure_wyckoff_vocabulary_in_every_locale(self):
        """The mirror case, which had no test at all before: a Wyckoff basis may not reach for a liquidity word."""
        cases = [(ACC_C, facts()), (DIST_C, facts()), ({"structure": "tích lũy", "phase": "B"}, facts()),
                 ({"structure": "chưa xác lập", "phase": "A"}, facts()), (None, facts())]
        for wy, f in cases:
            for lang in self.i18n.LOCALES:
                text = self.htf.basis_text(self.htf.wyckoff_bias(wy, f)[1], lang)
                self.assertEqual(self.mp.violations(text, "wyckoff"), [], f"impure Wyckoff basis [{lang}]: {text}")


class BiasMethodsFromTheSwitch(unittest.TestCase):
    """`/automation dimension <m> off` has to reach the bias, not just the columns that get drawn. The flag
    semantics mirror build-artifact.py's own (`flag is not False` -> engaged), so an absent key means on."""

    def setUp(self):
        self.htf = load("htf_context.py")

    def cfg(self, market, dims):
        return {"markets": {market: {"dimensions": dims}}}

    def test_ict_only_market_yields_ict_only(self):
        self.assertEqual(self.htf.engaged_methods("scalping", self.cfg("crypto", {"wyckoff": False, "ict": True})), ("ict",))

    def test_wyckoff_only_market_yields_wyckoff_only(self):
        self.assertEqual(self.htf.engaged_methods("scalping", self.cfg("crypto", {"wyckoff": True, "ict": False})), ("wyckoff",))

    def test_both_on_yields_both_in_a_stable_order(self):
        self.assertEqual(self.htf.engaged_methods("scalping", self.cfg("crypto", {"wyckoff": True, "ict": True})), ("wyckoff", "ict"))

    def test_all_off_yields_nothing(self):
        self.assertEqual(self.htf.engaged_methods("scalping", self.cfg("crypto", {"wyckoff": False, "ict": False})), ())

    def test_absent_flag_counts_as_engaged(self):
        self.assertEqual(self.htf.engaged_methods("scalping", self.cfg("crypto", {})), ("wyckoff", "ict"))

    def test_cfd_prefixed_styles_read_the_cfd_market(self):
        """The two markets share all three horizon words, so the `cfd-` prefix is the ONLY thing that routes a
        flat style name to a market's dimension flags (automation.market_of_style). Same horizon, both markets."""
        cfg = {"markets": {"crypto": {"dimensions": {"wyckoff": False, "ict": True}},
                           "cfd": {"dimensions": {"wyckoff": True, "ict": False}}}}
        self.assertEqual(self.htf.engaged_methods("cfd-scalping", cfg), ("wyckoff",))
        self.assertEqual(self.htf.engaged_methods("scalping", cfg), ("ict",))


class BriefLinesFollowTheSwitch(unittest.TestCase):
    """The model brief is where the leak did the most damage: local-eval-brief.py handed Sonnet a Wyckoff
    structure/phase read and a Wyckoff-derived BIAS to obey, in every run, whatever /automation said."""

    def setUp(self):
        self.htf = load("htf_context.py")

    def ctx(self):
        return {"tf": "1h", "style": "day", "scanned_at": "2026-09-12T18:00:00Z", "last_time": "2026-09-12T18:00:00Z",
                "last": 100.0, "lo": 90.0, "hi": 110.0, "eq": 100.0, "pct": 0.5, "stance": "CHỜ", "verdict": None,
                "anchors": [], "last_mss": {"type": "bear", "level": 99.0},
                "wyckoff": {"structure": "tái tích lũy", "phase": "C", "updated": "2026-09-12T15:02:00Z"},
                "wyckoff_source": "data/live/narrative/day.json", "bias": "short", "basis": [("ict", "bias.ict.nothing", {})]}

    def test_ict_only_brief_does_not_print_the_wyckoff_read(self):
        joined = " ".join(self.htf.brief_lines(self.ctx(), str, methods=("ict",)))
        self.assertNotIn("Wyckoff", joined)
        self.assertIn("BIAS", joined)

    def test_wyckoff_engaged_brief_still_prints_the_wyckoff_read(self):
        joined = " ".join(self.htf.brief_lines(self.ctx(), str, methods=("wyckoff",)))
        self.assertIn("Wyckoff", joined)

    def anchor_ctx(self):
        c = self.ctx()
        c["anchors"] = [{"label": "SC mới (Cao trào bán), khối lượng kỷ lục", "short": "SC", "method": "wyckoff",
                         "price": 76676.0, "ref_vs": "above", "dist_pct": 0.66},
                        {"label": "BSL cụm đỉnh bằng nhau", "short": "BSL", "method": "ict",
                         "price": 77425.0, "ref_vs": "below", "dist_pct": -0.32}]
        return c

    def test_disengaged_methods_anchors_are_given_by_price_without_their_name(self):
        # The level still matters to an ICT read; its Wyckoff NAME does not, and feeding it in is the same leak
        # (local-eval-brief.py mục 6: "Mốc neo có tên Wyckoff (SC, AR…) chỉ được gọi bằng giá").
        joined = " ".join(self.htf.brief_lines(self.anchor_ctx(), lambda v: f"{v:,.0f}", methods=("ict",)))
        self.assertIn("76,676", joined)
        self.assertNotIn("Cao trào bán", joined)
        self.assertNotIn("SC", joined)

    def test_anchor_without_a_method_field_is_classified_by_its_label(self):
        # facts.json written before the scanner carried `method` through: fall back to the label, exactly as
        # build-artifact.anchor_method does, so old files are handled instead of leaking.
        c = self.ctx()
        c["anchors"] = [{"label": "Đáy Spring — xuyên xuống dưới SC rồi đóng cửa hồi phục", "short": None,
                         "price": 76464.0, "ref_vs": "above", "dist_pct": 0.94}]
        joined = " ".join(self.htf.brief_lines(c, lambda v: f"{v:,.0f}", methods=("ict",)))
        self.assertIn("76,464", joined)
        self.assertNotIn("Spring", joined)

    def test_engaged_methods_anchors_keep_their_names(self):
        joined = " ".join(self.htf.brief_lines(self.anchor_ctx(), lambda v: f"{v:,.0f}", methods=("ict",)))
        self.assertIn("BSL", joined)

    def test_ladder_lines_pass_the_engaged_methods_down(self):
        # ladder_lines is what local-eval-brief.py actually calls; it must not widen the set again.
        self.assertIn("methods", self.htf.ladder_lines.__code__.co_varnames)


def candles(n=30, base=100.0):
    """Flat, boring candles — the tests below shape only the last two, which is all prev_candle reads."""
    return [{"time": f"2026-09-12T{h:02d}:00:00Z", "open": base, "high": base + 1, "low": base - 1,
             "close": base, "volume": 10.0} for h in range(n)]


class PrevCandleFacts(unittest.TestCase):
    """The draw levels ICT reads its bias from have to survive the scan into facts.json. They were computed
    (prev_day, ict-scan.py) and then dropped from the persisted payload, so htf_context could never see them."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def analyze(self, prev, cur, tf="1h"):
        c = candles()
        c[-2].update(prev); c[-1].update(cur)
        return self.scan.analyze(c, 5, tf=tf)["prev_candle"]

    def test_prev_candle_is_stamped_with_the_timeframe_it_was_read_on(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 105, "low": 95, "close": 100}, tf="4h")
        self.assertEqual((pc["tf"], pc["pch"], pc["pcl"]), ("4h", 110, 90))

    def test_body_close_above_previous_high_is_closed_through(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 115, "low": 100, "close": 112})
        self.assertEqual(pc["pch_state"], "closed_through")

    def test_wick_above_previous_high_closing_back_is_swept(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 115, "low": 100, "close": 105})
        self.assertEqual(pc["pch_state"], "swept")

    def test_untouched_previous_high_is_intact(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 108, "low": 100, "close": 105})
        self.assertEqual(pc["pch_state"], "intact")

    def test_body_close_below_previous_low_is_closed_through(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 100, "low": 85, "close": 88})
        self.assertEqual(pc["pcl_state"], "closed_through")

    def test_wick_below_previous_low_closing_back_is_swept(self):
        pc = self.analyze({"high": 110, "low": 90}, {"high": 100, "low": 85, "close": 95})
        self.assertEqual(pc["pcl_state"], "swept")


def shaped_candles(n=40, base=100.0):
    """Candles with a real swing, a gap and a volume spike, so every per-method computation has something to find."""
    c = candles(n, base)
    for i, x in enumerate(c):
        x["high"] = base + 1 + (i % 7); x["low"] = base - 1 - (i % 5); x["close"] = base + (i % 3)
    c[20].update(high=base + 12, low=base + 8, close=base + 11)      # displacement leaving a gap
    c[21].update(high=base + 20, low=base + 14, close=base + 19)
    c[22].update(high=base + 26, low=base + 22, close=base + 25)
    c[30].update(volume=100.0)                                        # volume outlier for the Wyckoff lane
    return c


class ScannerSkipsDisengagedMethods(unittest.TestCase):
    """Turning a dimension off must stop the work, not just hide the column: the FVG-mitigation and pool-sweep
    scans are the quadratic part of analyze(), and the volume-outlier scan is the Wyckoff-only part. Paying for
    a read nothing will display slows down the methods that ARE on (user decision 2026-09-13)."""

    def setUp(self):
        self.scan = load("ict-scan.py")

    def test_default_still_computes_both_lanes(self):
        a = self.scan.analyze(shaped_candles(), 20, tf="1h")
        self.assertTrue(a["fvgs_all"] or a["pools"])
        self.assertTrue([e for e in a["events"] if e["kind"] == "volume"])

    def test_wyckoff_only_skips_the_ict_structures(self):
        a = self.scan.analyze(shaped_candles(), 20, tf="1h", methods=("wyckoff",))
        self.assertEqual(a["fvgs_all"], [])
        self.assertEqual(a["pools"], [])
        self.assertEqual(a["mss"], [])
        self.assertIsNone(a["last_mss"])
        self.assertIsNone(a["nearest_fvg"])
        self.assertIsNone(a["prev_candle"])
        self.assertEqual([e for e in a["events"] if e["kind"] in ("sweep", "mss_bull", "mss_bear", "fvg_bull", "fvg_bear")], [])

    def test_wyckoff_only_keeps_the_volume_events_it_owns(self):
        a = self.scan.analyze(shaped_candles(), 20, tf="1h", methods=("wyckoff",))
        self.assertTrue([e for e in a["events"] if e["kind"] == "volume"])

    def test_ict_only_skips_the_volume_scan(self):
        a = self.scan.analyze(shaped_candles(), 20, tf="1h", methods=("ict",))
        self.assertEqual([e for e in a["events"] if e["kind"] == "volume"], [])

    def test_ict_only_keeps_its_own_structures(self):
        a = self.scan.analyze(shaped_candles(), 20, tf="1h", methods=("ict",))
        self.assertIsNotNone(a["prev_candle"])

    def test_shared_window_facts_survive_either_way(self):
        # last / window extremes are neither method's property; consumers read them unconditionally.
        for ms in (("wyckoff",), ("ict",), ()):
            a = self.scan.analyze(shaped_candles(), 20, tf="1h", methods=ms)
            self.assertIsNotNone(a["last"], ms)
            self.assertIsNotNone(a["lo"], ms)
            self.assertIsNotNone(a["hi"], ms)
            self.assertIsNotNone(a["pct"], ms)


class FactsEntryPersistsTheDrawLevels(unittest.TestCase):
    def setUp(self):
        self.scan = load("ict-scan.py")

    def test_persisted_facts_entry_carries_prev_candle_and_prev_day(self):
        a = self.scan.analyze(candles(), 5, tf="1h")
        entry = self.scan.facts_entry(a, "CHỜ", None, None, None)
        self.assertIn("prev_candle", entry)
        self.assertEqual(entry["prev_candle"]["tf"], "1h")
        self.assertIn("prev_day", entry)


class StoredBasisFormat(unittest.TestCase):
    """`context.basis` is written into data/live/prelim/<style>.facts.json and into the point-in-time research
    snapshots under data/live/model-reads/**. The bilingual work changed its shape from a rendered sentence to
    a keyed list, so CLAUDE.md §59 applies: the old shape stays on disk, must stay readable, and the change
    must be auditable rather than implicit.
    """

    def setUp(self):
        self.htf = load("htf_context.py")

    def test_a_format_1_basis_still_reads(self):
        """Format 1 is a finished sentence in the authoring locale. Returned as written -- shown, not crashed
        on, and not machine-translated into a language it was not written in."""
        old = "khung lớn tích lũy pha C — tìm Spring[C]/LPS[C]"
        for lang in ("en", "vi"):
            self.assertEqual(self.htf.basis_text(old, lang), old)

    def test_the_stored_shape_carries_its_version(self):
        self.assertEqual(self.htf.BASIS_FORMAT, 2)

    def test_the_structure_word_never_reaches_a_sentence_untranslated(self):
        """A word outside the known vocabulary is the narrative's own Vietnamese. In English mode it must be
        marked as a quotation, never dropped in bare as though it were English."""
        bias, basis = self.htf.wyckoff_bias({"structure": "Đi ngang", "phase": "C"}, {"last": 1.0})
        en = self.htf.basis_text(basis, "en")
        self.assertIn("“đi ngang”", en)
        self.assertIn("as written", en)

    def test_a_missing_structure_word_reads_as_not_established(self):
        """It used to interpolate an empty string: "higher timeframe phase A () — stopping action…"."""
        _, basis = self.htf.wyckoff_bias({"structure": "", "phase": "A"}, {"last": 1.0})
        self.assertIn("(not established)", self.htf.basis_text(basis, "en"))
        self.assertIn("(chưa xác lập)", self.htf.basis_text(basis, "vi"))

    def test_the_structure_word_still_decides_direction_by_the_stored_value(self):
        """The display change must not touch the matching. Both spellings of accumulation still read long."""
        for word in ("tích lũy", "tích luỹ", "tái tích lũy"):
            self.assertEqual(self.htf.wyckoff_bias({"structure": word, "phase": "C"}, {"last": 1.0})[0], "long")
        self.assertEqual(self.htf.wyckoff_bias({"structure": "phân phối", "phase": "C"}, {"last": 1.0})[0], "short")


if __name__ == "__main__":
    unittest.main()


class VolumeTypingFollowsTheBooksTwoTables(unittest.TestCase):
    """knowledge/wyckoff/modern-tools.md:55-72 -- Bảng 2.1 (Spring, WMT p049) and Bảng 2.2 (Upthrust, WMT
    p064) are DIFFERENT ladders. Until 2026-09-19 the Spring ladder ran on shorts too, so a below-average bar
    was typed 1 (and given the most aggressive entry) and a genuine UTAD was typed 3."""

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")

    def test_spring_is_ascending_in_volume_low_one_high_three(self):
        lo = self.bt.VOL["low_max_ratio"]; hi = self.bt.VOL["high_min_ratio"]
        self.assertEqual(self.bt.vtype(lo - 0.1, "long"), 1)      # book: "Low -- no fresh selling pressure"
        self.assertEqual(self.bt.vtype((lo + hi) / 2, "long"), 2)  # book: "Moderate"
        self.assertEqual(self.bt.vtype(hi + 0.1, "long"), 3)      # book: "High -- panic selling / Shake Out"

    def test_upthrust_type_two_is_the_highest_volume_not_type_three(self):
        hi = self.bt.VOL["high_min_ratio"]
        self.assertEqual(self.bt.vtype(hi + 0.5, "short"), 2,
                         "book Bảng 2.2: type 2 (UTAD) is 'very high at the extreme'")

    def test_the_book_has_no_low_volume_upthrust_so_it_is_refused(self):
        self.assertIsNone(self.bt.vtype(self.bt.VOL["upthrust_min_ratio"] - 0.01, "short"))
        self.assertIsNone(self.bt.vtype(0.1, "short"))

    def test_an_increase_at_the_touch_is_upthrust_type_one(self):
        self.assertEqual(self.bt.vtype(self.bt.VOL["upthrust_min_ratio"], "short"), 1)
        self.assertEqual(self.bt.vtype(self.bt.VOL["high_min_ratio"], "short"), 1)

    def test_no_ratio_is_still_no_type_on_either_side(self):
        self.assertIsNone(self.bt.vtype(None, "long")); self.assertIsNone(self.bt.vtype(None, "short"))

    def test_every_caller_passes_the_side(self):
        """A caller that forgets `side` silently gets the Spring ladder -- the exact defect being fixed."""
        import re
        for rel in ("scripts/backtest-methods.py", "scripts/strategy-runner.py"):
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            for m in re.finditer(r"(?<!def )\bvtype\(([^)]*)\)", src):
                args = m.group(1)
                if args.strip() in ("ratio", "self"):
                    continue
                self.assertIn("side", args, f"{rel}: vtype({args}) does not pass a side")


class DoiNhanFollowsTheBooksThirds(unittest.TestCase):
    """đối nhãn Dấu hiệu 1 and 2 (WA p150-165), the "counter-labelling" tests that ask whether the structure
    being drawn is really the structure it is labelled as.

    Before 2026-09-19 neither sign existed on the mechanical path and the ONE threshold that did exist -- the
    `st_min` filter -- used a HALF, while the book divides the range into THREE parts:
    "chia biên độ của cấu trúc thành 3 phần" (WA p150). docs/audits/2026-09-19-knowledge-fidelity.md finding 9.
    """

    @classmethod
    def setUpClass(cls):
        cls.W = load("wyckoff_rules.py")

    def test_the_book_divides_the_range_into_three_not_two(self):
        self.assertAlmostEqual(self.W.PARAMS["doi_nhan_third"], 1 / 3, places=6,
                               msg="WA p150 says three parts; a half is not in the book")

    def _sign(self, st_pct):
        third = self.W.PARAMS["doi_nhan_third"]
        return "supports" if st_pct >= 2 * third else ("contradicts" if st_pct <= third else "neutral")

    def test_st_in_the_upper_third_supports_the_label(self):
        self.assertEqual(self._sign(0.80), "supports")
        self.assertEqual(self._sign(2 / 3), "supports", "the boundary itself is in the upper third")

    def test_st_in_the_lower_third_contradicts_the_label(self):
        """WA p150: ST in the lower third is 'dấu hiệu để nhận dạng sớm tái phân phối hoặc phân phối'."""
        self.assertEqual(self._sign(0.10), "contradicts")
        self.assertEqual(self._sign(1 / 3), "contradicts")

    def test_the_middle_is_neither(self):
        self.assertEqual(self._sign(0.5), "neutral")

    def test_a_half_is_no_longer_treated_as_the_books_boundary(self):
        """The old docstring claimed 'ST above 50% = supply thinned'. 0.5 must NOT read as a strength sign."""
        self.assertNotEqual(self._sign(0.5), "supports")

    def test_both_signs_are_recorded_on_every_structure(self):
        """Absent-from-the-mechanical-path was the finding; presence on the record is the fix."""
        src = open(os.path.join(ROOT, "scripts", "wyckoff_rules.py"), encoding="utf-8").read()
        self.assertEqual(src.count("st_sign=st_sign"), 2, "both out.append paths must record Dấu hiệu 1")
        self.assertEqual(src.count("phase_b_sign="), 2, "both out.append paths must record Dấu hiệu 2")

    def test_the_signs_survive_the_distribution_mirror(self):
        """detect_distributions runs the detector on INVERTED prices. The signs are named supports/contradicts
        precisely so the mirror cannot flip their meaning -- upper/lower would have."""
        src = open(os.path.join(ROOT, "scripts", "wyckoff_rules.py"), encoding="utf-8").read()
        self.assertIn("NOTE ON FRAME", src)
        for word in ("supports", "contradicts"):
            self.assertIn(f'"{word}"', src)


class DoiNhanSignsAreRecordedAndNeitherVetoesByDefault(unittest.TestCase):
    """The symmetry is the point, and it was not the first answer.

    Dấu hiệu 1 defaulted ON for part of 2026-09-19, on the reading that WA p150's "ST ở 1/3 phần dưới ...
    dấu hiệu để nhận dạng sớm tái phân phối hoặc phân phối" amounts to a veto on the accumulation label. It
    was turned back off the same day: the section is titled "những thử nghiệm trong các Phase" -- tests for
    judging a structure while it is forming -- and closes with "trong diễn biến thực tế của thị trường, chúng
    ta không thể thực sự biết đó là tích lũy hay phân phối" (WA p167). The book states a SIGN; "therefore do
    not trade it" is an inference on top of it, and an inference wearing the book's authority is the
    unlabelled-invention this audit exists to remove.

    What IS the book's is the thirds (WA p150), and those are asserted in DoiNhanFollowsTheBooksThirds above.
    Whether gating helps is a §41 hypothesis with a measurable answer, not a default.
    """

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")

    def test_neither_sign_vetoes_by_default(self):
        self.assertFalse(self.bt.OPTS["st_gate"])
        self.assertFalse(self.bt.OPTS["phase_b_gate"])

    def test_both_gates_still_exist_so_the_hypothesis_can_be_measured(self):
        for gate in ("st_gate", "phase_b_gate"):
            self.assertIn(gate, self.bt.OPTS)

    def test_both_signs_reach_the_trade_record_whether_or_not_they_gate(self):
        """A sign that is recorded is usable by the human and LLM paths and by a backtest comparison; a sign
        that only ever refused would be invisible on the trades it let through."""
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn('st_sign=r["st_sign"]', src)
        self.assertIn('phase_b_sign=r["phase_b_sign"]', src)

    def test_the_measured_cost_of_gating_is_written_next_to_the_gate(self):
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("Measured cost of defaulting Dấu hiệu 1 on", src)

    def test_the_gate_is_in_the_live_path_too(self):
        """CLAUDE.md §37: the backtest must run the live semantics. A gate in only one engine means the
        selection was measured on a population the runner does not take."""
        # Since 2026-09-19 there is ONE Wyckoff read, bt.wyckoff_fires(); the runner's setups_wyckoff delegates to
        # it and bt.scan() walks it window by window, so the gates live in that one function and are read from
        # bt.OPTS there. The runner must not grow a second copy.
        runner = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("bt.wyckoff_fires(side, candles, tf, sym)", runner, "setups_wyckoff no longer delegates to the shared read")
        self.assertNotIn("W.detect_accumulations", runner, "the runner detects on its own again -- two engines")
        engine = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        for gate in ("sloped_gate", "st_gate", "phase_b_gate"):
            self.assertIn(f'OPTS["{gate}"]', engine, f"the shared read does not apply {gate}")


class VolumeProvenanceReachesEveryRecord(unittest.TestCase):
    """WMT p131-133: the book's volume rules assume TRADED volume, and it says so about tick feeds itself.
    The MT5 CFD feed reports tick COUNT. Nothing carried that distinction before 2026-09-19 (finding 8)."""

    @classmethod
    def setUpClass(cls):
        cls.W = load("wyckoff_rules.py")
        cls.bt = load("backtest-methods.py")

    def test_the_default_is_traded_and_it_is_a_parameter(self):
        import inspect
        for fn in (self.W.detect_accumulations, self.W.detect_distributions):
            self.assertEqual(inspect.signature(fn).parameters["volume_kind"].default, "traded")

    def test_a_cfd_symbol_is_tick_volume_and_a_crypto_one_is_not(self):
        self.assertTrue(self.bt._I.is_tick_volume("XAUUSD"))
        self.assertFalse(self.bt._I.is_tick_volume("BTCUSDT"))

    def test_both_engines_pass_the_symbols_own_kind(self):
        # One read for both engines since 2026-09-19 (bt.wyckoff_fires); the runner passes `sym` through to it.
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("is_tick_volume(sym)", src, "the shared read guesses the volume kind instead of reading it")
        self.assertIn("volume_kind=vkind", src, "the shared read does not pass the kind into the detector")
        runner = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("bt.wyckoff_fires(side, candles, tf, sym)", runner, "the runner does not hand its symbol to the shared read")

    def test_the_kind_reaches_the_trade_record(self):
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn('volume_kind=r["volume_kind"]', src)


class DeadIctSwitchesAreGone(unittest.TestCase):
    """finding 11: --ict-pd and --std-origin were declared, printed in report headers, written into
    pilot-top20.json and tuned for a year by scripts/ict-flags-1y.py -- and read by nothing. Both rules they
    named are real deck rules already enforced elsewhere, which is why the fix is deletion, not wiring."""

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")

    def test_neither_switch_survives_in_the_options(self):
        for dead in ("ict_pd", "std_origin", "ict_disp"):
            self.assertNotIn(dead, self.bt.OPTS, f"{dead} is back in OPTS")

    def test_the_tuner_that_measured_noise_is_deleted(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "scripts", "ict-flags-1y.py")))

    def test_r13_is_still_enforced_just_not_by_a_flag(self):
        """knowledge/ict/core-a.md §3.4 R13 -- longs in discount, shorts in premium -- is not optional in the
        deck. It lives in the scanner as pd_ok and every ICT candidate is refused without it."""
        scan = open(os.path.join(ROOT, "scripts", "ict-scan.py"), encoding="utf-8").read()
        self.assertIn("pd_ok", scan)
        bt_src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn('su.get("pd_ok")', bt_src, "the backtest does not refuse a wrong-half candidate")

    def test_displacement_is_mandatory_not_a_switch(self):
        """R10 calls a full-bodied close beyond structure an MSS; R11 calls the same break WITHOUT displacement
        a liquidity grab -- the opposite read. find_ict used to default O=None, which turned the check off for
        every caller that omitted it."""
        import inspect
        sig = inspect.signature(self.bt.find_ict)
        self.assertIs(sig.parameters["O"].default, inspect.Parameter.empty,
                      "find_ict's displacement check can still be silently disabled by omitting O")


class BothDeckLiquidityTypesBecomePools(unittest.TestCase):
    """knowledge/ict/core-a.md §2.7 enumerates TWO types of liquidity and the scanner only built the second.

      "Old Highs & Lows are previous highs and lows."  Old High -> Buyside Liquidity, Old Low -> Sellside.
      "Equal Highs & Lows are when price reaches the same price level multiple times."

    With only the equal type, a lone prior swing high could never be BSL: never swept, never a target, and
    never an edge of the dealing range -- which is the measured reason the range kept falling back to the
    scan-window edge. docs/audits/2026-09-19-knowledge-fidelity.md finding 10.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = load("ict-scan.py")

    @staticmethod
    def _bars(prices):
        out = []
        for i, p in enumerate(prices):
            out.append({"time": f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00Z", "open": p, "high": p + 0.5,
                        "low": p - 0.5, "close": p, "volume": 100})
        return out

    def _pools(self, prices):
        a = self.m.analyze(self._bars(prices), 6, tf="15m")
        return a["pools"]

    def test_a_single_prior_swing_high_is_buyside_liquidity(self):
        """One clear peak, no matching second peak: nothing an "equal highs" rule could ever pair it with."""
        prices = [100 + i for i in range(8)] + [107 - i for i in range(1, 9)] + [99 + i * 0.2 for i in range(20)]
        pools = self._pools(prices)
        bsl_old = [p for p in pools if p["kind"] == "BSL" and p["type"] == "old"]
        self.assertTrue(bsl_old, "a lone swing high produced no buyside liquidity at all")

    def test_every_pool_declares_which_type_it_is(self):
        prices = [100 + i for i in range(8)] + [107 - i for i in range(1, 9)] + [99 + i * 0.2 for i in range(20)]
        for p in self._pools(prices):
            self.assertIn(p.get("type"), ("old", "equal"), f"pool without a deck type: {p}")

    def test_the_equal_reading_wins_when_both_describe_the_same_level(self):
        """Equal pairs are added first so the stronger, named reading keeps the row; the tolerance dedupe then
        drops the single-swing duplicate rather than recording the same price twice."""
        src = open(os.path.join(ROOT, "scripts", "ict-scan.py"), encoding="utf-8").read()
        i_equal = src.index('"equal"'); i_old = src.index('add("BSL", [i], H[i], "old")')
        self.assertLess(i_equal, i_old, "the old-highs pass must run after the equal-highs pass")

    def test_the_deck_sentence_is_quoted_where_the_rule_lives(self):
        src = open(os.path.join(ROOT, "scripts", "ict-scan.py"), encoding="utf-8").read()
        self.assertIn("Old Highs & Lows are previous highs and lows", src)
        self.assertIn("core-a.md §2.7", src)


class SlopedStructuresAreNotRefusedByDefault(unittest.TestCase):
    """The default that got flipped twice in one day, pinned with the reason and the measurement.

    WA p170 does say "Tôi không khuyến khích mọi người giao dịch với những mẫu hình dốc như thế này", and on
    2026-09-19 that sentence was read as a default-on veto. It was reverted the same day because:
      * the book teaches the four sloped variants across WA p167-181 WITH their entries, closing with
        "tất cả đều là biến thể của cấu trúc nằm ngang" (WA p180-181);
      * this repo's own rule extraction scopes the discouragement to beginners -- WA2-42,
        knowledge/wyckoff/advance.md:1113 "IF you are a first-time Wyckoff operator";
      * the threshold is ours. `slope_max_tr = 0.35` is a PROJECT parameter and the book says in the same
        sentence there is "không có một quy chuẩn nào về độ dốc".
    Measured on BTCUSDT 15m over the last 20 000 bars: defaulting it on took WYCKOFF-BOOK from 23 structures
    to 5 and COMBINED-BOOK from 1 to 0.
    """

    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")

    def test_the_gate_is_off_by_default(self):
        self.assertFalse(self.bt.OPTS["sloped_gate"])

    def test_the_threshold_is_declared_a_project_parameter(self):
        W = load("wyckoff_rules.py")
        self.assertIn("slope_max_tr", W.PARAMS)
        src = open(os.path.join(ROOT, "scripts", "wyckoff_rules.py"), encoding="utf-8").read()
        line = next(l for l in src.splitlines() if l.strip().startswith("slope_max_tr="))
        self.assertIn("project", line.lower(), "the slope threshold must not read as sourced from the book")

    def test_the_reason_for_the_default_is_written_where_the_gate_is(self):
        """A default this consequential must carry its argument next to the code, not only in an audit file."""
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("WA2-42", src)
        self.assertIn("không có một quy chuẩn nào về độ dốc", src)

    def test_the_selection_path_uses_the_same_default(self):
        """stability-report.py pins the options it measures under; if it pinned the gate ON while the runner
        left it OFF, the selection would be measured on a population the runner does not take (CLAUDE.md §37)."""
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("sloped_gate=False", src)
        self.assertNotIn("sloped_gate=True", src)
        self.assertIn("st_gate=False", src)
        self.assertNotIn("st_gate=True", src)


class TheIctTargetIsTheProjectionNotTheNearestPool(unittest.TestCase):
    """knowledge/ict/models.md §2.1.5: "the main focus for identifying targets is using standard deviation
    projections". Liquidity levels are a DRAW (core-a.md §2.8), not the target; R13's own diagram targets the
    opposite range extreme.

    The scanner had this inverted -- nearest unswept pool first, projection as a fallback -- and the same
    morning's (correct) addition of Old Highs & Lows made "nearest pool" almost always the very next swing.
    Median planned R fell to 0.55 and the 3R floor refused every reachable trade; on the same twenty entries
    the deck's target gave a median of 2.91 and nine trades over the floor (docs/architecture/policy.json,
    2026-09-19). Both engines read scripts/ict-scan.py setup_candidate, so this pins the one seam.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = load("ict-scan.py")
        bt = load("backtest-methods.py")     # its load() reads the FULL stored history; ict-scan's reads the
        cls.cands = []                       # 576-bar live window, which is too short to hold a candidate
        for sym in ("BTCUSDT", "XAUUSD"):
            try:
                c, _src = bt.load(sym, "15m")
            except Exception:
                continue
            if not c:
                continue
            # Complete candidates are rare (about one every few weeks per series), and one is only visible
            # while its sweep sits inside the lookback, so the probe steps every 4 bars over the last 40 000
            # and stops once it has a handful -- bounded, and enough to pin the rule on real data.
            W = 576
            for k in range(max(W, len(c) - 40000), len(c), 4):
                win = c[k - W:k]
                a = cls.m.analyze(win, 2, tf="15m")
                su = cls.m.setup_candidate(a, win, 12)
                if su and su.get("complete") and su.get("std_targets"):
                    cls.cands.append(su)
                if len(cls.cands) >= 6:
                    break
        if not cls.cands:
            raise unittest.SkipTest("no complete ICT candidate with a projection in the probe window")

    def test_when_a_leg_exists_the_target_is_minus_two_sigma(self):
        for su in self.cands:
            self.assertAlmostEqual(su["target"], su["std_targets"]["-2"], places=6,
                                   msg=f"{su['side']} setup at {su['mss']['time']} targets {su['target']} not "
                                       f"the -2σ projection {su['std_targets']['-2']}")

    def test_the_target_kind_names_the_deck_rule(self):
        for su in self.cands:
            self.assertIn("models.md §2.1.5", su["target_kind"])

    def test_the_nearest_pool_is_still_recorded_as_an_objective_not_lost(self):
        """A draw on liquidity is real information for the reader; it is demoted, not deleted."""
        self.assertIn("objective", self.cands[0])

    def test_the_nearest_pool_is_never_the_target_when_a_projection_exists(self):
        for su in self.cands:
            obj = su.get("objective")
            if obj is None or abs(obj - su["std_targets"]["-2"]) < 1e-9:
                continue
            self.assertNotAlmostEqual(su["target"], obj, places=6,
                                      msg="a nearby pool became the target while a projection existed")
