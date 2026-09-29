"""chart.js must not detect ICT structure (ADR 0009, docs/audits/2026-09-29-a2-chart-from-engine.md).

The one ICT detector is scripts/ict-scan.py `analyze()`; the chart only renders what scripts/structures.py wraps from
it. A detector re-introduced under ANOTHER NAME would slip past a check for one old function name, so this file
checks what a detector DOES rather than what it is called:

  * BEHAVIOUR: hand `ictFromStructures` / `ictShapes` candles containing a textbook swing high, an equal-highs
    pool, a three-candle gap, a wick sweep and a displaced break -- but an EMPTY engine structure list. The chart
    must draw none of them: its ICT read is a function of the engine's structures, never of the candles.
  * SOURCE: no code in chart.js compares one candle's price with a NEIGHBOURING candle's (`rows[i-1][HIGH]`, the
    shape every pivot / FVG / sweep / MSS scan takes), and none takes a window extreme with `Math.max(...highs)`.

The ICT invariants themselves (pools, dealing range, FVG, MSS re-derived from candles) are tested where the detector
lives: scripts/tests/test_ict_candle_invariants.py, test_audit_round2_ict.py, test_structures.py.
"""
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHART = os.path.join(ROOT, "scripts", "chart.js")


def _node_available():
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True).returncode == 0
    except Exception:
        return False


def _rows_with_every_textbook_pattern():
    """[o,h,l,c,v,iso] rows: equal highs at 105 (bars 4 and 10), a wick sweep of them (bar 14: high 107, close
    103), a bullish three-candle gap at bar 20 (high[19] < low[21]) and a displaced close above the swing at bar 22."""
    rows = []
    for i in range(30):
        o, h, l, c = 100.0, 101.0, 99.0, 100.0
        if i in (4, 10): h = 105.0
        if i == 14: h, c = 107.0, 103.0
        if i == 19: h = 100.5
        if i == 20: o, h, l, c = 100.5, 108.0, 100.4, 107.5
        if i == 21: o, h, l, c = 107.5, 109.0, 106.0, 108.5
        if i == 22: o, h, l, c = 108.5, 115.0, 108.0, 114.5
        rows.append([o, h, l, c, 10.0, f"2026-01-01T{i:02d}:00:00Z"])
    return rows


class ChartJsDoesNotDetectIct(unittest.TestCase):
    @unittest.skipUnless(_node_available(), "node not available")
    def test_candles_alone_produce_no_ict_object(self):
        rows = _rows_with_every_textbook_pattern()
        r = subprocess.run(["node", "-e",
                            f"const T=require({CHART!r}); const rows={json.dumps(rows)};"
                            "const ict=T.ictFromStructures([],{},rows,{tfMin:60});"
                            "const sh=T.ictShapes(rows,ict,{compact:false,fmt:v=>String(v)});"
                            "process.stdout.write(JSON.stringify({pools:ict.pools.length,fvgs:ict.fvgs.length,mss:ict.mss.length,"
                            "lo:ict.lo,hi:ict.hi,kinds:[...new Set(sh.map(s=>s.kind))].sort()}))"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        out = json.loads(r.stdout)
        self.assertEqual((out["pools"], out["fvgs"], out["mss"], out["lo"], out["hi"]), (0, 0, 0, None, None),
                         "chart.js produced an ICT object from candles alone: a detector has been re-introduced")
        # what is drawn is the single 'structure not established' note and the now marker -- nothing else
        self.assertEqual(out["kinds"], ["label", "mark"])

    def test_no_neighbour_candle_scan_in_the_source(self):
        src = open(CHART, encoding="utf-8").read()
        neighbour = re.findall(r"\[\s*[A-Za-z_]\w*\s*[-+]\s*\d+\s*\]\s*\[\s*(?:HIGH|LOW|CLOSE|OPEN)\s*\]", src)
        self.assertEqual(neighbour, [], "chart.js indexes a neighbouring candle's price: that is the shape of a pivot/FVG/sweep scan")
        self.assertIsNone(re.search(r"Math\.(?:max|min)\(\s*\.\.\.[^)]*(?:HIGH|LOW)", src),
                          "chart.js takes a window extreme from the candles: the dealing range comes from the engine")

    def test_the_old_detector_names_are_gone(self):
        src = open(CHART, encoding="utf-8").read()
        for name in ("ictAnalyze", "ictParams"):
            self.assertNotIn(name, src)

    def test_the_source_check_would_catch_a_detector(self):
        """The regex is only worth having if it matches what it is for."""
        pat = r"\[\s*[A-Za-z_]\w*\s*[-+]\s*\d+\s*\]\s*\[\s*(?:HIGH|LOW|CLOSE|OPEN)\s*\]"
        self.assertTrue(re.search(pat, "if(rows[i-1][HIGH] < rows[i+1][LOW]) fvg.push(i)"))
        self.assertFalse(re.search(pat, "const c=rows[i], up=c[CLOSE]>=c[OPEN]"))


if __name__ == "__main__":
    unittest.main()
