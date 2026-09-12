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
        cls.tmp = tempfile.mkdtemp(); cls.out = os.path.join(cls.tmp, "daytrade.html")
        b.build("daytrade", cls.out)
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


if __name__ == "__main__":
    unittest.main()
