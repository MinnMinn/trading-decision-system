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


if __name__ == "__main__":
    unittest.main()
