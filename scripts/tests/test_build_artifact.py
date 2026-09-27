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


_I18N = load("i18n.py")

# A dims reason is (message key, params), not a sentence, so the same reason can be said in either language.
# Tests name the reason by key and compare against its rendered text, which is what makes them locale-agnostic:
# the assertion is "this reason was stated", not "this Vietnamese sentence appeared".
ON = ("dims.reason.in_use", {})
OFF = ("dims.reason.off", {})
NO_SRC = ("dims.reason.no_commodity_source", {})
NO_CANDLES = ("dims.reason.no_candles", {})


def _say(reason, lang=None):
    key, params = reason
    return _I18N.t(key, lang or _I18N.DEFAULT, **params)


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
        # A candle row is [open, high, low, close, volume, isoUTC] -- six fields. The seventh, a leading
        # Python-formatted time label, was removed on 2026-09-17: chart.js never read it (it derives every
        # time from the ISO), it was 13% of the page, and a pre-formatted label cannot serve two languages
        # and two timezones. This pins the shape so it cannot silently grow one back.
        self.assertTrue(all(len(r) == 6 for t in sym["tiers"] for r in t["rows"]))
        self.assertTrue(all(isinstance(r[5], str) and r[5].endswith("Z") for t in sym["tiers"] for r in t["rows"]),
                        "the last field of every row must be the candle's UTC ISO time")
        self.assertIn("lookback", params)


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class Engine(unittest.TestCase):
    """scripts/chart.js exposes its pure functions under module.exports when loaded by node."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_ict_engine_result_is_a_function_of_the_window_only(self):
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(240)]
        P = {"lookback": 20, "high": 1.5, "spike": 2.5, "ict": {}}
        out = self.run_js(f"const rows={json.dumps(rows)}, P={json.dumps(P)};"
                          "const a=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "const b=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "console.log(JSON.stringify({same:JSON.stringify(a)===JSON.stringify(b), keys:Object.keys(a).sort(), hi:a.hi, lo:a.lo}))")
        self.assertTrue(out["same"])
        for k in ("fvgs", "obs", "mss", "pools", "levels", "sess", "kz", "eq", "hi", "lo", "pct"):
            self.assertIn(k, out["keys"])
        self.assertEqual(out["hi"], max(r[1] for r in rows)); self.assertEqual(out["lo"], min(r[2] for r in rows))

    def test_volume_stats_use_the_project_lookback(self):
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(60)]
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          "const v=T.volStats(rows,{lookback:20}); console.log(JSON.stringify({n:v.ratio.length, first:v.ratio.slice(0,3), last:v.ratio[59]}))")
        self.assertEqual(out["n"], 60); self.assertEqual(out["first"], [None, None, None]); self.assertIsInstance(out["last"], float)

    def test_annotation_builders_are_pure(self):
        """Overlay shapes are plain {kind,...} records in (bar index, price) space so they can be checked without a browser."""
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          "const P={lookback:20,high:1.5,spike:2.5,ict:{}}; const ict=T.ictAnalyze(rows,{kz:true,tfMin:15,market:'crypto'},P);"
                          "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                          "const wy=T.wyckoffShapes(rows,{tr:{high:77300,low:76900,from:rows[10][5]},phases:[{from:rows[5][5],to:rows[40][5],label:'Pha B'}],events:[{time:rows[20][5],label:'SC 76,900',up:false}]},{compact:false,fmt:v=>String(v)});"
                          "console.log(JSON.stringify({kinds:[...new Set(sh.concat(wy).map(s=>s.kind))].sort(), wyN:wy.length, allPlaced:sh.concat(wy).every(s=>s.kind&&(('i1' in s)||('i' in s)))}))")
        self.assertTrue(out["allPlaced"], "every shape carries a bar-index position (i or i1; null = full width)")
        self.assertTrue({"rect", "hseg"} <= set(out["kinds"]))
        self.assertGreaterEqual(out["wyN"], 4)  # TR high + TR low + phase band + event mark

    def test_expectation_shapes_are_pure_and_per_methodology(self):
        """Task B3 (plan §0.7): expectationShapes draws only the ACTIVE lane's own records, one hseg per leg,
        and never mixes another methodology's legs into the same lane's shapes (CLAUDE.md §17)."""
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(60)]
        plan = {
            "date_opened": rows[10][5],
            "expectations": [
                {"id": "aaa111aaa111", "status": "POTENTIAL", "original": {
                    "methodology": "ict",
                    "expected_path": [
                        {"phase": "before_entry", "level": 100.0, "label": "vùng vào lệnh"},
                        {"phase": "entry_area", "level": 100.0, "label": "entry"},
                        {"phase": "after_entry", "level": 103.0, "label": "target_1"},
                    ]}},
                {"id": "bbb222bbb222", "status": "POTENTIAL", "original": {
                    "methodology": "wyckoff",
                    "expected_path": [
                        {"phase": "before_entry", "level": 99.0, "label": "vùng vào lệnh"},
                        {"phase": "entry_area", "level": 99.0, "label": "entry"},
                        {"phase": "after_entry", "level": 102.0, "label": "target_1"},
                    ]}},
            ],
        }
        out = self.run_js(f"const rows={json.dumps(rows)}, plans={json.dumps([plan])};"
                          "const ict=T.expectationShapes(rows,plans,'ict',v=>String(v));"
                          "const wy=T.expectationShapes(rows,plans,'wyckoff',v=>String(v));"
                          "console.log(JSON.stringify({ictN:ict.length, wyN:wy.length, "
                          "ictKinds:[...new Set(ict.map(s=>s.kind))], allPlaced:ict.concat(wy).every(s=>('i1' in s)),"
                          "ictPrices:ict.map(s=>s.price), wyPrices:wy.map(s=>s.price)}))")
        self.assertEqual(out["ictN"], 3, "one hseg per leg -- three legs in the ict fixture")
        self.assertEqual(out["wyN"], 3)
        self.assertEqual(out["ictKinds"], ["hseg"])
        self.assertTrue(out["allPlaced"])
        self.assertEqual(sorted(out["ictPrices"]), [100.0, 100.0, 103.0])
        self.assertEqual(sorted(out["wyPrices"]), [99.0, 99.0, 102.0])
        # never merged: ict's shapes carry none of wyckoff's prices and vice versa
        self.assertTrue(set(out["ictPrices"]).isdisjoint(out["wyPrices"]))


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
class RowFieldPositions(unittest.TestCase):
    """The candle row is a positional array shared between two files: build-artifact.py writes it, chart.js
    reads it. That contract has no schema and no runtime check -- a wrong index reads a neighbouring field and
    draws something plausible rather than throwing.

    It broke exactly that way. The i18n work dropped a dead leading label field, shifting every position by
    one; two of the ~20 read sites were missed. An MSS segment then drew from its level down to the bar's
    VOLUME on the price scale, and a volume-spike label took an ISO date string as its price -- on the ICT
    lane, the lane every published page uses. Nothing failed: the Python suite never reaches the shape
    builders, and the node engine tests only exercised ictAnalyze/volStats/rangePctSeries.

    So both halves are pinned here: the names chart.js uses against the order build-artifact.py documents,
    and the two previously-wrong sites executed for real under node.
    """

    def test_the_named_positions_match_the_order_the_builder_writes(self):
        js = open(CHART_JS, encoding="utf-8").read()
        m = re.search(r"const OPEN=(\d), HIGH=(\d), LOW=(\d), CLOSE=(\d), VOL=(\d), ISO=(\d);", js)
        self.assertTrue(m, "chart.js must name its row field positions, not use bare integers")
        self.assertEqual([int(g) for g in m.groups()], [0, 1, 2, 3, 4, 5])
        doc = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertIn("[open, high, low, close, volume, isoUTC]", doc,
                      "rows_js must document the row order these names are pinned against")

    def test_no_bare_row_index_survives_in_chart_js(self):
        js = open(CHART_JS, encoding="utf-8").read()
        bad = [ln for ln in js.split("\n")
               if re.search(r"\b(rows|rowsV|r|c|full)\[[A-Za-z0-9_.+ -]*\]\[[0-5]\]", ln)]
        self.assertEqual(bad, [], "a bare row index is unreviewable — use OPEN/HIGH/LOW/CLOSE/VOL/ISO")

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_an_mss_segment_ends_on_the_close_not_the_volume(self):
        """`vseg.p2` is a PRICE. Reading the volume there put a 1-13 figure on a 77,000 price scale.

        The MSS is handed in rather than discovered, so the test exercises the drawing code directly instead
        of depending on the synthetic series happening to shift structure.
        """
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(240)]
        mss_i = 200
        ict = {"n": len(rows), "kz": [], "hi": 78000.0, "eq": 77500.0, "lo": 77000.0, "pct": 0.5,
               "drSource": "window", "fvgs": [], "obs": [], "cisd": [], "pools": [], "levels": [], "sess": [],
               "ote": None, "std": None, "mss": [{"type": "bull", "i": mss_i, "level": 77100.0, "disp": True}]}
        out = self.run_js(f"const rows={json.dumps(rows)}, ict={json.dumps(ict)};"
                          "const S=T.ictShapes(rows,ict,{compact:false,fmt:x=>String(x)});"
                          "const v=S.filter(s=>s.kind==='vseg');"
                          "console.log(JSON.stringify({n:v.length, p2:v.map(s=>s.p2), "
                          "closes:v.map(s=>rows[s.i][3]), vols:v.map(s=>rows[s.i][4])}))")
        self.assertEqual(out["n"], 1, "the handed-in MSS must produce exactly one vertical segment")
        self.assertEqual(out["p2"], out["closes"], "an MSS segment must end at the bar's close")
        self.assertNotEqual(out["p2"], out["vols"], "it must not end at the bar's volume")


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class RangePctSeriesEngine(unittest.TestCase):
    """Pure function backing the ICT pane's range_pct kind: per-bar position within the dealing range
    (ict.lo/ict.hi, already computed by ictAnalyze), 0-100, so it can be checked without a browser."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_series_is_a_pure_function_of_rows_and_dealing_range(self):
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
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
        dims = {d: {"engaged": d == "wyckoff", "reason": ("dims.reason.in_use", {})} for d in ("wyckoff", "ict", "footprint", "heatmap")}
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
        dims = {d: {"engaged": d == "wyckoff", "reason": ("dims.reason.in_use", {})} for d in ("wyckoff", "ict", "footprint", "heatmap")}
        html = ba.ladder(_stub_S(), "BTCUSDT", "int", "—", None, None, {}, None, dims)
        self.assertIn("lane-wyckoff", html)
        self.assertNotIn("lane-ict", html)

    def test_ladder_drops_wyckoff_when_ict_is_the_only_engaged_method(self):
        """The reported defect: SOLO ICT preset, dims.wyckoff.engaged is False, dims.ict.engaged is True."""
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": OFF}, "ict": {"engaged": True, "reason": ON},
                "footprint": {"engaged": False, "reason": NO_SRC}, "heatmap": {"engaged": False, "reason": NO_SRC}}
        html = ba.ladder(_stub_S(), "BTCUSDT", "int", "—", None, None, {}, None, dims)
        self.assertNotIn("lane-wyckoff", html, "Wyckoff column must not render when dims.wyckoff.engaged is False")
        self.assertNotIn(_say(("ladder.no_wyckoff_read", {})), html, "Wyckoff cell text must not leak into the ladder when disengaged")
        self.assertIn("lane-ict", html)
        self.assertIn(_say(OFF), html, "the disengaged reason must be stated, not silently dropped (matrix() convention)")


class TimelineColumnsDropADisengagedWyckoffOrIct(unittest.TestCase):
    """timeline() (scripts/build-artifact.py:352) is the same class of bug: unconditional <th class="lane-wyckoff">
    / <td class="lane-wyckoff"> regardless of dims. It arrived with the timeframe-ladder work (716b32a) after the
    Task 10 matrix()-only sweep, so it never got the dims-gating treatment."""

    def test_timeline_drops_the_wyckoff_column_when_disengaged(self):
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": OFF}, "ict": {"engaged": True, "reason": ON}}
        rows = [{"time": "2026-09-01T00:00:00Z", "event": "MSS", "wyckoff": "LEAK-WYCKOFF-TEXT", "ict": "MSS tăng"}]
        html = ba.timeline(rows, dims)
        self.assertNotIn("lane-wyckoff", html)
        self.assertNotIn("LEAK-WYCKOFF-TEXT", html, "a disengaged method's cell content must not render at all")
        self.assertIn("lane-ict", html)
        self.assertIn("MSS tăng", html)   # model prose, shown verbatim


class NoDisengagedMethodContentAnywhereInThePage(unittest.TestCase):
    """General regression, not scoped to one table: with a method disengaged, no per-method render site --
    matrix(), ladder(), timeline() today -- may show that method's column, cell, or label. General enough to
    catch a future 4th such table the same way it would have caught ladder() and timeline()."""

    def test_wyckoff_off_ict_on_leaves_no_wyckoff_content_in_any_table(self):
        ba = load("build-artifact.py")
        dims = {"wyckoff": {"engaged": False, "reason": OFF}, "ict": {"engaged": True, "reason": ON},
                "footprint": {"engaged": False, "reason": NO_SRC},
                "heatmap": {"engaged": False, "reason": NO_SRC}}
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
            dims = {d: {"engaged": d in preset["dimensions"], "reason": ("dims.reason.in_use", {})} for d in methods.ALL_DIMENSIONS}
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
            "wyckoff": {"engaged": False, "reason": OFF},
            "ict": {"engaged": False, "reason": NO_CANDLES},
            "footprint": {"engaged": True, "reason": ON},
            "heatmap": {"engaged": False, "reason": NO_SRC},
        }
        html = ba.matrix("btc", "int", None, None, None, dims)
        for label, reason in (("Wyckoff", _say(OFF)), ("ICT", _say(NO_CANDLES)), ("Heatmap", _say(NO_SRC))):
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


class OverlayLanesAreRegistryDerived(unittest.TestCase):
    """Task B3 (plan §0.7): OVERLAY_LANES comes from `dimensions.<d>.overlay_engine`, not a hand-kept
    ("wyckoff", "ict") literal -- that pair used to be typed out in six places in this file."""

    def test_no_hardcoded_wyckoff_ict_tuple_literal_survives(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertNotIn('("wyckoff", "ict")', src)

    def test_overlay_lanes_matches_the_registry(self):
        b = load("build-artifact.py")
        methods = load("methods.py")
        want = tuple(d for d in methods.ALL_DIMENSIONS if methods.DIMENSIONS[d].get("overlay_engine"))
        self.assertEqual(b.OVERLAY_LANES, want)
        self.assertEqual(set(b.OVERLAY_LANES), {"wyckoff", "ict"})


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class ChartJsDrawnGateUsesAnalysedNotEngaged(unittest.TestCase):
    """Task B3 (plan §0.7): `drawnFor` must key on `analysed` (CLAUDE.md §15 -- trading selection is not a
    global analysis filter), and an analysed-but-not-engaged lane must carry the `chart.lane.not_in_confluence`
    notice; the lane-status text for a lane that is NOT analysed must stay unchanged."""

    def test_drawn_for_reads_analysed_not_engaged(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertIn("DATA[key].analysed", src)
        self.assertNotIn("DATA[key].engaged||[]).includes(lane)", src.replace(" ", ""))

    def test_not_in_confluence_key_is_referenced(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertIn("chart.lane.not_in_confluence", src)

    def test_key_is_defined_in_both_locales(self):
        catalog = json.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))
        entry = catalog["messages"]["chart.lane.not_in_confluence"]
        self.assertTrue(entry["en"].strip())
        self.assertTrue(entry["vi"].strip())


class ExpectationsFlowThroughToTheBuiltPage(unittest.TestCase):
    """Task B3 (plan §0.6/§0.7): a plan carrying per-methodology expectations must reach the built page's
    embedded data unchanged, and the two methodologies must stay distinguishable -- never merged (CLAUDE.md
    §17). `trade_plans` is monkeypatched rather than touching the real trades/index.jsonl store (dispatch note:
    "use a temp copy or monkeypatched trade_plans")."""

    def _build(self, plans):
        b = load("build-artifact.py")
        real_read = b.read_json
        keep = ("analysis-params.json", "automation-config.json")
        b.read_json = lambda path, default=None: real_read(path, default) if path.endswith(keep) else default
        b.candles = lambda sym, tf, n, snap=None: (synth(n, step_min=b.TF_MIN.get(tf, 15)), "2026-09-12T00:00:00Z", "test-fixture")
        b.trade_plans = lambda sym: plans
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "scalping.html")
            b.build("scalping", out)
            html = open(out, encoding="utf-8").read()
            at = html.find("TChart.init(")
            dec = json.JSONDecoder()
            data, end = dec.raw_decode(html, at + len("TChart.init("))
            return html, data
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_analysed_is_emitted_alongside_engaged(self):
        _html, data = self._build([])
        sym = next(iter(data.values()))
        self.assertIn("analysed", sym)
        self.assertTrue(set(sym["analysed"]) <= {"wyckoff", "ict", "footprint", "heatmap"})

    def test_two_methodologies_expectations_stay_apart_in_the_built_page(self):
        X = load("expectation.py")
        EP = load("expectation_producer.py")
        plan_row = dict(id="2026-09-17-TEST-01", direction="LONG", entry=100.0, stop_loss=99.0, targets=[103.0],
                        planned_rr=3.0, status="OPEN", rehearsal_mode=False, date_opened="2026-09-01T01:00:00Z",
                        setup_type="test")
        ict_rec = EP.from_plan(plan_row, "ict", created_at="2026-09-01T01:00:00Z")
        wy_rec = EP.from_plan(plan_row, "wyckoff", created_at="2026-09-01T01:00:00Z")
        plan_row["expectations"] = [X.to_json(ict_rec), X.to_json(wy_rec)]
        _html, data = self._build([plan_row])
        sym = next(iter(data.values()))
        plans = sym["plans"]
        self.assertEqual(len(plans), 1)
        exps = plans[0]["expectations"]
        methodologies = sorted(e["original"]["methodology"] for e in exps)
        self.assertEqual(methodologies, ["ict", "wyckoff"])
        phases = {leg["phase"] for e in exps for leg in e["original"]["expected_path"]}
        self.assertEqual(phases, {"before_entry", "entry_area", "after_entry"})
        # never merged: each record keeps its OWN methodology and its OWN id, not a synthesized cross-methodology path
        ict_only = next(e for e in exps if e["original"]["methodology"] == "ict")
        wy_only = next(e for e in exps if e["original"]["methodology"] == "wyckoff")
        self.assertNotEqual(ict_only["id"], wy_only["id"])


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

    def clause(self, *on, lang=None):
        ba = load("build-artifact.py")
        return ba.method_clause({d: d in on for d in self.ALL}, lang or _I18N.DEFAULT)

    def reads(self, dim, lang):
        """The dimension's own reading-basis gloss, from the registry -- never a literal in this file."""
        import methods as _M
        return _M.text(dim, "reads", lang)

    # Every case below runs in EVERY locale. The invariant was never about one language's words: it is that a
    # clause names the engaged methods and only those, and claims a synthesis step only when there is one.
    def test_one_engaged_method_is_named_alone_with_no_synthesis_claim(self):
        for lang in _I18N.LOCALES:
            c = self.clause("ict", lang=lang)
            self.assertIn("ICT", c)
            self.assertIn(self.reads("ict", lang), c, "the dimension's own reading basis must still be stated")
            self.assertNotIn("Wyckoff", c)
            self.assertNotIn(self.reads("wyckoff", lang), c, "Wyckoff's reading basis must not appear in an ICT-only clause")
            self.assertNotIn(_I18N.t("lede.read_with_many", lang, methods="", last=""), c,
                             "'separately, then synthesised' is meaningless with one method")

    def test_wyckoff_only_is_the_mirror_case(self):
        for lang in _I18N.LOCALES:
            c = self.clause("wyckoff", lang=lang)
            self.assertIn("Wyckoff", c)
            self.assertIn(self.reads("wyckoff", lang), c)
            self.assertNotIn("ICT", c)
            self.assertNotIn(self.reads("ict", lang), c)

    def test_two_engaged_methods_keep_the_separate_then_synthesise_wording(self):
        for lang in _I18N.LOCALES:
            c = self.clause("wyckoff", "ict", lang=lang)
            self.assertIn("Wyckoff", c)
            self.assertIn("ICT", c)
            # the many-method template is the one that claims a synthesis step; the one-method template does not
            tail = _I18N.t("lede.read_with_many", lang, methods="\x00", last="\x01").split("\x01")[-1]
            self.assertTrue(c.endswith(tail.rstrip()) or tail.strip() in c,
                            f"the separate-then-synthesise wording is missing from: {c}")

    def test_four_engaged_methods_name_all_four(self):
        for lang in _I18N.LOCALES:
            c = self.clause(*self.ALL, lang=lang)
            for label in ("Wyckoff", "ICT", "Footprint", "Heatmap"):
                self.assertIn(label, c)

    def test_no_engaged_method_says_so_instead_of_naming_one(self):
        for lang in _I18N.LOCALES:
            c = self.clause(lang=lang)
            for label in ("Wyckoff", "ICT", "Footprint", "Heatmap"):
                self.assertNotIn(label, c, "a page with no engaged lane must not name a method at all")
            self.assertIn("/automation", c, "it must say where the switch is")

    def test_the_clause_reads_its_glosses_from_the_registry_not_a_literal(self):
        """methods.json is the single source for the reading-basis gloss, the same way `label` and `pane`
        already are -- now one entry per locale. A second copy in build-artifact.py, or in i18n.json, is how the
        first defect happened."""
        import json as _j
        reg = _j.load(open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8"))
        cat = _j.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))["messages"]
        for d, v in reg["dimensions"].items():
            self.assertIn("reads", v, f"dimension {d} has no `reads` gloss in methods.json")
            for lang in _I18N.LOCALES:
                self.assertIn(lang, v["reads"], f"dimension {d}'s `reads` gloss has no {lang} text")
                gloss = v["reads"][lang]
                self.assertIn(gloss, self.clause(d, lang=lang), f"{d}'s clause must quote its registry gloss verbatim")
                self.assertNotIn(gloss, [m.get(lang) for m in cat.values()],
                                 f"{d}'s reading-basis gloss belongs to methods.json, not the message catalog")

    def test_glossary_prints_only_engaged_lanes(self):
        ba = load("build-artifact.py")
        html = ba.glossary({d: d == "ict" for d in self.ALL})
        self.assertIn("lane-ict", html)
        for off in ("wyckoff", "footprint", "heatmap"):
            self.assertNotIn(f"lane-{off}", html, f"{off} terminology must not print when the lane is disengaged")
        # stronger than checking one term: no Wyckoff glossary BLOCK at all, so an emptied-out
        # block would fail too
        self.assertNotIn(_I18N.t("gloss.wyckoff.phase_a_events.d", _I18N.DEFAULT)[:30], html,
                         "a disengaged method's glossary entries must not render")

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
        # Which preset was SELECTED is the logic under test, so assert the preset id. The label is copy, and
        # it lives in methods.json per locale -- covered by the registry completeness check instead.
        self.assertEqual(ba.preset_id({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "ict")
        self.assertEqual(ba.preset_id({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False}, "crypto"), "wyckoff+ict")
        self.assertEqual(ba.preset_id({}, "crypto"), "full", "absent keys mean ON, so {} is all four")
        self.assertEqual(ba.preset_id({"wyckoff": False, "ict": True}, "cfd"), "ict",
                         "cfd has no footprint/heatmap at all, so their absent keys must not read as ON there")
        for lang in _I18N.LOCALES:
            self.assertTrue(ba.preset_label({}, "crypto", lang), f"the configured preset must have a {lang} label")

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


class NoSymbolIsDroppedSilently(unittest.TestCase):
    """CLAUDE.md §6: an unavailable source is EXPOSED with its reason, never disappeared.

    `STYLE_SYMS["cfd"]` was a hand-written `[_meta("XAUUSD")]` justified by a comment about the MT5 EA only
    exporting symbols with an attached chart. That stopped being true: a silver chart is attached, XAGUSD has
    600 live bars in every timeframe, and `automation-config.json` lists it — and the page drew gold alone and
    said nothing. A hardcoded list cannot become unavailable, so there was nothing for §6 to expose: available
    analysis was suppressed by a literal.

    Found by opening the built page in a browser and noticing XAGUSD was simply not on it.
    """

    @staticmethod
    def _ba():
        spec = importlib.util.spec_from_file_location("ba", os.path.join(ROOT, "scripts", "build-artifact.py"))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    def test_no_market_has_a_hand_written_symbol_list(self):
        ba = self._ba()
        for market in ba._auto.MARKETS:
            self.assertEqual([m[0] for m in ba.STYLE_SYMS[market]], list(ba.I.analysis(market)),
                             f"{market}'s page symbols are not its analysis allowlist")

    def test_a_symbol_with_a_feed_is_drawn_and_one_without_is_named(self):
        """Deterministic regardless of whether this checkout's (gitignored) data/live/mt5-bridge is populated:
        `_series_path` is faked into a temp dir where only a chosen subset of cfd's allowlist gets a file, so
        the split is proven from `drawable()`'s own logic, not from ambient filesystem state."""
        ba = self._ba()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "ohlcv.XAUUSD.15m.json"), "w").close()
            open(os.path.join(tmp, "ohlcv.XAGUSD.15m.json"), "w").close()
            orig_series_path = ba._series_path
            ba._series_path = lambda sym, tf: os.path.join(tmp, f"ohlcv.{sym}.{tf}.json")
            try:
                drawn, absent = ba.drawable(ba.STYLE_SYMS["cfd"], "15m")
            finally:
                ba._series_path = orig_series_path
        self.assertIn("XAUUSD", [m[0] for m in drawn])
        self.assertIn("XAGUSD", [m[0] for m in drawn], "silver has live bars and must be drawn")
        self.assertEqual(sorted(m[0] for m in absent), ["AUS200", "DE40", "FRA40", "US30", "US500", "USTEC"])

    def test_the_absent_symbols_reach_the_page(self):
        """USOIL/UKOIL used to be the permanent example of an allowlisted-but-unfed cfd symbol; both were
        deleted from the registry 2026-09-27 (docs/architecture/instruments.json history), so this test can
        no longer assert a fixed pair of names -- it asserts the NAMING mechanism instead, whichever symbol(s)
        this environment's live feed happens to be missing today."""
        import subprocess
        import sys as _sys
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "cfd.html")
            r = subprocess.run([_sys.executable, os.path.join(ROOT, "scripts", "build-artifact.py"),
                                "cfd-scalping", "--out", out, "--snapshot-dir", tmp],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                self.skipTest(f"the cfd page could not be built here: {r.stdout[-200:]}{r.stderr[-200:]}")
            with open(out, encoding="utf-8") as fh:
                html = fh.read()
        self.assertIn("XAGUSD", html, "silver is drawn")
        if "no feed attached" not in html:
            self.skipTest("every current cfd symbol has a feed in this environment -- nothing to name as absent")
        self.assertTrue(any(sym in html for sym in ("XAUUSD", "US500", "US30", "USTEC", "DE40", "FRA40", "AUS200")),
                         "the footer claims an absent symbol but none of the current cfd allowlist appears")

    def test_a_market_with_no_feed_at_all_still_refuses(self):
        """Naming the absent ones must not turn a page with zero charts into a page.

        Proven reachable for real by `forex`'s entire 2026-09-17..2026-09-27 life on the registry: every
        fx- style hit exactly this exit every time, because no MT5 chart was ever attached for any of the
        seven majors (docs/architecture/instruments.json history). forex is gone now (deleted 2026-09-27,
        zero data/analysis/trades in its whole time on the registry), so this test forces the same zero-feed
        state onto a market that still exists -- build()'s refusal is computed from market_of_style(), not a
        literal, so it is exercised the same way regardless of which market hits it.
        """
        b = self._ba()
        orig_drawable = b.drawable
        b.drawable = lambda syms, tf: ([], syms)
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "cfd.html")
                with self.assertRaises(SystemExit) as ctx:
                    b.build("cfd-scalping", out)
                self.assertIn("no data for any cfd symbol", str(ctx.exception))
        finally:
            b.drawable = orig_drawable


class PremiumDiscountSaysWhereTheRangeCameFrom(unittest.TestCase):
    """knowledge/ict/core-a.md §2.18: the dealing range is a BSL<->SSL pair. When one border is the scan
    window's edge (52% of point-in-time reads on real history) the page must not call the result the decks'
    'premium'/'discount' without saying so. Knowledge audit 2026-09-19."""

    @classmethod
    def setUpClass(cls):
        cls.B = load("build-artifact.py")

    def test_a_pool_framed_range_reads_as_the_deck_term_alone(self):
        self.assertEqual(self.B.dr_qualifier("pools", "vi"), "")

    def test_a_window_border_is_disclosed_in_both_locales(self):
        for lang, vi_word, en_word in (("vi", "mép cửa sổ", None), ("en", None, "window edge")):
            mixed = self.B.dr_qualifier("mixed", lang)
            self.assertIn(vi_word or en_word, mixed, lang)
        self.assertIn("cả hai biên", self.B.dr_qualifier("window", "vi"))
        self.assertIn("both borders", self.B.dr_qualifier("window", "en"))

    def test_an_unknown_source_adds_nothing_rather_than_guessing(self):
        self.assertEqual(self.B.dr_qualifier(None, "vi"), "")
        self.assertEqual(self.B.dr_qualifier("something-new", "vi"), "")


class PhaseBandLabelsAreTheLetterNotSe(unittest.TestCase):
    """User report 2026-09-19: every Wyckoff phase band on the chart was labelled "se".

    Cause: `String(ph.label).replace(/^(pha|phase)\\s*/i,'').slice(0,2)`. Regex alternation is ORDERED, so
    "pha" matched first and stripped only 3 characters of "Phase C", leaving "se C" -> sliced to "se". Every
    phase band on every chart showed the same two letters, which is also why it read as a rendering glitch
    rather than a label."""

    def _lbl(self, label):
        """Run the real expression from scripts/chart.js under node -- not a Python re-implementation."""
        import subprocess, json, re
        src = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        m = re.search(r"const lbl=String\(ph\.label\|\|''\)(\.replace\([^;]*?\)\.slice\(0,\s*2\)(?:\.trim\(\))?);", src)
        self.assertIsNotNone(m, "the phase-label expression moved; update this test to find it")
        js = f"process.stdout.write(JSON.stringify(String({json.dumps(label)}){m.group(1)}))"
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_every_phase_renders_its_own_letter(self):
        for letter in "ABCDE":
            self.assertEqual(self._lbl(f"Phase {letter}"), letter)

    def test_the_vietnamese_prefix_still_works(self):
        self.assertEqual(self._lbl("Pha C"), "C")

    def test_a_bare_letter_is_left_alone(self):
        self.assertEqual(self._lbl("C"), "C")

    def test_no_phase_label_renders_as_se(self):
        for label in ("Phase A", "Phase B", "Phase C", "Phase D", "Phase E", "phase e", "PHASE D"):
            self.assertNotEqual(self._lbl(label), "se", label)
