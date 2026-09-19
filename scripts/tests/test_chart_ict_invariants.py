"""What the ICT overlay DRAWS, checked against the candles it drew it from.

Asked for after a reader questioned the Wyckoff chart on the same page (2026-09-19) and the Wyckoff read did
turn out to be wrong. ICT is computed differently -- `ictAnalyze` in scripts/chart.js runs in the browser on
each tier's OWN rows, so unlike Wyckoff it cannot borrow a structure from another timeframe -- but "computed
from the right candles" is not the same as "computed correctly", and nothing was checking the second.

Every assertion below is a rule from the decks, re-derived from the rows rather than trusted:

  * dealing range = nearest unswept BUYSIDE pool above / SELLSIDE pool below the last close, window extreme
    only as the declared fallback, and `drSource` must say which (knowledge/ict/core-a.md §2.18-2.19)
  * a pool's `swept` flag: a wick through the level and a close back, searched from the bar the pool FORMED
  * every open FVG is a real three-candle gap at its own index (knowledge/ict/core-a.md §2.21)
  * every MSS is a BODY close beyond its swing, with origin <= swept extreme <= MSS bar (§2.17, core-b §2.2)
  * OTE is exactly 0.62 / 0.705 / 0.79, deepening away from the terminus, 0.705 midway (§2.20)
  * STDEV projections are exactly -2 / -2.5 / -4 and ordered (knowledge/ict/models.md §2.1.5)

Three of these caught ME rather than the chart while this was being written, which is the reason they are
written down: a "nearest unswept pool below" that ignored pool KIND (a BSL below the close is not eligible to
be the range low), a sweep search started from the EARLIER of two equal swings, and an OTE band read through
`lo`/`hi` fields the object does not have. All three produced confident-looking violation lists. The pool
sweep check was only made possible by exporting the forming bar (`at`) from chart.js in the same change --
before that the flag could not be verified from outside at all.
"""
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ict-invariants.js")
PARAMS = os.path.join(ROOT, "docs", "architecture", "analysis-params.json")
CHART = os.path.join(ROOT, "scripts", "chart.js")
TF_MIN = {"15m": 15, "1H": 60, "4H": 240}
BARS = {"15m": 576, "1H": 480, "4H": 360}


def _node_available():
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True).returncode == 0
    except Exception:
        return False


class ThePoolContractIsCheckable(unittest.TestCase):
    """No node needed: the forming bar must stay exported, or every check below goes dark."""

    def test_chart_js_exports_the_bar_a_pool_forms_on(self):
        src = open(CHART, encoding="utf-8").read()
        self.assertIn("at:last", src, "chart.js stopped exporting the pool's forming bar")
        self.assertIn("the bar the pool BECOMES one", src,
                      "the reason `at` exists must stay next to it, or it will be removed as redundant")

    @unittest.skipUnless(_node_available(), "node not available")
    def test_ict_analyze_is_reachable_from_node(self):
        """chart.js is UMD precisely so its pure parts can be tested without a browser. Asserted by actually
        requiring it, not by pattern-matching the source -- the export list is the property, not the words."""
        r = subprocess.run(["node", "-e",
                            f"const T=require({CHART!r});"
                            "process.stdout.write(typeof T.ictAnalyze)"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertEqual(r.stdout, "function", "chart.js no longer exports ictAnalyze for node")


@unittest.skipUnless(_node_available(), "node not available")
class TheIctOverlayMatchesItsOwnCandles(unittest.TestCase):
    """Runs the real `ictAnalyze` from scripts/chart.js over real stored history and re-derives every object
    it produced from the candles it produced them from."""

    @classmethod
    def setUpClass(cls):
        series = []
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSD"):
            for tf, bars in BARS.items():
                p = os.path.join(ROOT, "data", "history", f"ohlcv.{sym}.{tf}.json")
                if not os.path.exists(p):
                    continue
                c = json.load(open(p, encoding="utf-8"))["candles"][-bars:]
                series.append({"sym": sym, "tf": tf,
                               "rows": [[x["open"], x["high"], x["low"], x["close"], x.get("volume", 0), x["time"]]
                                        for x in c],
                               "cfg": {"kz": tf in ("15m", "1H"), "tfMin": TF_MIN[tf], "market": "crypto"}})
        cls.series_n = len(series)
        if not series:
            cls.res = {"cnt": {"series": 0, "pools": 0, "fvg": 0, "mss": 0, "ote": 0, "std": 0}, "bad": []}
            return
        import tempfile
        fd = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(series, fd); fd.close()
        try:
            r = subprocess.run(["node", CHECK, CHART, PARAMS, fd.name], capture_output=True, text=True)
        finally:
            os.unlink(fd.name)
        if r.returncode != 0:
            raise AssertionError("node could not run the invariant check: " + r.stderr[-800:])
        cls.res = json.loads(r.stdout)

    def test_the_sweep_actually_exercised_something(self):
        """A check that examined nothing cannot fail, which is how this kind of test rots."""
        if not self.series_n:
            self.skipTest("no stored history on this machine")
        c = self.res["cnt"]
        self.assertGreater(c["series"], 0)
        self.assertGreater(c["pools"], 0)
        self.assertGreater(c["mss"], 0)

    def test_every_ict_object_agrees_with_the_rows_it_was_drawn_from(self):
        if not self.series_n:
            self.skipTest("no stored history on this machine")
        self.assertEqual(self.res["bad"], [],
                         "ICT overlay disagrees with its own candles:\n  " + "\n  ".join(self.res["bad"][:20]))


if __name__ == "__main__":
    unittest.main()
