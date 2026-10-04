"""Wyckoff chart-fidelity regressions (docs/audits/2026-10-04-wyckoff-chart-fidelity.md, findings 1-18).

Each class names the finding it pins. Real repo candles (data/history, data/live/market-data) are used wherever a
property must hold "on the data the page actually draws"; node runs scripts/chart.js's pure builders.

The decision path is NOT exercised for change here on purpose: every fix below is either chart-only
(structures.py envelope, build-artifact.py labels, chart.js) or, for W8, a wyckoff_rules.py PARAMS key that is
False by default and set only by structures.ENVELOPE_PARAMS -- see W8ChochInsideBox.
"""
import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N  # noqa: E402
import wyckoff_rules as W  # noqa: E402

CHART_JS = os.path.join(ROOT, "scripts", "chart.js")


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


structures = _load("structures.py", "structures_fid")
cn = _load("check-narrative.py", "check_narrative_fid")
ba = cn._ba   # check-narrative.py already loaded build-artifact.py; reuse it rather than paying for a second load


def _iso(c, tf):
    return N.available_time(c, tf).isoformat().replace("+00:00", "Z")


def _arrays(rows):
    return ([r["open"] for r in rows], [r["high"] for r in rows], [r["low"] for r in rows],
            [r["close"] for r in rows], [r.get("volume", 0) for r in rows])


def _det(rows, side):
    """The arrays the detector actually reads (detect_distributions runs on -L/-H)."""
    O, H, L, C, V = _arrays(rows)
    if side == "short":
        return [-x for x in O], [-x for x in L], [-x for x in H], [-x for x in C]
    return O, H, L, C


def _mirror(rows):
    return [dict(r, open=-r["open"], high=-r["low"], low=-r["high"], close=-r["close"]) for r in rows]


# A spread of repo series: crypto + CFD, several timeframes, history + the live market-data the page draws.
SERIES = [("history", s, tf) for s, tf in (("AUS200", "4H"), ("BTCUSDT", "1H"), ("ETHUSDT", "4H"), ("XAUUSD", "4H"),
                                            ("XAUUSD", "15m"), ("TAOUSDT", "4H"), ("US30", "15m"), ("VIRTUALUSDT", "1H"),
                                            ("XAGUSD", "1W"), ("USTEC", "4H"), ("SUIUSDT", "30m"), ("TAOUSDT", "2H"))]


def _series(src, sym, tf, n):
    path = (os.path.join(ROOT, "data", "history", f"ohlcv.{sym}.{tf}.json") if src == "history"
            else os.path.join(ROOT, "data", "live", "market-data", f"ohlcv.{sym}.{tf}.json"))
    if not os.path.exists(path):
        return None
    return json.load(open(path, encoding="utf-8"))["candles"][-n:]


def _all_series(n=360):
    out = []
    for src, sym, tf in SERIES:
        rows = _series(src, sym, tf, n)
        if rows:
            out.append((f"{sym} {tf}", sym, tf, rows))
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "live", "market-data", "ohlcv.*.json"))):
        sym, tf = os.path.basename(path).split(".")[1:3]
        rows = json.load(open(path, encoding="utf-8"))["candles"][-n:]
        if len(rows) > 60:
            out.append((f"live {sym} {tf}", sym, tf, rows))
    return out


_ENV_CACHE = {}


def _envs(P, n=360):
    """(name, sym, tf, side, rows, env) for every series x side, cached per (P, n) -- the PIT scan is not free."""
    key = (id(P), n)
    if key not in _ENV_CACHE:
        got = []
        for name, sym, tf, rows in _all_series(n):
            O, H, L, C, V = _arrays(rows)
            for side in ("long", "short"):
                got.append((name, sym, tf, side, rows,
                            structures.wyckoff_structures(O, H, L, C, V, rows, tf, P=P, side=side)))
        _ENV_CACHE[key] = got
    return _ENV_CACHE[key]


class W8ChochInsideBox(unittest.TestCase):
    """Finding 1 (WA p68-69): the confirming CHoCH must lie inside (or at the edge of) the SC->AR box; the ran-away
    guard runs before the LPS[C]/SOS test."""

    def test_flag_is_off_for_the_decision_path_and_on_for_the_chart(self):
        self.assertIs(W.PARAMS["fx_w8_choch_in_box"], False, "v1 decision semantics: W8 is an owner decision")
        self.assertTrue(structures.ENVELOPE_PARAMS["fx_w8_choch_in_box"])
        for f in ("backtest-methods.py", "live_rules.py", "strategy-runner.py", "fvg_demo.py"):
            p = os.path.join(ROOT, "scripts", f)
            if os.path.exists(p):
                self.assertNotIn("fx_w8", open(p, encoding="utf-8").read(), f"{f} must not set W8 silently")
                self.assertNotIn("ENVELOPE_PARAMS", open(p, encoding="utf-8").read(), f)

    def test_every_chart_record_has_its_choch_inside_the_box(self):
        tol = W.PARAMS["choch_box_tol_tr"]
        checked = outside_v1 = 0
        for name, sym, tf, rows in _all_series(600):
            O, H, L, C, V = _arrays(rows)
            for side in ("long", "short"):
                Hd = _det(rows, side)[1]
                for P, chart in ((structures.ENVELOPE_PARAMS, True), (W.PARAMS, False)):
                    for r in structures.wyckoff_records(O, H, L, C, V, P=P, side=side):
                        lo, hi = (r["tr_lo"], r["tr_hi"]) if side == "long" else (-r["tr_hi"], -r["tr_lo"])
                        inside = Hd[r["choch"]] <= hi + tol * (hi - lo) + 1e-12
                        if chart:
                            checked += 1
                            self.assertTrue(inside, f"{name} {side}: CHoCH outside the SC-AR box")
                        elif not inside:
                            outside_v1 += 1
        self.assertGreater(checked, 0, "no chart record at all: the box rule is unpinned")
        self.assertGreater(outside_v1, 0, "v1 never produced an outside-box CHoCH on this data: the fixture pins nothing")

    def test_ran_away_guard_runs_before_the_phase_c_and_sos_tests(self):
        """With W8 the walk breaks on H[b] > ceiling + TR before testing b as an SOS, so no bar from the walk start
        up to the LPS[C]-path SOS bar (or up to the bar before a Spring) can sit beyond the final ceiling + TR."""
        checked = 0
        for name, sym, tf, rows in _all_series(600):
            O, H, L, C, V = _arrays(rows)
            for side in ("long", "short"):
                Hd = _det(rows, side)[1]
                for r in structures.wyckoff_records(O, H, L, C, V, P=structures.ENVELOPE_PARAMS, side=side):
                    lo, hi = (r["tr_lo"], r["tr_hi"]) if side == "long" else (-r["tr_hi"], -r["tr_lo"])
                    ceiling = r["ceiling"] if side == "long" else -r["ceiling"]
                    start = max(r["choch"], r["st"]) + 1
                    end = r["sos_bar"] if r["path"] == "lps_c" else r["spring"] - 1
                    if end < start:
                        continue
                    checked += 1
                    self.assertLessEqual(max(Hd[start:end + 1]), ceiling + (hi - lo) + 1e-12, f"{name} {side}")
        self.assertGreater(checked, 0)


class PointInTimePrefixRedetection(unittest.TestCase):
    """Findings 3/4 (CLAUDE.md §8): for every object the page ships, re-running wyckoff_structures() on
    candles[:k+1] where k is the object's available_at bar emits it in the SAME state, and the run ending one bar
    earlier does not. Checked for the chart config (ENVELOPE_PARAMS) and the v1 config, both sides."""

    @staticmethod
    def _shipped(tr):
        out = {("tr",): ((tr["tr_lo"], tr["tr_hi"], tr["formed_at"]), tr["available_at"])}
        if tr["to"]:
            out[("tr_end",)] = ((tr["to"], tr["end_reason"]), tr["to_available_at"])
        if tr["invalidated"]:
            inv = tr["invalidated"]
            out[("inval",)] = ((inv["formed_at"], inv["reason"]), inv["available_at"])
        for e in tr["events"]:
            st = tuple((k, e.get(k)) for k in ("shakeout", "vol_type", "confirmed", "conf_bar"))
            out[("ev", e["kind"], e["formed_at"])] = (st, e["available_at"])
        for p in tr["phases"]:
            out[("ph", p["label"])] = ((p["from"],), p["available_at"])
            out[("ph_full", p["label"])] = ((p["from"], p["to"], p["status"], tuple(p["reasons"])), p["state_available_at"])
        return out

    def _prefix(self, cache, rows, tf, P, side, m):
        if m not in cache:
            O, H, L, C, V = _arrays(rows[:m])
            env = structures.wyckoff_structures(O, H, L, C, V, rows[:m], tf, P=P, side=side, pit=False)
            cache[m] = {(t["sc"], t["ar"], t["st"], t["choch"]): {k: v[0] for k, v in self._shipped(t).items()}
                        for t in env["structures"]}
        return cache[m]

    def test_every_shipped_object_appears_exactly_at_its_available_at(self):
        objects = springs_after_reclaim = 0
        for P in (structures.ENVELOPE_PARAMS, W.PARAMS):
            for name, sym, tf, side, rows, env in _envs(P, 300):
                bar_of = {_iso(c, tf): i for i, c in enumerate(rows)}
                cache = {}
                for tr in env["structures"]:
                    key = (tr["sc"], tr["ar"], tr["st"], tr["choch"])
                    for oid, (state, avail) in self._shipped(tr).items():
                        k = bar_of[avail]
                        now = self._prefix(cache, rows, tf, P, side, k + 1).get(key, {})
                        self.assertEqual(now.get(oid), state, f"{name} {side} {oid}: not emitted at its available_at")
                        if k > 0:
                            before = self._prefix(cache, rows, tf, P, side, k).get(key, {})
                            self.assertNotEqual(before.get(oid), state, f"{name} {side} {oid}: emitted a bar earlier")
                        objects += 1
                    for e in tr["events"]:
                        if e["kind"] == "spring" and tr["reclaim"] is not None:
                            # Finding 3: the Spring/UT type is decided at the reclaim at the earliest.
                            self.assertGreaterEqual(e["available_at"], _iso(rows[tr["reclaim"]], tf))
                            springs_after_reclaim += 1
                    # Finding 4: the range is not knowable before the record is emittable, nor before the CHoCH
                    # pivot is confirmed.
                    self.assertGreaterEqual(tr["available_at"],
                                            _iso(rows[min(tr["choch"] + W.PARAMS["pivot"], len(rows) - 1)], tf))
        self.assertGreater(objects, 50, "too few shipped objects: the PIT test would prove little")
        self.assertGreater(springs_after_reclaim, 0, "no reclaimed Spring/UT in the data: finding 3 unpinned")


class EventLabels(unittest.TestCase):
    """Findings 2, 6, 8, 18: labels and flag anchors."""

    ROWS = [{"time": f"2026-09-01T00:{i:02d}:00Z", "open": 10.0, "high": 12.0, "low": 8.0, "close": 11.0} for i in range(5)]

    def lab(self, e, side, tick=False):
        return ba._wy_event_label(dict({"i": 1}, **e), side, self.ROWS, "int", tick)

    def test_shakeout_is_labelled_shakeout_not_spring(self):
        self.assertTrue(self.lab({"kind": "spring", "shakeout": True, "vol_type": 3}, "long")[0].startswith("Shakeout "))
        self.assertTrue(self.lab({"kind": "spring", "shakeout": True, "vol_type": 2}, "short")[0].startswith("UTAD (Shakeout) "))

    def test_spring_carries_its_volume_type_and_tick_marker(self):
        self.assertTrue(self.lab({"kind": "spring", "shakeout": False, "vol_type": 2}, "long")[0].startswith("Spring T2 "))
        self.assertTrue(self.lab({"kind": "spring", "shakeout": False, "vol_type": 1}, "long", tick=True)[0].startswith("Spring T1 (tick) "))
        self.assertTrue(self.lab({"kind": "spring", "shakeout": False, "vol_type": None}, "long")[0].startswith("Spring "))

    def test_distribution_vocabulary(self):
        self.assertTrue(self.lab({"kind": "bu", "confirmed": True}, "short")[0].startswith("LPSY "))
        self.assertTrue(self.lab({"kind": "spring", "shakeout": False, "vol_type": 2}, "short")[0].startswith("UTAD T2 "))
        self.assertTrue(self.lab({"kind": "sos_bar"}, "short")[0].startswith("SOW "))
        self.assertTrue(self.lab({"kind": "sc"}, "short")[0].startswith("BC "))
        self.assertTrue(self.lab({"kind": "lps_c", "confirmed": True}, "short")[0].startswith("LPSY[C] "))
        self.assertTrue(self.lab({"kind": "bu", "confirmed": True}, "long")[0].startswith("BU "))
        self.assertTrue(self.lab({"kind": "lps_c", "confirmed": True}, "long")[0].startswith("LPS[C] "))

    def test_anchor_sides(self):
        self.assertEqual(self.lab({"kind": "st"}, "short"), ("ST 12", True), "distribution ST retests the BC high (WA p103)")
        self.assertEqual(self.lab({"kind": "st"}, "long"), ("ST 8", False))
        self.assertTrue(self.lab({"kind": "choch"}, "long")[1], "the accumulation CHoCH bar is a swing high")
        self.assertFalse(self.lab({"kind": "choch"}, "short")[1])

    def test_unconfirmed_label_ends_with_question_mark(self):
        label = self.lab({"kind": "bu", "confirmed": False}, "long")[0]
        self.assertTrue(label.endswith("?"), label)
        self.assertFalse(cn._label_confirmed(label))


class EngineObjectsOnData(unittest.TestCase):
    """Findings 5, 9, 10 on real data (chart config)."""

    def test_invalidation_is_emitted_and_means_what_the_books_say(self):
        seen = 0
        for P in (structures.ENVELOPE_PARAMS, W.PARAMS):
            for name, sym, tf, side, rows, env in _envs(P, 360):
                Cd = _det(rows, side)[3]
                for tr in env["structures"]:
                    inv = tr["invalidated"]
                    if not inv:
                        continue
                    seen += 1
                    self.assertEqual(tr["path"], "spring", "the LPS[C] path has no book invalidation rule")
                    self.assertIn(inv["reason"], ("abandon", "close_beyond_spring_low"))
                    self.assertGreaterEqual(inv["available_at"], tr["available_at"])
                    self.assertGreaterEqual(inv["available_at"], _iso(rows[inv["i"]], tf))
                    self.assertEqual(tr["invalidated_at"], inv["available_at"])
                    if inv["reason"] == "abandon":
                        self.assertTrue(tr["abandon"])
                    else:
                        low = tr["spring_low"] if side == "long" else -tr["spring_low"]
                        self.assertLess(Cd[inv["i"]], low, f"{name} {side}")
                        self.assertGreater(inv["i"], tr["reclaim"] if tr["reclaim"] is not None else tr["spring"])
        self.assertGreater(seen, 0, "no invalidated read in the data: finding 5 unpinned")

    def test_lps_c_path_has_a_phase_c_and_an_lps_c_event(self):
        seen = 0
        for P in (structures.ENVELOPE_PARAMS, W.PARAMS):
            for name, sym, tf, side, rows, env in _envs(P, 360):
                for tr in env["structures"]:
                    if tr["path"] != "lps_c":
                        continue
                    seen += 1
                    labels = [p["label"] for p in tr["phases"]]
                    self.assertEqual(labels[:4], ["A", "B", "C", "D"], f"{name} {side}: {labels}")
                    ev = next(e for e in tr["events"] if e["kind"] == "lps_c")
                    self.assertLess(tr["st"], ev["i"])
                    self.assertLess(ev["i"], tr["sos_bar"])
                    c = next(p for p in tr["phases"] if p["label"] == "C")
                    self.assertEqual(c["from"], ev["formed_at"])
                    self.assertEqual(c["to"], rows[tr["sos_bar"]]["time"])
        self.assertGreater(seen, 0)

    def test_phase_e_starts_beyond_the_sos_leg_after_the_bu_and_the_range_ends(self):
        e_seen = ended = 0
        for P in (structures.ENVELOPE_PARAMS, W.PARAMS):
            for name, sym, tf, side, rows, env in _envs(P, 360):
                Hd, Cd = _det(rows, side)[1], _det(rows, side)[3]
                times = [r["time"] for r in rows]
                for tr in env["structures"]:
                    e = next((p for p in tr["phases"] if p["label"] == "E"), None)
                    d = next((p for p in tr["phases"] if p["label"] == "D"), None)
                    if e:
                        e_seen += 1
                        q, bu = times.index(e["from"]), tr["bu"]["bar"]
                        self.assertGreater(q, bu, "Phase E starts AFTER the BU (WA p85)")
                        self.assertGreater(Cd[q], max(Hd[tr["sos_bar"]:bu]), "first close beyond the SOS leg")
                        self.assertEqual(d["to"], e["from"])
                        bu_ev = next(x for x in tr["events"] if x["kind"] == "bu")
                        self.assertLess(bu_ev["formed_at"], e["from"], "BU is a Phase-D event")
                    if tr["to"]:
                        ended += 1
                        self.assertIn(tr["end_reason"], ("phase_e", "invalidated", "expired"))
                        if tr["end_reason"] == "phase_e":
                            self.assertEqual(tr["to"], e["from"])
                        if tr["end_reason"] == "expired":
                            last = tr["phases"][-1]
                            self.assertIn("expired", last["reasons"])
                            self.assertEqual(last["to"], tr["to"])
                        if tr["end_reason"] == "invalidated" and "invalidated" in tr["phases"][-1]["reasons"]:
                            self.assertEqual(tr["phases"][-1]["to"], tr["invalidated"]["formed_at"],
                                             "an invalidated open phase stops at the invalidation (ADR 0004)")
                    for p in tr["phases"]:
                        if "expired" in p["reasons"]:
                            self.assertIsNotNone(p["to"])
                            self.assertEqual(p["status"], "hypothesis")
        self.assertGreater(ended, 0)
        self.assertGreater(e_seen, 0, "no Phase E in the data: finding 10 unpinned")


class NarrativeContractOnEngineOutput(unittest.TestCase):
    """Finding 14: the engine labels pass check-narrative.py's phase_grammar and confirmation_grammar (and its
    tick_volume_checks) -- the same contract the model's narrative is held to. The checker's SOS/pullback proxies
    are written for the accumulation direction, so a distribution read is checked on the price-mirrored candles
    (WA p101: the schematics are mirror images), labelled in accumulation vocabulary."""

    @staticmethod
    def _narrative(w):
        return {"phases": [{"label": p["label"], "from": p["from"], "to": p["to"], "status": p["status"]} for p in w["phases"]],
                "events": [{"time": e["time"], "label": e["label"]} for e in w["events"]],
                "trading_range": {"from": w["tr"]["from"], "high": w["tr"]["high"], "low": w["tr"]["low"]},
                "phase": w["phase"]}

    def test_engine_output_passes_the_narrative_grammar(self):
        reads = 0
        bad = []
        series = [(name, sym, tf, rows) for name, sym, tf, rows in _all_series(480)]
        for path in sorted(glob.glob(os.path.join(ROOT, "data", "history", "ohlcv.*.json"))):
            sym, tf = os.path.basename(path).split(".")[1:3]
            series.append((f"history {sym} {tf}", sym, tf, json.load(open(path, encoding="utf-8"))["candles"][-480:]))
        for name, sym, tf, rows in series:
            for side in ("long", "short"):
                rr = rows if side == "long" else _mirror(rows)
                w = ba.wy_ship(rr, tf, sym, "int", "long")
                if not w:
                    continue
                reads += 1
                wy = self._narrative(w)
                tag = f"{name} {side}"
                cn.phase_grammar(tag, wy, bad.append)
                cn.confirmation_grammar(tag, wy, rr, rr[-1]["time"], bad.append)
                cn.tick_volume_checks(tag, {"text_html": " · ".join(e["label"] for e in w["events"])}, {}, True, bad.append)
        self.assertEqual(bad, [])
        self.assertGreater(reads, 5, "too few engine reads to pin the contract")


class LadderReadsTheEngine(unittest.TestCase):
    """Finding 12 (ADR 0009): the ladder's Wyckoff cell shows the engine's TR/phase, not the narrative's."""

    def test_ladder_entry_cell_is_the_engine_read(self):
        dims = {d: {"engaged": d == "wyckoff", "reason": ("dims.reason.in_use", {})} for d in ("wyckoff", "ict", "footprint", "heatmap")}
        n3 = {"wyckoff": {"structure": "tích lũy", "phase": "C",
                          "trading_range": {"low": 11111, "high": 22222, "low_label": "SC", "high_label": "AR"}}}
        engine = {"tr": {"low": 33333, "high": 44444, "low_label": "AR", "high_label": "BC"}, "side": "short",
                  "phases": [{"label": "A", "status": "tested"}, {"label": "B", "status": "hypothesis"}]}
        html = ba.ladder({"tf": "15m", "tiers": {}}, "BTCUSDT", "int", "—", None, n3, {}, None, dims,
                         wy_engine={"entry": engine})
        self.assertIn("33,333", html)
        self.assertIn("44,444", html)
        self.assertNotIn("11,111", html, "the narrative TR must not sit beside the engine TR")
        self.assertIn("B?", html)
        empty = ba.ladder({"tf": "15m", "tiers": {}}, "BTCUSDT", "int", "—", None, n3, {}, None, dims,
                          wy_engine={"entry": dict(ba._WY_EMPTY)})
        self.assertNotIn("11,111", empty)


class I18nAndSource(unittest.TestCase):
    """Findings 13, 17 (and the chart.js wiring of 5)."""

    def test_legend_text_is_side_aware_and_names_the_engine(self):
        cat = json.load(open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8"))
        msgs, locales = cat["messages"], list(cat["locales"])
        for loc in locales:
            self.assertIn("{labels}", msgs["legend.tr"][loc])
            self.assertNotIn("full analysis", msgs["legend.wyckoff_events"][loc])
            self.assertNotIn("phân tích đầy đủ", msgs["legend.wyckoff_events"][loc])
            for key in ("chart.wyckoff.not_established_short", "chart.wyckoff.reason.sloped",
                        "chart.wyckoff.reason.st_lower_third", "chart.wyckoff.reason.b_tests_lower",
                        "chart.wyckoff.reason.unconfirmed", "chart.wyckoff.reason.expired", "chart.wyckoff.reason.open"):
                self.assertTrue(msgs[key][loc], (key, loc))
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertIn("L('legend.tr',{labels:wyTrLabels(d)})", src)

    def test_chart_feeds_the_engine_invalidation_and_marks_tick_spikes(self):
        src = open(CHART_JS, encoding="utf-8").read()
        self.assertNotIn("const invalidatedAt=null", src)
        self.assertIn("wy.invalidated_at.time", src)
        self.assertRegex(src, re.escape("o.r.toFixed(1)+'×'+(d.tick?' (tick)':'')"))


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class ChartBuilders(unittest.TestCase):
    """Findings 5, 7, 10, 11 in chart.js's pure builders."""

    ROWS = [[100 + i, 102 + i, 98 + i, 101 + i, 10, f"2026-09-01T{i // 4:02d}:{(i % 4) * 15:02d}:00Z"] for i in range(60)]

    def run_js(self, body):
        p = subprocess.run(["node", "-e", f"const T=require({json.dumps(CHART_JS)}); const rows={json.dumps(self.ROWS)}; {body}"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_compact_tier_draws_a_short_not_established_tag(self):
        out = self.run_js("console.log(JSON.stringify(T.wyckoffShapes(rows,{tr:null,events:[],phases:[]},{compact:true,fmt:String})));")
        labels = [s for s in out if s["kind"] == "label"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["text"], "chart.wyckoff.not_established_short")

    def test_contradicted_phase_is_drawn_with_question_mark_and_reason(self):
        out = self.run_js(
            "const wy={tr:{high:150,low:100,from:rows[2][5]},events:[],phases:["
            "{from:rows[2][5],to:rows[10][5],label:'A',status:'hypothesis',reasons:['st_lower_third']},"
            "{from:rows[10][5],to:rows[20][5],label:'B',status:'tested',reasons:[]}]};"
            "console.log(JSON.stringify(T.wyckoffShapes(rows,wy,{compact:false,fmt:String}).filter(s=>s.kind==='rect')));")
        self.assertEqual(out[0]["label"], "A? chart.wyckoff.reason.st_lower_third")
        self.assertFalse(out[0]["labelBold"])
        self.assertEqual(out[1]["label"], "B")
        self.assertTrue(out[1]["labelBold"])

    def test_range_ends_at_the_engine_end_bar(self):
        out = self.run_js(
            "const wy={tr:{high:150,low:100,from:rows[2][5],to:rows[30][5]},events:[],phases:[]};"
            "console.log(JSON.stringify(T.wyckoffShapes(rows,wy,{compact:false,fmt:String}).filter(s=>s.kind==='hseg')));")
        self.assertEqual([s["i2"] for s in out], [30.5, 30.5])

    def test_replay_hides_what_is_not_yet_available(self):
        out = self.run_js(
            "const wy={tr:{high:150,low:100,from:rows[2][5],available_at:'2026-09-01T03:00:00Z',to:rows[30][5],to_available_at:'2026-09-01T08:00:00Z'},"
            "events:[{time:rows[5][5],label:'SC 98',available_at:'2026-09-01T03:00:00Z'},{time:rows[20][5],label:'Spring 118',available_at:'2026-09-01T06:00:00Z'}],"
            "phases:[{from:rows[2][5],to:rows[20][5],label:'B',status:'tested',reasons:[],open_reasons:['open'],available_at:'2026-09-01T03:00:00Z',state_available_at:'2026-09-01T06:00:00Z'}],"
            "invalidated_at:{time:rows[25][5],available_at:'2026-09-01T07:00:00Z',reason:'close_beyond_spring_low'}};"
            "const a=T.wyckoffAt(wy,'2026-09-01T04:00:00Z'), b=T.wyckoffAt(wy,'2026-09-01T09:00:00Z');"
            "console.log(JSON.stringify({a,b}));")
        a, b = out["a"], out["b"]
        self.assertEqual(len(a["events"]), 1)
        self.assertIsNone(a["tr"]["to"])
        self.assertIsNone(a["invalidated_at"])
        self.assertIsNone(a["phases"][0]["to"])
        self.assertEqual(a["phases"][0]["status"], "hypothesis")
        self.assertEqual(len(b["events"]), 2)
        self.assertEqual(b["tr"]["to"], self.ROWS[30][5])
        self.assertEqual(b["invalidated_at"]["reason"], "close_beyond_spring_low")
        self.assertEqual(b["phases"][0]["status"], "tested")

    def test_engine_invalidation_renders_the_read_as_invalidated_keeping_its_labels(self):
        """ADR 0004: original labels stay, faded and suffixed; the breaking candle gets the 'x' mark."""
        out = self.run_js(
            "const wy={tr:{high:150,low:100,from:rows[2][5]},events:[{time:rows[5][5],label:'Spring 103',up:false}],"
            "phases:[{from:rows[2][5],to:null,label:'C',status:'hypothesis',reasons:['open']}]};"
            "console.log(JSON.stringify(T.wyckoffShapes(rows,wy,{compact:false,fmt:String,invalidatedAt:rows[30][5]})));")
        flags = [s for s in out if s["kind"] == "flag"]
        self.assertEqual(flags[0]["text"], "Spring 103")
        self.assertEqual(flags[0]["color"], "muted")
        self.assertTrue(any(s["kind"] == "mark" and s.get("glyph") == "x" and s["i"] == 30 for s in out))
        self.assertTrue(all("chart.wyckoff.invalidated_suffix" in s["label"] for s in out if s["kind"] == "hseg"))


if __name__ == "__main__":
    unittest.main()
