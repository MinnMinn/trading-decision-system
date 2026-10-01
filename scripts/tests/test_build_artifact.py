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

    def _page_data(self):
        at = self.html.find("TChart.init(")
        data, _ = json.JSONDecoder().raw_decode(self.html, at + len("TChart.init("))
        return data

    def test_page_data_carries_the_engines_own_structure_objects(self):
        """A2 / ADR 0009: every tier ships the ENGINE's structure list (scripts/structures.py), not a
        chart-side detection. Each object carries kind/formed_at/available_at; an invalidated pool or FVG
        carries invalidated_at >= available_at (A1b); Wyckoff ships {tr, events, phases}; the model-owned
        anchors (`levels`) are not shipped as analysis at all."""
        sym = self._page_data()["btc"]
        self.assertTrue(any(t["ict"]["structures"] for t in sym["tiers"]), "no tier carried an engine ICT object")
        for t in sym["tiers"]:
            self.assertEqual(t["levels"], [], f"{t['key']}: model-owned anchors must not be drawn as analysis")
            self.assertEqual(sorted(t["wy"]), ["events", "phases", "tr"], t["key"])
            self.assertEqual(sorted(t["ict"]), ["bias", "dealing_range", "structures"], t["key"])
            for o in t["ict"]["structures"]:
                for k in ("kind", "formed_at", "available_at"):
                    self.assertIn(k, o, f"{t['key']}: {o}")
                self.assertGreaterEqual(o["available_at"], o["formed_at"], o)
                if o.get("invalidated_at") is not None:
                    self.assertGreaterEqual(o["invalidated_at"], o["available_at"], o)
            for ph in t["wy"]["phases"]:
                self.assertGreaterEqual(ph["available_at"], ph["formed_at"], ph)

    def test_htf_tiers_carry_a_quality_state_and_the_entry_tier_does_not(self):
        """A2b: each higher-timeframe tier ships its own §20 state (a real state word, never absent) and the
        reason that names its age; the entry tier IS the clock, so it carries none."""
        sym = self._page_data()["btc"]
        Q = load("quality.py")
        for t in sym["tiers"]:
            if t["key"] == "entry":
                self.assertIsNone(t["quality"])
            else:
                self.assertIn(t["quality"]["state"], Q.STATES, t["key"])
                self.assertTrue(t["quality"]["reason"], t["key"])


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class Engine(unittest.TestCase):
    """scripts/chart.js exposes its pure functions under module.exports when loaded by node."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_ict_from_structures_is_a_pure_function_of_its_inputs_never_detection(self):
        """A2 / ADR 0009: chart.js's own ICT detector (the old `ictAnalyze`) is gone. `ictFromStructures()`
        does not detect anything -- it only regroups the engine's own flat structure list (scripts/
        structures.py `ict_structures()`, forwarded verbatim by build-artifact.py `ict_json()`) by `kind`.
        Same structs+dealing_range+rows -> same output (pure), and hi/lo/eq come from the ENGINE's
        dealing_range -- never re-derived from the rows the way the removed detector used to (`Math.max(...
        rows.map(r=>r[HIGH]))`)."""
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(60)]
        structs = [
            {"kind": "pool", "pool_kind": "BSL", "level": 78000.0, "from": 5, "to": 5, "type": "old", "invalidated_at": None},
            {"kind": "sweep", "pool_kind": "BSL", "level": 78000.0, "i": 15},
            {"kind": "fvg", "type": "bull", "i": 10, "lo": 77000.0, "hi": 77100.0, "size": 100.0, "ce": 77050.0, "end": 59, "mitigated": False},
            {"kind": "mss", "type": "bull", "i": 20, "level": 77200.0, "disp": True},
        ]
        dealing_range = {"hi": 78000.0, "lo": 76000.0, "eq": 77000.0, "source": "pools"}
        out = self.run_js(f"const rows={json.dumps(rows)}, structs={json.dumps(structs)}, dr={json.dumps(dealing_range)};"
                          "const a=T.ictFromStructures(structs,dr,rows);"
                          "const b=T.ictFromStructures(structs,dr,rows);"
                          "console.log(JSON.stringify({same:JSON.stringify(a)===JSON.stringify(b), keys:Object.keys(a).sort(), "
                          "hi:a.hi, lo:a.lo, eq:a.eq, poolsN:a.pools.length, fvgsN:a.fvgs.length, mssN:a.mss.length, sweptI:a.pools[0].swept}))")
        self.assertTrue(out["same"], "same inputs must give the same output -- no hidden state, no detection")
        for k in ("fvgs", "obs", "mss", "pools", "levels", "sess", "eq", "hi", "lo", "pct", "drSource"):
            self.assertIn(k, out["keys"])
        self.assertEqual(out["hi"], 78000.0); self.assertEqual(out["lo"], 76000.0); self.assertEqual(out["eq"], 77000.0)
        self.assertEqual(out["poolsN"], 1); self.assertEqual(out["fvgsN"], 1); self.assertEqual(out["mssN"], 1)
        self.assertEqual(out["sweptI"], 15, "the pool's sweep mark must come from the matching sweep structure, not a re-detection")

    def test_structure_not_established_is_shown_when_the_engine_found_none(self):
        """A2: an empty engine read (no TR/events/phases; no pivots/pools/FVG/MSS) draws ONE 'not established' note
        and the now dot -- never a blank lane. The note is pinned to the RIGHT EDGE at the last close (i=null): the
        chart shows only the tail of the window, so a bar-index / window-high anchor could sit off-pane and hide the
        very message (seen in the 2026-09-29 BTC 15m capture)."""
        rows = [[100 + i, 102 + i, 98 + i, 101 + i, 10, f"2026-09-01T{i // 4:02d}:{(i % 4) * 15:02d}:00Z"] for i in range(48)]
        out = self.run_js(
            f"const rows={json.dumps(rows)};"
            "const cfg={compact:false,fmt:v=>String(v)};"
            "const wy=T.wyckoffShapes(rows,{tr:null,events:[],phases:[]},cfg);"
            "const ict=T.ictShapes(rows,{fvgs:[],pools:[],mss:[],sweeps:[],pivots:[],hi:150,lo:100,eq:125,pct:0.5,kz:[]},cfg);"
            "console.log(JSON.stringify({wy,ict}));")
        for lane in ("wy", "ict"):
            labels = [x for x in out[lane] if x["kind"] == "label"]
            self.assertEqual(len(labels), 1, (lane, out[lane]))
            self.assertIsNone(labels[0]["i"], "anchored at the right edge, not at a bar index")
            self.assertEqual(labels[0]["price"], rows[-1][3], "at the last close: always inside the visible range")
            self.assertIn("not_established", labels[0]["text"])
            self.assertEqual([x["kind"] for x in out[lane] if x["kind"] != "label"], ["mark"])

    def test_ict_detector_is_gone_from_chart_js(self):
        """A2 / ADR 0009: the chart draws engine structures only -- chart.js must not carry its own ICT
        detection (pivot/pool/FVG/MSS scanning) any more."""
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("ictAnalyze", src)
        self.assertNotIn("ictParams", src)

    def test_volume_stats_use_the_project_lookback(self):
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(60)]
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          "const v=T.volStats(rows,{lookback:20}); console.log(JSON.stringify({n:v.ratio.length, first:v.ratio.slice(0,3), last:v.ratio[59]}))")
        self.assertEqual(out["n"], 60); self.assertEqual(out["first"], [None, None, None]); self.assertIsInstance(out["last"], float)

    def test_annotation_builders_are_pure(self):
        """Overlay shapes are plain {kind,...} records in (bar index, price) space so they can be checked
        without a browser. A2 / ADR 0009: the ICT `ict` object is built via ictFromStructures() from a
        hand-built engine structure list -- ictShapes() itself never detects anything, so there is nothing to
        re-derive here; the fixture stands in for what build-artifact.py's ict_json() would have sent."""
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
        structs = [
            {"kind": "pool", "pool_kind": "BSL", "level": 78000.0, "from": 5, "to": 5, "type": "old", "invalidated_at": None},
            {"kind": "fvg", "type": "bull", "i": 10, "lo": 77000.0, "hi": 77100.0, "size": 100.0, "ce": 77050.0, "end": 119, "mitigated": False},
            {"kind": "mss", "type": "bull", "i": 20, "level": 77200.0, "disp": True},
        ]
        dealing_range = {"hi": 78000.0, "lo": 76000.0, "eq": 77000.0, "source": "pools"}
        out = self.run_js(f"const rows={json.dumps(rows)}, structs={json.dumps(structs)}, dr={json.dumps(dealing_range)};"
                          "const ict=Object.assign(T.ictFromStructures(structs,dr,rows),{kz:T.killzoneSpans(rows,{kz:true,tfMin:15,market:'crypto'})});"
                          "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                          "const wy=T.wyckoffShapes(rows,{tr:{high:77300,low:76900,from:rows[10][5]},phases:[{from:rows[5][5],to:rows[40][5],label:'Pha B',status:'tested'}],events:[{time:rows[20][5],label:'SC 76,900',up:false}]},{compact:false,fmt:v=>String(v)});"
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
    (ict.lo/ict.hi), 0-100, so it can be checked without a browser.

    A2 / ADR 0009: `ict.lo`/`ict.hi` are the ENGINE's dealing_range (scripts/structures.py `ict_structures()`,
    forwarded by build-artifact.py `ict_json()`) -- chart.js's own (removed) `ictAnalyze` detector used to
    compute them client-side. `rangePctSeries` itself only ever read `lo`/`hi` off its `ict` argument, so this
    test hand-builds that dealing_range directly rather than running any detector, engine or otherwise -- the
    same "no detection, only rows-and-a-dealing-range" contract the function's docstring already states."""

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_series_is_a_pure_function_of_rows_and_dealing_range(self):
        rows = [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["time"]] for r in synth(120)]
        lo, hi = min(r[2] for r in rows), max(r[1] for r in rows)
        ict = {"lo": lo, "hi": hi}
        want_pct = (rows[-1][3] - lo) / ((hi - lo) or 1) * 100
        out = self.run_js(f"const rows={json.dumps(rows)}, ict={json.dumps(ict)};"
                          "const s=T.rangePctSeries(rows,ict);"
                          "console.log(JSON.stringify({n:s.length, allInRange:s.every(p=>p.value>=0&&p.value<=100), "
                          "last:s[s.length-1].value}))")
        self.assertEqual(out["n"], 120)
        self.assertTrue(out["allInRange"], "every bar's position must be clamped to [0,100]")
        self.assertAlmostEqual(out["last"], want_pct, places=6,
                                msg="the series' last point must agree with the last bar's own dealing-range position")


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
            self.assertEqual([m[0] for m in ba.STYLE_SYMS[market]], list(ba.I.live_analysis(market)),
                             f"{market}'s page symbols are not its analysis allowlist minus research-only")
            # owner 2026-10-01: research-only symbols (fund-search FX etc.) are never on the live page
            self.assertTrue(set(ba.I.research_only(market)).isdisjoint(m[0] for m in ba.STYLE_SYMS[market]))

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


class A2bStaleHtfTierIsMarkedStaleAgainstTheEntryClock(unittest.TestCase):
    """A2b (CLAUDE.md sections 20/52): a higher-timeframe tier that has not been refreshed to the entry tier's
    clock is STALE -- judged against the CLOCK PASSED IN (the entry tier's data time), never the wall time the
    build happens to run at, and never silently FRESH."""

    def _b(self, series):
        b = load("build-artifact.py")
        b.read_json = lambda path, default=None: series
        return b

    def _series(self, last_updated, n=40, tf_min=240):
        return {"candles": synth(n, step_min=tf_min), "last_updated": last_updated}

    def test_a_tier_last_refreshed_days_before_the_clock_is_stale(self):
        b = self._b(self._series("2026-09-20T00:00:00Z"))
        q = b.tier_quality("BTCUSDT", "4H", "2026-09-25T00:00:00Z")
        self.assertEqual(q["state"], "STALE", q)
        self.assertIn("min ago", q["reason"])                      # the data age vs the clock is stated
        self.assertEqual(q["clock"], "2026-09-25T00:00:00Z")

    def test_the_same_tier_is_fresh_when_the_clock_is_close(self):
        b = self._b(self._series("2026-09-25T00:00:00Z"))
        self.assertEqual(b.tier_quality("BTCUSDT", "4H", "2026-09-25T01:00:00Z")["state"], "FRESH")

    def test_the_verdict_follows_the_clock_not_the_wall_time(self):
        """Same file, two clocks: the state must flip with the clock argument alone."""
        b = self._b(self._series("2026-09-20T00:00:00Z"))
        self.assertEqual(b.tier_quality("BTCUSDT", "4H", "2026-09-20T02:00:00Z")["state"], "FRESH")
        self.assertEqual(b.tier_quality("BTCUSDT", "4H", "2026-09-22T00:00:00Z")["state"], "STALE")

    def test_no_series_is_missing_never_fresh(self):
        b = self._b(None)
        self.assertEqual(b.tier_quality("BTCUSDT", "4H", "2026-09-25T00:00:00Z")["state"], "MISSING")

    def test_the_page_badge_names_the_stale_state(self):
        """The rendered chart title of a STALE tier carries the state word and the age; a FRESH tier carries none."""
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertIn('tier-quality tier-quality-{tq["state"].lower()}', src)
        self.assertIn('if tq and tq["state"] != "FRESH" else ""', src)


def _hist(sym, tf, n):
    d = json.load(open(os.path.join(ROOT, "data", "history", f"ohlcv.{sym}.{tf}.json"), encoding="utf-8"))
    return d["candles"][-n:]


def _rows6(candles):
    return [[c["open"], c["high"], c["low"], c["close"], c.get("volume", 0), c["time"]] for c in candles]


def _avail_iso(candle, tf_min):
    import datetime
    t = datetime.datetime.fromisoformat(candle["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=tf_min)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class A1bReplayNeverLeaksTheFuture(unittest.TestCase):
    """Code-review I1/I2 (CLAUDE.md section 8): at a replay cursor the chart shows only what the ENGINE had made
    available by then. An ATTRIBUTE that happens after the cursor (a pool's invalidation, an FVG's mitigation, the
    dealing range itself) shows as not-yet-happened, and `invalidated_at` -- an AVAILABILITY time (bar open + tf)
    -- is resolved to the bar whose availability it is, not one bar late."""

    run_js = Engine.run_js

    T15 = 15

    def _rows(self, n=40):
        return [[100 + i, 102 + i, 98 + i, 101 + i, 10, f"2026-09-01T{(i * 15) // 60:02d}:{(i * 15) % 60:02d}:00Z"] for i in range(n)]

    def _avail(self, rows, i):
        return _avail_iso({"time": rows[i][5]}, self.T15)

    def _ict(self, rows, structs, dr, cut=None):
        opts = {"tfMin": self.T15}
        if cut:
            opts["cutIso"] = cut
        return self.run_js(f"const rows={json.dumps(rows)}, s={json.dumps(structs)}, dr={json.dumps(dr)};"
                           f"console.log(JSON.stringify(T.ictFromStructures(s,dr,rows,{json.dumps(opts)})))")

    def test_a_pool_line_ends_on_the_bar_whose_availability_is_invalidated_at(self):
        """I2 on synthetic rows: invalidated_at == availability of bar 12 -> the line ends on bar 12 (`to`=12.5)."""
        rows = self._rows()
        structs = [{"kind": "pool", "pool_kind": "BSL", "level": 110.0, "from": 3, "type": "eq",
                    "available_at": self._avail(rows, 6), "invalidated_at": self._avail(rows, 12)}]
        out = self._ict(rows, structs, {})["pools"]
        self.assertEqual(out[0]["to"], 12.5, "one bar late (13.5) is the I2 defect: idxOf matched the OPEN time")

    def test_a_pool_line_end_matches_the_engine_on_real_candles(self):
        """I2 pinned against the engine: for every closed_through pool of a real window, the drawn `to` is the
        engine's own closing bar + 0.5 (structures.py: invalidated_at = availability of `closed_at`, clamped to
        the pool's own availability by S5)."""
        structures = load("structures.py")
        candles = _hist("AUS200", "4H", 480)
        env = structures.ict_structures(candles, 4, "4H", methods=("ict",))
        pools = [s for s in env["structures"] if s["kind"] == "pool"]
        raw = env["analysis"]["pools"]
        self.assertEqual(len(pools), len(raw))
        self.assertTrue([r for r in raw if r["state"] == "closed_through"], "fixture must contain a closed_through pool")
        # a whole real window does not fit on a Windows command line: hand it to node through a file
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "in.json")
            json.dump({"rows": _rows6(candles), "s": env["structures"]}, open(f, "w"))
            drawn = self.run_js(f"const d=JSON.parse(require('fs').readFileSync({json.dumps(f)},'utf8'));"
                                "console.log(JSON.stringify(T.ictFromStructures(d.s,{},d.rows,{tfMin:240}).pools))")
        self.assertEqual(len(drawn), len(pools))
        for d, w, r in zip(drawn, pools, raw):
            if r["state"] == "closed_through":
                own = next(i for i in range(len(candles)) if _avail_iso(candles[i], 240) >= w["available_at"])
                self.assertEqual(d["to"], max(r["closed_at"], own) + 0.5, (w["level"], r["closed_at"]))
            else:
                self.assertIsNone(d["to"])

    def test_an_invalidation_after_the_cursor_leaves_the_pool_open(self):
        rows = self._rows()
        structs = [{"kind": "pool", "pool_kind": "SSL", "level": 90.0, "from": 2, "type": "eq",
                    "available_at": self._avail(rows, 5), "invalidated_at": self._avail(rows, 20)}]
        out = self._ict(rows[:11], structs, {}, cut=self._avail(rows, 10))["pools"]
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0]["to"], "the invalidation had not happened at the cursor")

    def test_an_fvg_mitigated_after_the_cursor_is_drawn_open_and_ends_at_the_cursor_bar(self):
        rows = self._rows()
        f = {"kind": "fvg", "type": "bull", "i": 8, "lo": 100.0, "hi": 101.0, "size": 1.0, "ce": 100.5, "end": 30,
             "mitigated": True, "available_at": self._avail(rows, 9), "invalidated_at": self._avail(rows, 30)}
        out = self._ict(rows[:16], [f], {}, cut=self._avail(rows, 15))["fvgs"]
        self.assertFalse(out[0]["mitigated"], "mitigated after the cursor must not show as mitigated")
        self.assertEqual(out[0]["end"], 15, "an open FVG runs only to the last bar the reader can see")
        out2 = self._ict(rows, [f], {}, cut=self._avail(rows, 35))["fvgs"]
        self.assertTrue(out2[0]["mitigated"])
        self.assertEqual(out2[0]["end"], 30)

    def test_the_dealing_range_is_absent_before_its_available_at(self):
        rows = self._rows()
        dr = {"hi": 110.0, "lo": 95.0, "eq": 102.5, "source": "pools", "available_at": self._avail(rows, 39)}
        cut = self._avail(rows, 20)
        out = self.run_js(f"const rows={json.dumps(rows[:21])}, dr={json.dumps(dr)};"
                          f"const a=T.ictFromStructures([],dr,rows,{{tfMin:{self.T15},cutIso:{json.dumps(cut)}}});"
                          "console.log(JSON.stringify({lo:a.lo,hi:a.hi,eq:a.eq,pct:a.pct,src:a.drSource,"
                          "shapes:T.ictShapes(rows,a,{compact:false,fmt:v=>String(v)}).map(s=>s.kind+':'+(s.text||''))}))")
        self.assertEqual([out["lo"], out["hi"], out["eq"], out["pct"], out["src"]], [None] * 5)
        self.assertFalse([x for x in out["shapes"] if "premium" in x or "discount" in x], out["shapes"])
        out2 = self._ict(rows, [], dr, cut=self._avail(rows, 39))
        self.assertEqual([out2["lo"], out2["hi"]], [95.0, 110.0])

    def test_an_object_with_no_available_at_is_dropped_at_a_cursor_never_assumed_available(self):
        rows = self._rows()
        structs = [{"kind": "mss", "type": "bull", "i": 5, "level": 101.0, "disp": True}]
        self.assertEqual(len(self._ict(rows, structs, {}, cut=self._avail(rows, 20))["mss"]), 0)
        self.assertEqual(len(self._ict(rows, structs, {})["mss"]), 1)

    def test_idx_of_avail_resolves_the_bar_whose_availability_is_the_time(self):
        rows = self._rows()
        iso = self._avail(rows, 7)
        out = self.run_js(f"const rows={json.dumps(rows)};"
                          f"console.log(JSON.stringify([T.idxOfAvail(rows,{json.dumps(iso)},{self.T15}), T.idxOfAvail(rows,null,{self.T15}), "
                          f"T.idxOfAvail(rows,'2000-01-01T00:00:00Z',{self.T15})]))")
        self.assertEqual(out, [7, -1, -1])


class A1bWyckoffReplayUsesAvailability(unittest.TestCase):
    """Code-review I4: replay filters the Wyckoff read by the engine's own `available_at` -- never by formed time,
    which would show a range or an SOS before it was knowable. Objects with no `available_at` are dropped."""

    run_js = Engine.run_js

    WY = {"tr": {"high": 110, "low": 90, "from": "2026-09-01T00:00:00Z", "available_at": "2026-09-01T10:00:00Z"},
          "events": [{"time": "2026-09-01T02:00:00Z", "label": "SC", "up": False, "available_at": "2026-09-01T03:00:00Z"},
                     {"time": "2026-09-01T09:00:00Z", "label": "SOS", "up": True, "available_at": "2026-09-01T12:00:00Z"},
                     {"time": "2026-09-01T04:00:00Z", "label": "ST", "up": False}],
          "phases": [{"from": "2026-09-01T02:00:00Z", "to": "2026-09-01T05:00:00Z", "label": "A", "status": "tested",
                      "available_at": "2026-09-01T10:00:00Z"},
                     {"from": "2026-09-01T09:00:00Z", "to": None, "label": "D", "status": "hypothesis",
                      "available_at": "2026-09-01T12:00:00Z"}]}

    def _at(self, cut):
        return self.run_js(f"console.log(JSON.stringify(T.wyckoffAt({json.dumps(self.WY)},{json.dumps(cut)})))")

    def test_no_cursor_returns_the_read_unchanged(self):
        self.assertEqual(self._at(None), self.WY)

    def test_before_the_range_is_available_nothing_is_shown_even_if_an_event_formed_earlier(self):
        out = self._at("2026-09-01T09:00:00Z")
        self.assertIsNone(out["tr"])
        self.assertEqual(out["events"], [])
        self.assertEqual(out["phases"], [])

    def test_once_the_range_is_available_only_available_events_and_phases_show(self):
        out = self._at("2026-09-01T11:00:00Z")
        self.assertIsNotNone(out["tr"])
        self.assertEqual([e["label"] for e in out["events"]], ["SC"], "SOS formed at 09:00 but is available at 12:00; ST has no available_at")
        self.assertEqual([p["label"] for p in out["phases"]], ["A"], "Phase D is available at 12:00")

    def test_everything_shows_once_everything_is_available(self):
        out = self._at("2026-09-01T12:00:00Z")
        self.assertEqual([e["label"] for e in out["events"]], ["SC", "SOS"])
        self.assertEqual([p["label"] for p in out["phases"]], ["A", "D"])

    def test_a_range_with_no_available_at_is_not_shown_at_a_cursor(self):
        wy = {"tr": {"high": 1, "low": 0, "from": "2026-09-01T00:00:00Z"}, "events": [], "phases": []}
        out = self.run_js(f"console.log(JSON.stringify(T.wyckoffAt({json.dumps(wy)},'2026-09-02T00:00:00Z')))")
        self.assertIsNone(out["tr"])

    def test_the_built_read_carries_available_at_on_every_object(self):
        """build-artifact.py's wy_json_engine ships available_at on tr, events and phases (what wyckoffAt reads)."""
        b = load("build-artifact.py")
        seen = 0
        for sym, tf, kind in (("AUS200", "4H", "cfd"), ("BTCUSDT", "4H", "crypto"), ("ETHUSDT", "4H", "crypto")):
            wy = b.wy_json_engine(_hist(sym, tf, 600), tf, sym, kind)
            if not wy["tr"]:
                continue
            seen += 1
            self.assertTrue(wy["tr"]["available_at"])
            for o in wy["events"] + wy["phases"]:
                self.assertTrue(o.get("available_at"), o)
        self.assertGreater(seen, 0)


class A1bEmptyRowsAreGuarded(unittest.TestCase):
    """Code-review S3: ictShapes/wyckoffShapes on an empty window draw nothing and do not throw."""

    run_js = Engine.run_js

    def test_empty_rows_give_no_shapes(self):
        out = self.run_js("const cfg={compact:false,fmt:v=>String(v)};"
                          "console.log(JSON.stringify({i:T.ictShapes([],T.ictFromStructures([],{},[]),cfg),"
                          "w:T.wyckoffShapes([],{tr:null,events:[],phases:[]},cfg)}))")
        self.assertEqual(out, {"i": [], "w": []})


class A2bTierQualityNeverGuessesTheClock(unittest.TestCase):
    """Code-review I6 (CLAUDE.md section 20): no entry-tier clock -> UNKNOWN, never a verdict against the wall
    clock; and when the build wrote a snapshot the verdict comes from THAT copy, not the live file."""

    def _series(self, last_updated, n=40):
        return {"candles": synth(n, step_min=240), "last_updated": last_updated}

    def test_no_clock_is_unknown_never_fresh_or_stale(self):
        b = load("build-artifact.py")
        b.read_json = lambda path, default=None: self._series("2026-09-20T00:00:00Z")
        for clock in (None, ""):
            q = b.tier_quality("BTCUSDT", "4H", clock)
            self.assertEqual(q["state"], "UNKNOWN", q)
            self.assertIsNone(q["clock"])

    def test_the_verdict_is_read_from_the_snapshot_copy_not_the_live_file(self):
        b = load("build-artifact.py")
        read = []
        snap = os.path.join(tempfile.gettempdir(), "a2b-snap-test")
        snap_series = self._series("2026-09-25T00:00:00Z")            # fresh vs the clock below
        live_series = self._series("2026-09-01T00:00:00Z")            # would be stale if the live file were read

        def fake_read(path, default=None):
            read.append(path)
            return snap_series if os.path.dirname(path) == snap else live_series
        b.read_json = fake_read
        q = b.tier_quality("BTCUSDT", "4H", "2026-09-25T01:00:00Z", snap)
        self.assertEqual(q["state"], "FRESH", q)
        self.assertEqual(read, [os.path.join(snap, "ohlcv.BTCUSDT.4H.json")])
        read.clear()
        q2 = b.tier_quality("BTCUSDT", "4H", "2026-09-25T01:00:00Z")
        self.assertEqual(q2["state"], "STALE", q2)
        self.assertNotEqual(os.path.dirname(read[0]), snap)
