"""ICT chart-fidelity audit 2026-10-04 -- regression tests for the eleven chart defects (one class per item).

The decision path (scripts/ict-scan.py analyze()/setup_candidate(), read by live_rules/backtest/htf_context) must
be UNCHANGED by these display fixes: `DecisionOutputsUnchanged` compares the current ict-scan.py against a frozen
copy of the pre-fix file (scripts/tests/fixtures/ict_scan_frozen_09fc901.py) on real repo candles, with only the
additive display keys stripped.

Knowledge cited: knowledge/ict/core-a.md §2.6-2.7, §2.17 (R11), §2.21-2.27 (R19, R23), R6, R25;
knowledge/ict/mentorship-2024.md §15.
"""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
CHART_JS = os.path.join(ROOT, "scripts", "chart.js")
MD = os.path.join(ROOT, "data", "live", "market-data")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


structures = _load(os.path.join(ROOT, "scripts", "structures.py"), "structures_dl")
ict = structures.ict_scan
frozen = _load(os.path.join(ROOT, "scripts", "tests", "fixtures", "ict_scan_frozen_09fc901.py"), "ict_scan_frozen")
PIV = structures.PIV
ADDITIVE_MSS_KEYS = ("dep_pivots", "disp_conf_i")


def _series(sym, tf):
    with open(os.path.join(MD, f"ohlcv.{sym}.{tf}.json"), encoding="utf-8") as f:
        d = json.load(f)
    return d["candles"], d.get("last_updated")


def _windows():
    """A few closed windows of tracked repo candles (data/live/market-data), several symbols/timeframes/offsets."""
    out = []
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        for tf in ("15m", "1H", "4H"):
            c, _ = _series(sym, tf)
            c = c[:-1]                      # the last bar of these files is still forming
            for off in (0, 120):
                w = c[len(c) - 200 - off:len(c) - off]
                if len(w) == 200:
                    out.append((sym, tf, off, w))
    return out


def _strip(a):
    """analyze()'s dict with the additive display keys removed from every MSS record (deep copy via JSON)."""
    a = json.loads(json.dumps(a, sort_keys=True, default=str))
    for key in ("mss", "mss_all"):
        for m in a.get(key) or []:
            for k in ADDITIVE_MSS_KEYS:
                m.pop(k, None)
    for key in ("last_mss", "last_displaced_mss"):
        if a.get(key):
            for k in ADDITIVE_MSS_KEYS:
                a[key].pop(k, None)
    return a


def _rows6(candles):
    return [[c["open"], c["high"], c["low"], c["close"], c.get("volume", 0), c["time"]] for c in candles]


def _bars(spec, n, t0="2026-09-01T00:00:00Z", step_h=1, base=(100.0, 101.0, 99.0, 100.0)):
    """n hourly candles of `base` (o,h,l,c), with `spec` {i: (o,h,l,c)} overrides."""
    t = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00"))
    out = []
    for i in range(n):
        o, h, l, c = spec.get(i, base)
        out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c, "volume": 1.0})
        t += datetime.timedelta(hours=step_h)
    return out


def _node(body):
    p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); {body}"], capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stderr[-800:])
    return json.loads(p.stdout)


def _node_file(payload, body):
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "in.json")
        with open(f, "w") as fh:
            json.dump(payload, fh)
        return _node(f"const d=JSON.parse(require('fs').readFileSync({json.dumps(f)},'utf8')); {body}")


# --------------------------------------------------------------------------------------- decision unchanged
class DecisionOutputsUnchanged(unittest.TestCase):
    """Items 2-4 add display-only fields. analyze() (minus the additive MSS keys), setup_candidate() and the
    htf_context bias read must equal the frozen pre-fix ict-scan.py on real repo candles."""

    def test_analyze_and_setup_candidate_match_the_frozen_copy(self):
        ws = _windows()
        self.assertGreaterEqual(len(ws), 12)
        compared = 0
        for sym, tf, off, w in ws:
            for opts in (None, {"fx_b2b_ce_fail": True}):
                new = ict.analyze(w, 4, tf=tf, methods=("ict",), opts=opts)
                old = frozen.analyze(w, 4, tf=tf, methods=("ict",), opts=opts)
                self.assertEqual(_strip(new), _strip(old), (sym, tf, off, opts))
                for lb in (12, 24):
                    self.assertEqual(json.dumps(ict.setup_candidate(new, w, lb, opts=opts), sort_keys=True, default=str),
                                     json.dumps(frozen.setup_candidate(old, w, lb, opts=opts), sort_keys=True, default=str),
                                     (sym, tf, off, opts, lb))
                hb = structures.htf_context.ict_bias
                self.assertEqual(hb({"prev_candle": new["prev_candle"], "last_displaced_mss": new["last_displaced_mss"]}),
                                 hb({"prev_candle": old["prev_candle"], "last_displaced_mss": old["last_displaced_mss"]}))
                compared += 1
        self.assertGreater(compared, 0)

    def test_display_lifecycle_does_not_mutate_the_analysis(self):
        _, _, _, w = _windows()[0]
        a = ict.analyze(w, 4, tf="15m", methods=("ict",))
        before = json.dumps(a, sort_keys=True, default=str)
        ict.display_lifecycle(w, a)
        structures.ict_structures(w, 4, "15m", analysis=a)
        self.assertEqual(json.dumps(a, sort_keys=True, default=str), before)


# ------------------------------------------------------------------------------------------ item 1: causal
class Item1ChartUsesTheCausalWindow(unittest.TestCase):
    """build-artifact.py feeds ict_json / wy_json_engine the decision path's causal window (ict-scan.py
    causal_window, now = the series' last_updated) -- never a forming bar."""

    @classmethod
    def setUpClass(cls):
        cls.BA = _load(os.path.join(ROOT, "scripts", "build-artifact.py"), "build_artifact_dl")

    def test_causal_rows_is_the_decision_paths_causal_window(self):
        for tf in ("15m", "1H", "4H"):
            c, upd = _series("BTCUSDT", tf)
            now = datetime.datetime.fromisoformat(upd.replace("Z", "+00:00"))
            got = self.BA.causal_rows(c, tf, upd)
            self.assertEqual(got, ict.causal_window(c, tf, now))
            self.assertEqual(len(got), len(c) - 1, "the repo snapshot's last bar is forming and must be dropped")

    def test_a_closed_last_bar_is_kept_and_unknown_availability_is_dropped(self):
        rows = _bars({}, 30)
        closed_at = "2026-09-02T06:00:00Z"   # after bar 29's close (bar 29 opens 05:00, 1H)
        self.assertEqual(len(self.BA.causal_rows(rows, "1H", closed_at)), 30)
        self.assertEqual(len(self.BA.causal_rows(rows, "1H", None)), 29)

    def test_a_forming_last_bar_produces_no_object(self):
        # bar 30 (forming) is a huge up candle: on the full rows it creates a bull FVG at bar 29 (needs bar 30)
        # and closes through every pool; on the causal window neither can exist.
        spec = {29: (100.0, 103.0, 99.5, 102.5), 30: (104.5, 120.0, 104.0, 119.0)}
        rows = _bars(spec, 31)
        forming_upd = "2026-09-02T06:30:00Z"   # bar 30 opened 06:00, closes 07:00 -> still forming
        crows = self.BA.causal_rows(rows, "1H", forming_upd)
        self.assertEqual(len(crows), 30)
        full = self.BA.ict_json(rows, "1H")["structures"]
        causal = self.BA.ict_json(crows, "1H")["structures"]
        self.assertTrue([s for s in full if s["kind"] == "fvg" and s["i"] == 29], "fixture must create the forming FVG")
        self.assertFalse([s for s in causal if s["kind"] == "fvg" and s["i"] >= 29])
        last_avail = ict.N.available_time(crows[-1], "1H").isoformat().replace("+00:00", "Z")
        for s in causal:
            for key in ("available_at", "invalidated_at", "touched_at", "ce_fail_at", "inversion_at", "broken_at"):
                if s.get(key):
                    self.assertLessEqual(s[key], last_avail, (s["kind"], key))

    def test_every_tier_is_windowed_before_both_engines(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertIn("wy_json_engine(crows,", src)
        self.assertIn("ict_json(crows,", src)
        self.assertIn("wy_json_engine(ctrows,", src)
        self.assertIn("ict_json(ctrows,", src)
        self.assertFalse("= wy_json_engine(rows," in src or "= ict_json(rows," in src)
        self.assertFalse("ict_json(trows," in src or "wy_json_engine(trows," in src)


# --------------------------------------------------------------------------------------------- item 2: MSS
class Item2MssAvailableAtIncludesItsPivots(unittest.TestCase):

    def test_available_at_is_the_latest_dependency(self):
        for sym, tf, off, w in _windows():
            env = structures.ict_structures(w, 4, tf, methods=("ict",))
            for s in env["structures"]:
                if s["kind"] != "mss":
                    continue
                conf = max([s["i"], s["disp_conf_i"]] + [q + PIV for q in s["dep_pivots"]])
                self.assertEqual(s["available_at"], ict.N.available_time(w[conf], tf).isoformat().replace("+00:00", "Z"))
                self.assertIn(max(s["dep_pivots"]), env["analysis"]["pivots_high"] + env["analysis"]["pivots_low"])

    def test_prefix_redetection(self):
        """For every MSS: re-running the engine on candles[:k], k = index(available_at)+1, detects it (or -- when
        the window-wide median range flips an EARLIER record's displacement -- an earlier displaced close through
        the SAME swing, see note); on candles[:k-1] its MSS bar or one of its dependencies does not exist yet.

        Note: analyze()'s displacement test uses the WHOLE window's median range (`med`), so a prefix can score an
        earlier same-swing close as displaced and stop scanning. That is a pre-existing window-relativity of the
        decision path, untouched here (out of scope: it is read by setup_candidate/bias)."""
        checked = exact = 0
        for sym, tf, off, w in _windows():
            a = ict.analyze(w, 4, tf=tf, methods=("ict",))
            full = {(m["type"], m["i"], m["level"]): m for m in a["mss_all"]}
            for m in a["mss_all"]:
                k = max([m["i"], m["disp_conf_i"]] + [q + PIV for q in m["dep_pivots"]]) + 1
                b = ict.analyze(w[:k], 4, tf=tf, methods=("ict",))
                pivs = set(b["pivots_high"]) | set(b["pivots_low"])
                self.assertTrue(set(m["dep_pivots"]) <= pivs, (sym, tf, off, m["i"]))
                hit = [x for x in b["mss_all"] if (x["type"], x["i"], x["level"]) == (m["type"], m["i"], m["level"])]
                if hit:
                    exact += 1
                else:
                    alt = [x for x in b["mss_all"] if x["type"] == m["type"] and x["level"] == m["level"]
                           and x["i"] < m["i"] and x["disp"]
                           and not full.get((x["type"], x["i"], x["level"]), {}).get("disp", True)]
                    self.assertTrue(alt, (sym, tf, off, m["i"], k))
                # fewer bars: the MSS bar itself, a dependent pivot, or the displacement confirmation is missing
                if k - 1 > 0:
                    c = ict.analyze(w[:k - 1], 4, tf=tf, methods=("ict",))
                    pivs_short = set(c["pivots_high"]) | set(c["pivots_low"])
                    missing = (m["i"] >= k - 1 or m["disp_conf_i"] >= k - 1
                               or not set(m["dep_pivots"]) <= pivs_short)
                    self.assertTrue(missing, (sym, tf, off, m["i"], k))
                checked += 1
        self.assertGreater(checked, 20)
        self.assertGreater(exact / checked, 0.9)

    def test_a_late_pivot_delays_availability(self):
        """The defect is real on repo candles: some MSS bars come fewer than PIV bars after a pivot they depend
        on (or rest on an FVG needing the next bar). Each such MSS must be available strictly AFTER its own bar --
        before this fix every one of them claimed availability at its own bar."""
        late = 0
        for sym, tf, off, w in _windows():
            env = structures.ict_structures(w, 4, tf, methods=("ict",))
            for s in env["structures"]:
                if s["kind"] == "mss" and (max(s["dep_pivots"]) + PIV > s["i"] or s["disp_conf_i"] > s["i"]):
                    own = ict.N.available_time(w[s["i"]], tf).isoformat().replace("+00:00", "Z")
                    self.assertGreater(s["available_at"], own, (sym, tf, off, s["i"]))
                    late += 1
        self.assertGreater(late, 0, "fixture windows must exercise at least one late-confirmed MSS")


# ------------------------------------------------------------------------------------------- item 3: pools
POOL_SPEC = {5: (100.0, 110.0, 99.0, 100.0), 12: (100.0, 111.0, 99.0, 105.0), 20: (104.0, 113.0, 103.0, 112.0)}


class Item3SweptPoolsEndAtABodyClose(unittest.TestCase):

    def setUp(self):
        self.rows = _bars(POOL_SPEC, 30)
        self.env = structures.ict_structures(self.rows, 4, "1H", methods=("ict",))
        self.pool = next(s for s in self.env["structures"] if s["kind"] == "pool" and s["level"] == 110.0)

    def test_broken_at_is_the_first_later_body_close(self):
        raw = next(p for p in self.env["analysis"]["pools"] if p["level"] == 110.0)
        self.assertEqual((raw["state"], raw["swept"]), ("swept", 12), "decision fields: the sweep, unchanged")
        self.assertEqual(self.pool["broken_i"], 20)
        want = ict.N.available_time(self.rows[20], "1H").isoformat().replace("+00:00", "Z")
        self.assertEqual((self.pool["broken_at"], self.pool["invalidated_at"]), (want, want))

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_chart_draws_swept_muted_and_ends_the_line(self):
        rows = _rows6(self.rows)
        cut15 = ict.N.available_time(self.rows[15], "1H").isoformat().replace("+00:00", "Z")
        out = _node_file({"rows": rows, "s": self.env["structures"], "cut": cut15},
                         "const full=T.ictFromStructures(d.s,{},d.rows,{tfMin:60});"
                         "const r15=d.rows.slice(0,16), at=T.ictFromStructures(d.s,{},r15,{tfMin:60,cutIso:d.cut});"
                         "const p=x=>x.pools.find(q=>q.level===110);"
                         "const sh=T.ictShapes(r15,at,{compact:false,fmt:v=>String(v)});"
                         "const seg=sh.find(s=>s.kind==='hseg'&&s.price===110), lab=sh.find(s=>s.kind==='label'&&s.price===110);"
                         "console.log(JSON.stringify({fullTo:p(full).to, atTo:p(at).to, swept:p(at).swept, stroke:seg.stroke, label:lab.text}))")
        self.assertEqual(out["fullTo"], 20.5, "the swept line ends at the breaking close")
        self.assertIsNone(out["atTo"], "before the break (replay cursor at bar 15) the swept level stays open")
        self.assertEqual(out["swept"], 12)
        self.assertEqual(out["stroke"], "muted")
        self.assertIn("chart.pool.swept", out["label"])
        self.assertIn("chart.pool.old_high", out["label"], "item 10: labelled from the engine's pool type")


# -------------------------------------------------------------------------------------------- item 4: FVGs
FVG_SPEC = {10: (100.5, 104.0, 100.4, 103.8), 11: (103.8, 105.0, 103.0, 104.5),
            12: (104.0, 105.0, 103.5, 104.0), 13: (104.0, 105.0, 103.5, 104.0), 14: (104.0, 105.0, 103.5, 104.0),
            15: (104.0, 104.5, 102.8, 104.0), 16: (104.0, 105.0, 103.5, 104.0), 17: (104.0, 105.0, 103.5, 104.0),
            18: (103.5, 103.6, 101.5, 101.8), 19: (102.0, 102.5, 101.2, 101.6), 20: (102.0, 102.5, 101.2, 101.6),
            21: (102.0, 102.5, 101.2, 101.6), 22: (101.5, 101.7, 100.0, 100.5)}


class Item4FvgLifecycle(unittest.TestCase):

    def setUp(self):
        self.rows = _bars(FVG_SPEC, 30, base=(100.5, 101.0, 100.0, 100.5))
        self.env = structures.ict_structures(self.rows, 4, "1H", methods=("ict",))
        self.f = next(s for s in self.env["structures"] if s["kind"] == "fvg" and s["i"] == 10)

    def test_states_and_their_times(self):
        f = self.f
        self.assertEqual((f["lo"], f["hi"], f["ce"]), (101.0, 103.0, 102.0))
        self.assertEqual((f["touch_i"], f["ce_fail_i"], f["inversion_i"]), (15, 18, 22))
        self.assertTrue(f["mitigated"]); self.assertEqual(f["end"], 15, "decision fields copied verbatim")
        av = lambda i: ict.N.available_time(self.rows[i], "1H").isoformat().replace("+00:00", "Z")
        self.assertEqual((f["touched_at"], f["ce_fail_at"], f["inversion_at"]), (av(15), av(18), av(22)))
        self.assertEqual(f["invalidated_at"], av(22), "the box ends at the inversion, never at the first touch")
        self.assertGreaterEqual(f["touched_at"], f["available_at"])

    def test_same_walk_as_the_fx_b2b_decision_variant(self):
        a = ict.analyze(self.rows, 4, tf="1H", methods=("ict",), opts={"fx_b2b_ce_fail": True})
        raw = next(x for x in a["fvgs_all"] if x["i"] == 10)
        self.assertEqual((raw["ce_failed_at"], raw["inverted_at"]), (self.f["ce_fail_i"], self.f["inversion_i"]))
        self.assertNotIn("ce_failed_at", next(x for x in self.env["analysis"]["fvgs_all"] if x["i"] == 10),
                         "v1 decision default stays without the fx_b2b fields")

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_chart_keeps_the_box_through_the_touch_and_draws_the_inversion(self):
        out = _node_file({"rows": _rows6(self.rows), "s": self.env["structures"]},
                         "const ict=T.ictFromStructures(d.s,{},d.rows,{tfMin:60});"
                         "const sh=T.ictShapes(d.rows,ict,{compact:false,fmt:v=>String(v)});"
                         "const box=sh.filter(s=>s.kind==='rect'&&s.p1===103&&s.p2===101);"
                         "const ce=sh.find(s=>s.kind==='hseg'&&s.price===102);"
                         "const marks=sh.filter(s=>s.kind==='mark'&&(s.price===103||s.price===102)).map(s=>[s.i,s.glyph]);"
                         "console.log(JSON.stringify({boxes:box.map(b=>[b.i1,b.i2,b.fill,b.label||null,b.dash||null]),ce:[ce.i1,ce.i2],marks}))")
        boxes = out["boxes"]
        self.assertIn([9.5, 22.5, "up", None, None], boxes, "the box runs from the gap to the inversion bar")
        self.assertIn([22.5, 29.5, "down", "IFVG", [4, 3]], boxes, "the inverted gap: opposite colour, own style")
        self.assertEqual(out["ce"], [9.5, 22.5], "the CE line is kept while the box lives")
        self.assertIn([15, "dot"], out["marks"]); self.assertIn([18, "x"], out["marks"])


# ----------------------------------------------------------------------------------- items 5-6: dealing range
class Items5and6DealingRangeStartsWhereItExisted(unittest.TestCase):

    def test_from_i_is_the_later_edge(self):
        for sym, tf, off, w in _windows()[:6]:
            env = structures.ict_structures(w, 4, tf, methods=("ict",))
            dr, a = env["dealing_range"], env["analysis"]
            self.assertTrue(0 <= dr["from_i"] <= len(w) - 1)
            if dr["source"] == "pools":
                edge = [min(p.get("to", p["from"]) + PIV, len(w) - 1) for p in a["pools"]
                        if p["swept"] < 0 and p["state"] != "closed_through" and p["level"] in (a["hi"], a["lo"])]
                self.assertEqual(dr["from_i"], max(edge))

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_shading_eq_and_pane_start_at_from_i(self):
        rows = _rows6(_bars({}, 40))
        dr = {"hi": 101.0, "lo": 99.0, "eq": 100.0, "source": "pools", "from_i": 25,
              "available_at": "2026-09-02T16:00:00Z"}
        s = [{"kind": "pool", "pool_kind": "BSL", "level": 101.0, "from": 20, "to": 22, "type": "old",
              "available_at": "2026-09-01T23:00:00Z", "invalidated_at": None}]
        out = _node(f"const rows={json.dumps(rows)}, dr={json.dumps(dr)}, s={json.dumps(s)};"
                    "const ict=T.ictFromStructures(s,dr,rows,{tfMin:60});"
                    "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                    "const pd=sh.filter(x=>x.kind==='rect'&&(x.fill==='down'||x.fill==='up')&&x.p1!=null).map(x=>x.i1);"
                    "const eq=sh.find(x=>x.kind==='hseg'&&x.price===100);"
                    "const ser=T.rangePctSeries(rows,ict);"
                    "console.log(JSON.stringify({pd, eq:eq.i1, first:ser.findIndex(p=>'value' in p), drFrom:ict.drFrom}))")
        self.assertEqual(out["drFrom"], 25)
        self.assertEqual(out["pd"], [24.5, 24.5])
        self.assertEqual(out["eq"], 24.5)
        self.assertEqual(out["first"], 25, "item 5: the range-% pane starts where the range existed")


# ------------------------------------------------------------------------------------------- item 7: grab
@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class Item7GrabIsNotAnMss(unittest.TestCase):

    def test_grab_has_its_own_neutral_style_and_legend(self):
        rows = _rows6(_bars({}, 30))
        s = [{"kind": "mss", "type": "bull", "i": 20, "level": 100.5, "disp": False, "available_at": "2026-09-01T21:00:00Z"},
             {"kind": "mss", "type": "bull", "i": 25, "level": 100.5, "disp": True, "available_at": "2026-09-02T02:00:00Z"}]
        out = _node(f"const rows={json.dumps(rows)}, s={json.dumps(s)};"
                    "const ict=T.ictFromStructures(s,{},rows,{tfMin:60});"
                    "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                    "const at=i=>sh.filter(x=>x.i===i&&(x.kind==='vseg'||x.kind==='label')).map(x=>[x.kind,x.stroke||x.color,x.text||null]);"
                    "console.log(JSON.stringify({grab:at(20), mss:at(25), legend:T.legendHtml('ict',{kz:false,market:'crypto'},{})}))")
        self.assertEqual(out["grab"], [["vseg", "muted", None], ["label", "muted", "chart.grab.no_displacement"]])
        self.assertEqual(out["mss"], [["vseg", "up", None], ["label", "up", "MSS↑"]])
        self.assertIn("legend.grab", out["legend"])
        i18n = json.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))
        msgs = i18n.get("messages", i18n)
        self.assertNotIn("displacement missing", msgs["legend.mss"]["en"])
        self.assertIn("liquidity grab", msgs["legend.grab"]["en"])


# -------------------------------------------------------------------------------------- items 8-10: legend
class Items8to10Legend(unittest.TestCase):

    def setUp(self):
        i18n = json.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))
        self.msgs = i18n.get("messages", i18n)

    def test_london_window_is_called_a_project_session_window(self):
        self.assertIn("session window (project", self.msgs["legend.killzone"]["en"])
        self.assertNotIn("killzone LDN", self.msgs["legend.killzone"]["en"])

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_killzone_legend_follows_d_kz_and_the_asset_weights(self):
        out = _node("console.log(JSON.stringify([T.legendHtml('ict',{kz:true,market:'crypto'},{}),"
                    "T.legendHtml('ict',{kz:false,market:'crypto'},{}),T.legendHtml('ict',{kz:true,market:'indices'},{})]))")
        self.assertIn("legend.killzone<", out[0])
        self.assertIn("legend.killzone_off", out[1])
        self.assertIn("legend.killzone_off", out[2], "an asset class with all-'none' weights draws no band")

    def test_build_artifact_passes_d_kz(self):
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertIn('kz=any(t["kz"] for t in tiers_js)', src)

    def test_pool_legend_promises_only_drawn_types(self):
        self.assertNotIn("ERL", self.msgs["legend.liquidity"]["en"])
        src = open(CHART_JS, encoding="utf-8").read()
        for dead in ("'ERL-high'", "'OLD-H'", "'OLD-L'", "'ERL-low'"):
            self.assertNotIn(dead, src)


# ---------------------------------------------------------------------------------------- item 11: audit note
class Item11AuditCorrection(unittest.TestCase):

    def test_cisd_correction_note_is_appended(self):
        doc = open(os.path.join(ROOT, "docs", "audits", "2026-09-29-a2-chart-from-engine.md"), encoding="utf-8").read()
        tail = doc[doc.rfind("Correction (2026-10-04)"):]
        self.assertIn("Correction (2026-10-04)", doc)
        self.assertIn("CISD", tail)
        self.assertIn("ict-scan.py", tail)


if __name__ == "__main__":
    unittest.main()
