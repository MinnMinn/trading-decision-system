"""Bias is a per-method reading, not a Wyckoff monopoly (user decision 2026-09-13).

Before this, htf_context.bias_of() derived bias ONLY from the Wyckoff structure/phase read, so turning Wyckoff
off in /automation left the Wyckoff narrative still deciding every verdict (and, with no narrative at all, every
tier fell to "unknown" instead of falling back to ICT). ICT has its own directional bias and always did:

  - the draw on liquidity: a body close THROUGH the previous candle's high/low means that level was the draw,
    expect continuation; a wick through with the body failing to close beyond is FAILURE TO DISPLACE, so the
    opposite level becomes the new draw (knowledge/04 §2.11 PCH/PCL, §2.12 PDH/PDL, §2.14, §3.2 R5-R8);
  - structural falsification: the last confirmed MSS on that timeframe, by body close (knowledge/05 §2.2).

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
    """A tier's facts.json entry, trimmed to what bias_of reads."""
    return {"last": last, "last_mss": mss,
            "prev_candle": {"tf": tf, "pch": 110.0, "pcl": 90.0, "pch_state": pch_state, "pcl_state": pcl_state}}


ACC_C = {"structure": "tái tích lũy", "phase": "C"}          # -> wyckoff long
DIST_C = {"structure": "phân phối", "phase": "C"}            # -> wyckoff short


class IctBias(unittest.TestCase):
    def setUp(self):
        self.htf = load("htf_context.py")

    def test_body_close_through_previous_high_is_the_draw_and_reads_long(self):
        bias, basis = self.htf.ict_bias(facts(pch_state="closed_through"))
        self.assertEqual(bias, "long")
        self.assertIn("110", basis)

    def test_body_close_through_previous_low_reads_short(self):
        self.assertEqual(self.htf.ict_bias(facts(pcl_state="closed_through"))[0], "short")

    def test_wick_through_high_with_body_failing_is_failure_to_displace_and_reads_short(self):
        bias, basis = self.htf.ict_bias(facts(pch_state="swept"))
        self.assertEqual(bias, "short")
        self.assertIn("failure to displace", basis.lower())

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
        self.assertIn("mâu thuẫn", basis.lower())

    def test_daily_tier_names_the_level_pdh_not_pch(self):
        self.assertIn("PDH", self.htf.ict_bias(facts(pch_state="closed_through", tf="1D"))[1])

    def test_intraday_tier_names_the_level_pch(self):
        self.assertIn("PCH", self.htf.ict_bias(facts(pch_state="closed_through", tf="1h"))[1])

    def test_no_prev_candle_at_all_is_unknown(self):
        self.assertEqual(self.htf.ict_bias({"last": 100.0})[0], "unknown")


class BiasOfPerMethod(unittest.TestCase):
    def setUp(self):
        self.htf = load("htf_context.py")

    def test_defaults_to_wyckoff_only_so_existing_callers_are_unchanged(self):
        # demo-pilot.py and the checkers call bias_of() with two args; step 6 plumbs dims to them deliberately.
        self.assertEqual(self.htf.bias_of(ACC_C, facts(pch_state="closed_through"))[0], "long")
        self.assertEqual(self.htf.bias_of(DIST_C, facts(pch_state="closed_through"))[0], "short")

    def test_ict_only_ignores_the_wyckoff_read_entirely(self):
        # THE regression: Wyckoff says long, ICT draw says short, ICT-only mode must read short.
        bias, basis = self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=("ict",))
        self.assertEqual(bias, "short")
        self.assertNotIn("tích lũy", basis)

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
        self.assertIn("mâu thuẫn", basis.lower())
        self.assertIn("wyckoff", basis.lower())
        self.assertIn("ict", basis.lower())

    def test_both_engaged_but_one_silent_uses_the_other(self):
        self.assertEqual(self.htf.bias_of(ACC_C, facts(), methods=("wyckoff", "ict"))[0], "long")
        self.assertEqual(self.htf.bias_of(None, facts(pcl_state="swept"), methods=("wyckoff", "ict"))[0], "long")

    def test_no_method_engaged_is_unknown(self):
        self.assertEqual(self.htf.bias_of(ACC_C, facts(pch_state="swept"), methods=())[0], "unknown")


class IctBiasVocabularyIsPure(unittest.TestCase):
    """The basis string is shown on the page and fed to the model brief; an ICT bias may not carry Wyckoff words
    (method_purity.RULES['ict']) or the method switch leaks straight back in through the explanation."""

    def setUp(self):
        self.htf = load("htf_context.py")
        self.mp = load("method_purity.py")

    def test_every_ict_basis_is_pure_ict_vocabulary(self):
        cases = [facts(pch_state="closed_through"), facts(pcl_state="closed_through"), facts(pch_state="swept"),
                 facts(pcl_state="swept"), facts(mss={"type": "bull", "level": 99.0}), facts(tf="1D", pch_state="swept"),
                 facts(pch_state="closed_through", pcl_state="closed_through"), facts()]
        for f in cases:
            basis = self.htf.ict_bias(f)[1]
            self.assertEqual(self.mp.violations(basis, "ict"), [], f"impure ICT basis: {basis}")


class BiasMethodsFromTheSwitch(unittest.TestCase):
    """`/automation dimension <m> off` has to reach the bias, not just the columns that get drawn. The flag
    semantics mirror build-artifact.py's own (`flag is not False` -> engaged), so an absent key means on."""

    def setUp(self):
        self.htf = load("htf_context.py")

    def cfg(self, market, dims):
        return {"markets": {market: {"dimensions": dims}}}

    def test_ict_only_market_yields_ict_only(self):
        self.assertEqual(self.htf.engaged_methods("daytrade", self.cfg("crypto", {"wyckoff": False, "ict": True})), ("ict",))

    def test_wyckoff_only_market_yields_wyckoff_only(self):
        self.assertEqual(self.htf.engaged_methods("daytrade", self.cfg("crypto", {"wyckoff": True, "ict": False})), ("wyckoff",))

    def test_both_on_yields_both_in_a_stable_order(self):
        self.assertEqual(self.htf.engaged_methods("daytrade", self.cfg("crypto", {"wyckoff": True, "ict": True})), ("wyckoff", "ict"))

    def test_all_off_yields_nothing(self):
        self.assertEqual(self.htf.engaged_methods("daytrade", self.cfg("crypto", {"wyckoff": False, "ict": False})), ())

    def test_absent_flag_counts_as_engaged(self):
        self.assertEqual(self.htf.engaged_methods("daytrade", self.cfg("crypto", {})), ("wyckoff", "ict"))

    def test_gold_styles_read_the_cfd_market(self):
        cfg = {"markets": {"crypto": {"dimensions": {"wyckoff": False, "ict": True}},
                           "cfd": {"dimensions": {"wyckoff": True, "ict": False}}}}
        self.assertEqual(self.htf.engaged_methods("gold-scalp", cfg), ("wyckoff",))
        self.assertEqual(self.htf.engaged_methods("scalping", cfg), ("ict",))


class BriefLinesFollowTheSwitch(unittest.TestCase):
    """The model brief is where the leak did the most damage: local-eval-brief.py handed Sonnet a Wyckoff
    structure/phase read and a Wyckoff-derived BIAS to obey, in every run, whatever /automation said."""

    def setUp(self):
        self.htf = load("htf_context.py")

    def ctx(self):
        return {"tf": "1h", "style": "1h", "scanned_at": "2026-09-12T18:00:00Z", "last_time": "2026-09-12T18:00:00Z",
                "last": 100.0, "lo": 90.0, "hi": 110.0, "eq": 100.0, "pct": 0.5, "stance": "CHỜ", "verdict": None,
                "anchors": [], "last_mss": {"type": "bear", "level": 99.0},
                "wyckoff": {"structure": "tái tích lũy", "phase": "C", "updated": "2026-09-12T15:02:00Z"},
                "wyckoff_source": "data/live/narrative/1h.json", "bias": "short", "basis": "[ict] ..."}

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


class ExecutionFilterIsStillPinnedToWyckoff(unittest.TestCase):
    """The pilot's giảm-khung filter (demo-pilot.py) gates real orders. Steps 1-5 deliberately leave it reading
    Wyckoff-only so the analysis change and the execution change are separate, reviewable diffs.

    These are CHARACTERIZATION tests: they pin what the filter does TODAY, including the behaviour that is wrong
    (see the `unknown` case below). Step 6 is expected to change them — that is the point. A step-6 diff that
    leaves this class untouched has not actually changed order gating."""

    def setUp(self):
        self.pilot = load("demo-pilot.py")

    def ctx(self, bias):
        return {"tf": "4h", "bias": bias, "basis": f"[wyckoff] {bias} …"}

    def test_bias_methods_are_pinned_to_wyckoff(self):
        self.assertEqual(self.pilot.BIAS_METHODS, ("wyckoff",))

    def test_the_pin_is_actually_passed_to_load_context(self):
        # A pinned constant that nothing reads is the classic way a pin silently stops holding.
        src = open(os.path.join(ROOT, "scripts", "demo-pilot.py"), encoding="utf-8").read()
        self.assertIn("load_context(\"daytrade\", sym, methods=BIAS_METHODS)", src)

    def test_matching_bias_passes_the_filter(self):
        self.assertIsNone(self.pilot.htf_reject_reason(self.ctx("long"), "long", "LONG"))
        self.assertIsNone(self.pilot.htf_reject_reason(self.ctx("short"), "short", "SHORT"))

    def test_opposing_bias_rejects(self):
        self.assertIn("không ủng hộ", self.pilot.htf_reject_reason(self.ctx("short"), "long", "LONG"))

    def test_neutral_bias_rejects(self):
        self.assertIsNotNone(self.pilot.htf_reject_reason(self.ctx("neutral"), "long", "LONG"))

    def test_unknown_bias_rejects_and_is_worded_as_disagreement(self):
        """TODAY'S BUG, pinned so step 6 must confront it: "no data" and "the context disagrees" produce the
        same rejection. In an ICT-only configuration the Wyckoff-pinned bias is `unknown` for every symbol, so
        the pilot silently rejects 100% of setups and the log says the context did not support them."""
        why = self.pilot.htf_reject_reason(self.ctx("unknown"), "long", "LONG")
        self.assertIsNotNone(why)
        self.assertIn("không ủng hộ", why)

    def test_missing_context_rejects(self):
        self.assertIn("?", self.pilot.htf_reject_reason(None, "long", "LONG"))


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


if __name__ == "__main__":
    unittest.main()
