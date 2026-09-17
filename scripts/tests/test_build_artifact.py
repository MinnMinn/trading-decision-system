"""The chart pages are rendered by scripts/build-artifact.py with TradingView Lightweight Charts as the drawing layer
(docs/specs/2026-09-12-chart-lightweight-charts-design.md). These tests pin the contract of that page: the vendored
library and scripts/chart.js are inlined (no CDN), the old hand-drawn SVG is gone, every data placeholder is filled,
and the ICT engine's result depends on the tier window only — never on what the viewer zoomed into."""
import importlib.util, json, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = os.path.join(ROOT, "scripts", "vendor", "lightweight-charts.standalone.production.js")
CHART_JS = os.path.join(ROOT, "scripts", "chart.js")


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def synth(n, t0="2026-09-01T00:00:00Z", step_min=15, base=77000.0):
    """Deterministic OHLCV rows in the connector's shape (no live data needed to run the tests)."""
    import datetime
    t = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00")); out = []; p = base
    for i in range(n):
        o = p; c = o + ((i * 37) % 11 - 5) * 12.5; h = max(o, c) + (i * 13) % 7 * 4; l = min(o, c) - (i * 17) % 5 * 4
        out.append(dict(time=t.strftime("%Y-%m-%dT%H:%M:%SZ"), open=o, high=h, low=l, close=c, volume=1 + (i * 7) % 13))
        p = c; t += datetime.timedelta(minutes=step_min)
    return out


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b = load("build-artifact.py")
        real_read = b.read_json
        keep = ("analysis-params.json", "automation-config.json")
        b.read_json = lambda path, default=None: real_read(path, default) if path.endswith(keep) else default
        b.candles = lambda sym, tf, n, snap=None: (synth(n, step_min=b.TF_MIN.get(tf, 15)), "2026-09-12T00:00:00Z", "test-fixture")
        cls.tmp = tempfile.mkdtemp(); cls.out = os.path.join(cls.tmp, "scalping.html")
        b.build("scalping", cls.out)
        cls.html = open(cls.out, encoding="utf-8").read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_vendored_library_is_inlined_not_linked(self):
        self.assertTrue(os.path.exists(VENDOR), "scripts/vendor/lightweight-charts.standalone.production.js missing")
        self.assertTrue("TradingView Lightweight Charts" in self.html, "vendor license header not inlined")
        self.assertTrue("LightweightCharts" in self.html, "library global not present")
        self.assertIsNone(re.search(r'<script[^>]+src="https?://', self.html), "page must not load scripts from a CDN")

    def test_attribution_notice_replaces_the_canvas_logo(self):
        """Apache-2.0 §4(d): the library's NOTICE text must ship with the page. We print it in the footer and switch the
        on-canvas logo off; both halves must hold together."""
        self.assertTrue("attributionLogo:false" in open(CHART_JS, encoding="utf-8").read())
        self.assertTrue("TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc." in self.html, "NOTICE line missing from footer")
        self.assertTrue('href="https://www.tradingview.com/"' in self.html, "TradingView link missing from footer")

    def test_chart_js_is_a_separate_inlined_file(self):
        self.assertTrue(os.path.exists(CHART_JS), "scripts/chart.js missing")
        marker = open(CHART_JS, encoding="utf-8").read().splitlines()[0]
        self.assertTrue(marker in self.html, "scripts/chart.js first line not found in page")

    def test_old_svg_chart_is_gone_and_placeholders_are_filled(self):
        for bad in ('<svg class="chart"', "__ROWS__", "__DATA__", "__PARAMS__"):
            self.assertFalse(bad in self.html, f"{bad} still in page")
        self.assertIsNotNone(re.search(r'<div class="chart-wrap"><div class="chart" id="chart-entry-', self.html), "entry chart container missing")

    def test_page_data_is_valid_json(self):
        at = self.html.find("TChart.init(")
        self.assertGreater(at, 0, "TChart.init(DATA, PARAMS) call not found")
        dec = json.JSONDecoder(); data, end = dec.raw_decode(self.html, at + len("TChart.init("))
        params, _ = dec.raw_decode(self.html, self.html.index("{", end))
        self.assertIn("btc", data)
        sym = next(iter(data.values()))
        self.assertEqual([t["key"] for t in sym["tiers"]][-1], "entry")
        self.assertTrue(all(len(r) == 7 for t in sym["tiers"] for r in t["rows"]))
        self.assertIn("lookback", params)


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class Engine(unittest.TestCase):
    """scripts/chart.js exposes its pure functions under module.exports when loaded by node."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_ict_engine_result_is_a_function_of_the_window_only(self):
        rows = [[r["time"][5:16], r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(240)]
        P = {"lookback": 20, "high": 1.5, "spike": 2.5, "ict": {}}
        out = self.run_js(f"const rows={json.dumps(rows)}, P={json.dumps(P)};"
                          "const a=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "const b=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "console.log(JSON.stringify({same:JSON.stringify(a)===JSON.stringify(b), keys:Object.keys(a).sort(), hi:a.hi, lo:a.lo}))")
        self.assertTrue(out["same"])
        for k in ("fvgs", "obs", "mss", "pools", "levels", "sess", "kz", "eq", "hi", "lo", "pct"):
            self.assertIn(k, out["keys"])
        self.assertEqual(out["hi"], max(r[2] for r in rows)); self.assertEqual(out["lo"], min(r[3] for r in rows))

    def test_volume_stats_use_the_project_lookback(self):
        rows = [[r["time"][5:16], r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(60)]
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          "const v=T.volStats(rows,{lookback:20}); console.log(JSON.stringify({n:v.ratio.length, first:v.ratio.slice(0,3), last:v.ratio[59]}))")
        self.assertEqual(out["n"], 60); self.assertEqual(out["first"], [None, None, None]); self.assertIsInstance(out["last"], float)

    def test_annotation_builders_are_pure(self):
        """Overlay shapes are plain {kind,...} records in (bar index, price) space so they can be checked without a browser."""
        rows = [[r["time"][5:16], r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          "const P={lookback:20,high:1.5,spike:2.5,ict:{}}; const ict=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                          "const wy=T.wyckoffShapes(rows,{tr:{high:77300,low:76900,from:rows[10][6]},phases:[{from:rows[5][6],to:rows[40][6],label:'Pha B'}],events:[{time:rows[20][6],label:'SC 76,900',up:false}]},{compact:false,fmt:v=>String(v)});"
                          "console.log(JSON.stringify({kinds:[...new Set(sh.concat(wy).map(s=>s.kind))].sort(), wyN:wy.length, allPlaced:sh.concat(wy).every(s=>s.kind&&(('i1' in s)||('i' in s)))}))")
        self.assertTrue(out["allPlaced"], "every shape carries a bar-index position (i or i1; null = full width)")
        self.assertTrue({"rect", "hseg"} <= set(out["kinds"]))
        self.assertGreaterEqual(out["wyN"], 4)  # TR high + TR low + phase band + event mark


class NoEmptyIctPaneApology(unittest.TestCase):
    """The ICT second pane used to be an empty box with an implementation note explaining why it was empty.
    That sentence must be gone, and VOLUME_LANES must be derived from the pane registry (methods.json), not
    a hand-kept 'd == wyckoff' name comparison -- a second dimension could later declare a volume pane too."""

    def test_apology_sentence_is_gone_from_chart_js(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("khối lượng không thuộc ICT", src)

    def test_volume_lanes_is_not_a_hardcoded_name_comparison(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn('d == "wyckoff"', src)


class PaneRegistryDrivesChartJs(unittest.TestCase):
    """Every dimension's second-pane behaviour comes from ONE injected registry (PARAMS.panes), not a
    parallel hand-kept list, and chart.js renders each declared kind (Task: ICT pane replacement)."""

    def test_second_pane_choice_reads_the_injected_registry_not_a_lane_name_check(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("P.volumeLanes", src, "old parallel volume-lane list must be gone")
        self.assertIn("P.panes", src, "second-pane content must be driven by the injected pane registry")
        self.assertIn("pane.kind==='volume'", src.replace(" ", ""))
        self.assertIn("pane.kind==='range_pct'", src.replace(" ", ""))

    def test_a_dimension_missing_a_pane_spec_fails_the_build(self):
        methods = load("methods.py")
        import copy
        bad = copy.deepcopy(methods._DATA)
        del bad["dimensions"]["ict"]["pane"]
        with self.assertRaises(ValueError):
            methods._validate(bad)


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class RangePctSeriesEngine(unittest.TestCase):
    """Pure function backing the ICT pane's range_pct kind: per-bar position within the dealing range
    (ict.lo/ict.hi, already computed by ictAnalyze), 0-100, so it can be checked without a browser."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_series_is_a_pure_function_of_rows_and_dealing_range(self):
        rows = [[r["time"][5:16], r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
        P = {"lookback": 20, "high": 1.5, "spike": 2.5, "ict": {}}
        out = self.run_js(f"const rows={json.dumps(rows)}, P={json.dumps(P)};"
                          "const ict=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "const s=T.rangePctSeries(rows,ict);"
                          "console.log(JSON.stringify({n:s.length, allInRange:s.every(p=>p.value>=0&&p.value<=100), "
                          "lastMatchesPct:Math.abs(s[s.length-1].value-ict.pct*100)<1e-6}))")
        self.assertEqual(out["n"], 120)
        self.assertTrue(out["allInRange"], "every bar's position must be clamped to [0,100]")
        self.assertTrue(out["lastMatchesPct"], "the series' last point must agree with ict.pct (same lo/hi)")


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class RangePaneAxisLabelIsCompact(unittest.TestCase):
    """The 2026-09-12 ICT-pane-replacement commit (27568e7) put the pane's full registry label -- 'Vị trí trong
    dealing range (Premium / Discount)' -- on the price axis via 'EQ '+pane.label. An axis label widens the
    right-hand gutter of every pane on every chart (labelAt:'axis' reserves space for the longest tag). The price
    pane's own EQ tag (chart.js ictShapes, 'EQ '+fmt(ict.eq)) is a short value, not a sentence; the range pane's
    EQ tag must be equally short."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_range_pane_eq_shape_label_is_short_not_the_registry_sentence(self):
        out = self.run_js("const s=T.rangePctEqShape({label:'Vị trí trong dealing range (Premium / Discount)'});"
                           "console.log(JSON.stringify({label:s.label, labelAt:s.labelAt, kind:s.kind, price:s.price}))")
        self.assertEqual(out["kind"], "hseg")
        self.assertEqual(out["labelAt"], "axis")
        self.assertEqual(out["price"], 50)
        self.assertNotIn("dealing range", out["label"], "axis label must not carry the pane's full sentence label")
        self.assertLessEqual(len(out["label"]), 12, f"axis label {out['label']!r} is not a short value like the price pane's 'EQ <value>'")

    def test_chart_js_does_not_concatenate_pane_label_onto_an_axis_hseg(self):
        src = open(CHART_JS, encoding="utf-8").read().replace(" ", "")
        self.assertNotIn("'EQ'+(pane.label||'')", src, "pane.label must not be concatenated into an axis label")


class DimensionFlagsAreReal(unittest.TestCase):
    def test_lanes_come_from_the_registry(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn('[("wyckoff", "Wyckoff"), ("ict", "ICT")', src)

    def test_matrix_columns_drop_a_disengaged_wyckoff_or_ict(self):
        """Before this, cols hardcoded ["wyckoff","ict"], so turning the flags off changed nothing."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("ba", os.path.join(ROOT, "scripts", "build-artifact.py"))
        ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)
        dims = {d: {"engaged": d == "wyckoff", "reason": ""} for d in ("wyckoff", "ict", "footprint", "heatmap")}
        html = ba.matrix("btc", "int", None, None, None, dims)
        self.assertIn("lane-wyckoff", html)
        self.assertNotIn("lane-ict", html)


class HiddenAttributeIsNotDefeatedByDisplayFlex(unittest.TestCase):
    """chart.js toggles .lane-status and .legend visibility with the `hidden` IDL attribute (chart.js render():
    `st.hidden=drawn`, `leg.hidden=!drawn`) whenever the active lane is disengaged for a symbol. Both classes also
    declare `display:flex` in CSS, which -- per CSS cascade rules -- overrides the UA stylesheet's
    `[hidden]{display:none}` default, so `hidden=true` stops actually hiding the element: a disengaged lane's
    stale status text (e.g. 'Wyckoff — tắt trong /automation') stays visibly rendered even while a different,
    engaged lane (e.g. ICT) is selected. Found via the browser check for the SOLO-ICT ladder/timeline fix.
    A `[hidden]{display:none}` override rule for both classes restores the intended toggle."""

    def test_lane_status_and_legend_have_a_hidden_attribute_override_rule(self):
        ba = load("build-artifact.py")
        self.assertIn(".lane-status[hidden]", ba.CSS.replace(" ", ""), "hidden attribute is defeated by .lane-status{display:flex} without this override")
        self.assertIn(".legend[hidden]", ba.CSS.replace(" ", ""), "hidden attribute is defeated by .legend{display:flex} without this override")


def _stub_S(tf="15m"):
    """Minimal S dict that drives ladder() into its 'no farther tier' fallback rows for bias/structure, so the
    test only exercises the dims-gating of the entry row's wy_cell()/ict_cell() output."""
    return {"tf": tf, "tiers": {}}


class LadderColumnsDropADisengagedWyckoffOrIct(unittest.TestCase):
    """Same class of bug Task 10 fixed in matrix(): ladder() (scripts/build-artifact.py:413) took no dimension
    flags at all and unconditionally rendered wy_cell()/ict_cell(). SOLO ICT mode
    (markets.crypto.dimensions.wyckoff=false) must drop the Wyckoff column from the tier ladder table too, not
    just from the read matrix."""

    def test_ladder_columns_drop_a_disengaged_wyckoff_or_ict(self):
        ba = load("build-artifact.py")
        dims = {d: {"engaged": d == "wyckoff", "reason": ""} for d in ("wyckoff", "ict", "footprint", "heatmap")}
        html = ba.ladder(_stub_S(), "BTCUSDT", "int", "—", None, None, {}, None, dims)
        self.assertIn("lane-wyckoff", html)
        self.assertNotIn("lane-ict", html)

    def test_ladder_drops_wyckoff_when_ict_is_the_only_engaged_method(self):
        """The reported defect: SOLO ICT preset, dims.wyckoff.engaged is False, dims.ict.engaged is True."""
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": "tắt trong /automation"}, "ict": {"engaged": True, "reason": "đang dùng"},
                "footprint": {"engaged": False, "reason": "..."}, "heatmap": {"engaged": False, "reason": "..."}}
        html = ba.ladder(_stub_S(), "BTCUSDT", "int", "—", None, None, {}, None, dims)
        self.assertNotIn("lane-wyckoff", html, "Wyckoff column must not render when dims.wyckoff.engaged is False")
        self.assertNotIn("chưa có đọc Wyckoff cho khung này", html, "Wyckoff cell text must not leak into the ladder when disengaged")
        self.assertIn("lane-ict", html)
        self.assertIn("tắt trong /automation", html, "the disengaged reason must be stated, not silently dropped (matrix() convention)")


class TimelineColumnsDropADisengagedWyckoffOrIct(unittest.TestCase):
    """timeline() (scripts/build-artifact.py:352) is the same class of bug: unconditional <th class="lane-wyckoff">
    / <td class="lane-wyckoff"> regardless of dims. It arrived with the timeframe-ladder work (716b32a) after the
    Task 10 matrix()-only sweep, so it never got the dims-gating treatment."""

    def test_timeline_drops_the_wyckoff_column_when_disengaged(self):
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": "tắt trong /automation"}, "ict": {"engaged": True, "reason": "đang dùng"}}
        rows = [{"time": "2026-09-01T00:00:00Z", "event": "MSS", "wyckoff": "LEAK-WYCKOFF-TEXT", "ict": "MSS tăng"}]
        html = ba.timeline(rows, dims)
        self.assertNotIn("lane-wyckoff", html)
        self.assertNotIn("LEAK-WYCKOFF-TEXT", html, "a disengaged method's cell content must not render at all")
        self.assertIn("lane-ict", html)
        self.assertIn("MSS tăng", html)


class NoDisengagedMethodContentAnywhereInThePage(unittest.TestCase):
    """General regression, not scoped to one table: with a method disengaged, no per-method render site --
    matrix(), ladder(), timeline() today -- may show that method's column, cell, or label. General enough to
    catch a future 4th such table the same way it would have caught ladder() and timeline()."""

    def test_wyckoff_off_ict_on_leaves_no_wyckoff_content_in_any_table(self):
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": "tắt trong /automation"}, "ict": {"engaged": True, "reason": "đang dùng"},
                "footprint": {"engaged": False, "reason": "không có nguồn CoinGlass live"},
                "heatmap": {"engaged": False, "reason": "không có nguồn CoinGlass live"}}
        matrix_html = ba.matrix("btc", "int", None, None, None, dims)
        ladder_html = ba.ladder(_stub_S(), "BTCUSDT", "int", "—", None, None, {}, None, dims)
        timeline_html = ba.timeline([{"time": "2026-09-01T00:00:00Z", "event": "x", "wyckoff": "LEAK-WY", "ict": "LEAK-ICT"}], dims)
        combined = matrix_html + ladder_html + timeline_html
        self.assertNotIn("lane-wyckoff", combined, "Wyckoff column/cell rendered somewhere despite dims.wyckoff.engaged=False")
        self.assertNotIn("LEAK-WY", combined, "Wyckoff cell content leaked despite being disengaged")
        self.assertIn("lane-ict", combined, "ICT column should still render when engaged")
        self.assertIn("LEAK-ICT", combined)
        self.assertIn("tắt trong /automation", combined, "the disengaged reason must be stated somewhere, not silently dropped")


class MatrixColumnCountHasACssRule(unittest.TestCase):
    """General over every registered preset (docs/architecture/methods.json), not a hardcoded pair: whatever
    column count a preset's engaged dimensions produce, the page's CSS must define --n for that count, or the
    grid collapses (Task 10b item 1). A future 5th dimension or new preset re-triggers this automatically."""

    def test_every_preset_dimension_count_has_a_matching_css_rule(self):
        ba = load("build-artifact.py")
        methods = load("methods.py")
        seen_cols = set()
        for preset in methods.PRESETS:
            dims = {d: {"engaged": d in preset["dimensions"], "reason": ""} for d in methods.ALL_DIMENSIONS}
            html = ba.matrix("btc", "int", None, None, None, dims)
            m = re.search(r'class="matrix (cols-\d+)"', html)
            self.assertIsNotNone(m, f"preset '{preset['id']}' did not emit a cols-N class")
            seen_cols.add(m.group(1))
            self.assertIn(f".matrix.{m.group(1)}{{", ba.CSS,
                          f"preset '{preset['id']}' emits {m.group(1)} but the CSS has no rule for it")
        # sanity: the presets in methods.json actually exercise more than one column count (else this test
        # could pass vacuously without ever touching the cols-1 case)
        self.assertGreater(len(seen_cols), 1, "presets did not exercise multiple column counts")


class MatrixFooterExplainsEveryDisengagedLane(unittest.TestCase):
    """A wyckoff or ict lane switched off must vanish from the page with a stated reason, same as
    footprint/heatmap already did (Task 10b item 2)."""

    def test_footer_notes_cover_all_four_lanes_not_just_footprint_and_heatmap(self):
        ba = load("build-artifact.py")
        # one lane engaged (footprint) so the matrix renders normally rather than the cols-0 "nothing on" notice
        dims = {
            "wyckoff": {"engaged": False, "reason": "tắt trong /automation"},
            "ict": {"engaged": False, "reason": "tắt trong /automation (khác)"},
            "footprint": {"engaged": True, "reason": "đang dùng"},
            "heatmap": {"engaged": False, "reason": "không có nguồn CoinGlass live"},
        }
        html = ba.matrix("btc", "int", None, None, None, dims)
        for label, reason in (("Wyckoff", "tắt trong /automation"), ("ICT", "tắt trong /automation (khác)"),
                              ("Heatmap", "không có nguồn CoinGlass live")):
            self.assertIn(label, html, f"{label} missing from footer notes")
            self.assertIn(reason, html, f"reason for {label} missing from footer notes")


class LaneButtonsReflectRealEngagement(unittest.TestCase):
    """lane_btns must mark a lane 'off' from the same dims state the matrix/chart use -- not a hardcoded
    wyckoff/ict-are-always-on, everything-else-is-off pair (Task 10b item 3)."""

    def test_lane_button_off_class_is_driven_by_engagement_not_a_hardcoded_pair(self):
        ba = load("build-artifact.py")
        # wyckoff off, footprint on: the inverse of the old hardcode (old code always marked wyckoff "on"
        # and footprint "off" regardless of these flags)
        engaged = {"wyckoff": False, "ict": True, "footprint": True, "heatmap": False}
        html = ba.lane_buttons(engaged)
        self.assertIn('lane-btn lane-wyckoff off', html, "wyckoff should be 'off' when disengaged")
        self.assertNotIn('lane-btn lane-ict off', html, "ict should not be 'off' when engaged")
        self.assertIn('lane-btn lane-footprint"', html, "footprint should not be 'off' when engaged")
        self.assertIn('lane-btn lane-heatmap off', html, "heatmap should be 'off' when disengaged")


class ChartJsReadsInjectedLaneFacts(unittest.TestCase):
    """chart.js must not hand-keep a 4th copy of the lane list, and must not hardcode which lanes draw
    overlays / show volume -- those come from the builder's injected params (Task 10b item 4)."""

    def test_no_hardcoded_lane_array_in_chart_js(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("['wyckoff','ict','footprint','heatmap']", src)
        self.assertNotIn('["wyckoff","ict","footprint","heatmap"]', src)

    def test_drawn_lane_check_is_not_a_hardcoded_wyckoff_ict_pair(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("lane==='wyckoff'||lane==='ict'", src)

    def test_page_params_carry_lane_order_labels_overlay_and_volume_lanes(self):
        b = load("build-artifact.py")
        real_read = b.read_json
        keep = ("analysis-params.json", "automation-config.json")
        b.read_json = lambda path, default=None: real_read(path, default) if path.endswith(keep) else default
        b.candles = lambda sym, tf, n, snap=None: (synth(n, step_min=b.TF_MIN.get(tf, 15)), "2026-09-12T00:00:00Z", "test-fixture")
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "scalping.html")
            b.build("scalping", out)
            html = open(out, encoding="utf-8").read()
            at = html.find("TChart.init(")
            dec = json.JSONDecoder()
            data, end = dec.raw_decode(html, at + len("TChart.init("))
            params, _ = dec.raw_decode(html, html.index("{", end))
            self.assertEqual(params.get("laneOrder"), ["wyckoff", "ict", "footprint", "heatmap"])
            self.assertIn("wyckoff", params.get("laneLabels", {}))
            self.assertEqual(set(params.get("overlayLanes", [])), {"wyckoff", "ict"})
            panes = params.get("panes", {})
            self.assertEqual(panes["wyckoff"]["kind"], "volume")
            self.assertEqual(panes["ict"]["kind"], "range_pct")
            self.assertEqual(panes["footprint"]["kind"], "unavailable")
            self.assertEqual(panes["heatmap"]["kind"], "unavailable")
            self.assertTrue(panes["ict"]["label"])
            sym = next(iter(data.values()))
            self.assertIn("engaged", sym)
            self.assertTrue(set(sym["engaged"]) <= {"wyckoff", "ict", "footprint", "heatmap"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PageChromeNamesOnlyTheEngagedMethods(unittest.TestCase):
    """The tables were gated method-by-method (matrix/ladder/timeline above); the page CHROME was not. The lede
    said "đọc bằng Wyckoff (giá + khối lượng) và ICT (cấu trúc giá) riêng rẽ, rồi tổng hợp" as a plain string
    literal on every page, while markets.crypto.dimensions had been {wyckoff:false, ict:true} — ICT only — since
    2026-09-12. A reader was told two methods were cross-checked and synthesised when exactly one ran, and
    "rồi tổng hợp" named a synthesis step that cannot exist with one method.

    Three more strings had the same defect (the footer's "Chế độ …: Wyckoff + ICT", the unconditional
    "Footprint lấy Wyckoff làm nền", and the dims reason text), the glossary printed all four methods'
    terminology regardless, and the chart hint advertised "phím 1–4".

    Nothing caught it because method_purity.py only inspects per-method ANALYSIS blocks
    (method_purity.narrative_blocks / model_blocks) — page chrome is never submitted to the checker. Which is
    the irony worth pinning: the old lede contains "khối lượng", so violations(lede, "ict") would have
    rejected it outright had it ever been checked."""

    ALL = ("wyckoff", "ict", "footprint", "heatmap")

    def clause(self, *on):
        ba = load("build-artifact.py")
        return ba.method_clause({d: d in on for d in self.ALL})

    def test_one_engaged_method_is_named_alone_with_no_synthesis_claim(self):
        c = self.clause("ict")
        self.assertIn("ICT", c)
        self.assertIn("cấu trúc giá", c, "the dimension's own reading basis must still be stated")
        self.assertNotIn("Wyckoff", c)
        self.assertNotIn("khối lượng", c, "Wyckoff's reading basis must not appear in an ICT-only clause")
        self.assertNotIn("riêng rẽ", c, "'separately' is meaningless with one method")
        self.assertNotIn("tổng hợp", c, "there is no synthesis step with one method")

    def test_wyckoff_only_is_the_mirror_case(self):
        c = self.clause("wyckoff")
        self.assertIn("Wyckoff", c)
        self.assertIn("khối lượng", c)
        self.assertNotIn("ICT", c)
        self.assertNotIn("tổng hợp", c)

    def test_two_engaged_methods_keep_the_separate_then_synthesise_wording(self):
        c = self.clause("wyckoff", "ict")
        self.assertIn("Wyckoff", c)
        self.assertIn("ICT", c)
        self.assertIn("riêng rẽ", c)
        self.assertIn("tổng hợp", c)

    def test_four_engaged_methods_name_all_four(self):
        c = self.clause(*self.ALL)
        for label in ("Wyckoff", "ICT", "Footprint", "Heatmap"):
            self.assertIn(label, c)
        self.assertIn("tổng hợp", c)

    def test_no_engaged_method_says_so_instead_of_naming_one(self):
        c = self.clause()
        for label in ("Wyckoff", "ICT", "Footprint", "Heatmap"):
            self.assertNotIn(label, c, "a page with no engaged lane must not name a method at all")
        self.assertIn("/automation", c, "it must say where the switch is")

    def test_the_clause_reads_its_glosses_from_the_registry_not_a_literal(self):
        """methods.json is the single source for the Vietnamese reading-basis gloss, the same way `label` and
        `pane` already are. A second copy in build-artifact.py is how the first defect happened."""
        import json as _j
        reg = _j.load(open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8"))
        for d, v in reg["dimensions"].items():
            self.assertIn("reads", v, f"dimension {d} has no `reads` gloss in methods.json")
            self.assertIn(v["reads"], self.clause(d), f"{d}'s clause must quote its registry gloss verbatim")

    def test_glossary_prints_only_engaged_lanes(self):
        ba = load("build-artifact.py")
        html = ba.glossary({d: d == "ict" for d in self.ALL})
        self.assertIn("lane-ict", html)
        for off in ("wyckoff", "footprint", "heatmap"):
            self.assertNotIn(f"lane-{off}", html, f"{off} terminology must not print when the lane is disengaged")
        self.assertNotIn("Cao trào bán", html, "a disengaged method's glossary entries must not render")

    def test_glossary_with_nothing_engaged_renders_no_lane_block(self):
        ba = load("build-artifact.py")
        html = ba.glossary({d: False for d in self.ALL})
        for d in self.ALL:
            self.assertNotIn(f"lane-{d}", html)

    def test_preset_label_names_the_configured_set(self):
        """The footer's "Chế độ" line is about CONFIGURATION (what you asked for), so it reads the flags, not the
        per-symbol engaged state — and it must go through methods.profile_of, which already exists for exactly
        this. Note the flag convention: an ABSENT key means ON (build-artifact.py dims loop, `flag is not False`),
        the opposite of profile_of's truthiness, so the normalisation is load-bearing."""
        ba = load("build-artifact.py")
        self.assertEqual(ba.preset_label({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "ICT")
        self.assertEqual(ba.preset_label({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "Wyckoff + ICT")
        self.assertEqual(ba.preset_label({}, "crypto"), "Đầy đủ 4 chiều", "absent keys mean ON, so {} is all four")
        self.assertEqual(ba.preset_label({"wyckoff": False, "ict": True}, "cfd"), "ICT",
                         "cfd has no footprint/heatmap at all, so their absent keys must not read as ON there")

    def test_mode_is_paired_with_the_preset_it_belongs_to(self):
        """The footer printed the NARRATIVE's recorded mode next to a hard-coded "Wyckoff + ICT". Once the config
        went ICT-only that read "NORMAL: ICT", which contradicts itself -- NORMAL's minimum is 2 engaged
        dimensions (methods.json modes). The mode must come from the same preset as the name, via
        methods.mode_of, which is documented as the only function allowed to decide a run is SOLO."""
        ba = load("build-artifact.py")
        self.assertEqual(ba.preset_mode({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "SOLO")
        self.assertEqual(ba.preset_mode({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "NORMAL")
        self.assertEqual(ba.preset_mode({}, "crypto"), "NORMAL", "all four dimensions is the `full` preset, mode NORMAL")

    def test_no_live_source_names_only_market_relevant_coinglass_dimensions(self):
        ba = load("build-artifact.py")
        off_all = ba.no_live_source({d: False for d in self.ALL}, "crypto")
        self.assertIn("Footprint", off_all)
        self.assertIn("Heatmap", off_all)
        self.assertNotIn("Wyckoff", off_all, "Wyckoff reads candles, not CoinGlass")
        self.assertEqual(ba.no_live_source({"footprint": True, "heatmap": True}, "crypto"), "",
                         "nothing to report when both CoinGlass lanes are engaged")
        self.assertEqual(ba.no_live_source({d: False for d in self.ALL}, "cfd"), "",
                         "cfd has no footprint/heatmap dimension at all, so there is no missing source to report")

    def test_no_hardcoded_method_pair_survives_in_code(self):
        """srcscan strips comments and docstrings, so the explanation above may name the string it bans -- the
        mistake this repo has now made four times (test_min_rr_and_risk.py, test_one_system.py)."""
        import sys as _s
        _s.path.insert(0, os.path.join(ROOT, "scripts", "tests"))
        import srcscan
        code = srcscan.code_text("scripts/build-artifact.py")
        self.assertNotIn("Wyckoff + ICT", code, "the method pair must be derived from the engaged/configured set")
        self.assertNotIn("giá + khối lượng", code, "the reading-basis gloss belongs to methods.json")
        self.assertNotIn("phím 1–4", code, "the lane-key hint must count the lanes it actually renders")


class IctOnlyPageMentionsWyckoffNowhereInItsChrome(unittest.TestCase):
    """End-to-end version of the class above: build a real page with an ICT-only config and assert the rendered
    HTML never names Wyckoff outside a lane button (the buttons deliberately keep all four, greyed, so the
    reader can see what is switched off)."""

    def test_built_page_lede_and_glossary_are_ict_only(self):
        b = load("build-artifact.py")
        real_read = b.read_json
        cfg = {"markets": {"crypto": {"dimensions": {"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}}}}

        def fake_read(path, default=None):
            if path.endswith("automation-config.json"):
                return cfg
            return real_read(path, default) if path.endswith("analysis-params.json") else default

        b.read_json = fake_read
        b.candles = lambda sym, tf, n, snap=None: (synth(n, step_min=b.TF_MIN.get(tf, 15)), "2026-09-12T00:00:00Z", "test-fixture")
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "p.html")
            b.build("scalping", out)
            html = open(out, encoding="utf-8").read()
            lede = html.split('<div class="lede">', 1)[1].split("</div>", 2)[0]
            self.assertIn("ICT", lede)
            self.assertNotIn("Wyckoff", lede, "ICT-only page must not claim a Wyckoff read in its lede")
            self.assertNotIn("tổng hợp", lede, "ICT-only page must not claim a synthesis step")
            self.assertIn("Bias → Cấu trúc → Vào lệnh", lede, "the tier ladder is method-independent and stays")
            self.assertNotIn("Cao trào bán", html, "Wyckoff glossary entries must not render on an ICT-only page")
            self.assertNotIn("Footprint lấy Wyckoff làm nền", html, "that rule only applies when Footprint is engaged")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
