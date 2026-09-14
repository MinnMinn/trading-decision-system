"""The timeframe ladder is ONE rule (docs/architecture/timeframe-mapping.md §3): adjacent tiers are the next available rung
>= 4x. These tests pin the derived tables so a change to the rule or the rungs is a visible, deliberate diff."""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Ladder(unittest.TestCase):
    def setUp(self):
        self.a = load("automation.py")

    def test_rule_of_four_reproduces_the_pilot_structure_table(self):
        rungs = ["5m", "15m", "30m", "1H", "2H", "4H", "1D"]
        self.assertEqual({tf: self.a.next_rung(tf, rungs) for tf in rungs},
                         {"5m": "30m", "15m": "1H", "30m": "2H", "1H": "4H", "2H": "1D", "4H": "1D", "1D": None})

    def test_page_tiers(self):
        """Six styles since 2026-09-13 (three horizons x two markets), and the two markets now share one rung set,
        so the same horizon gets the same ladder in both -- the prefix routes the market, not the geometry."""
        t = {k: (v["structure"] and v["structure"]["tf"], v["bias"] and v["bias"]["tf"]) for k, v in self.a.TIERS.items()}
        self.assertEqual(t, {"scalping": ("1h", "4h"), "day": ("4h", "1D"), "swing": ("1D", "1W"),
                             "cfd-scalping": ("1h", "4h"), "cfd-day": ("4h", "1D"), "cfd-swing": ("1D", "1W")})

    def test_gate_is_bias_when_scanned_else_structure(self):
        self.assertEqual(self.a.gate_style("scalping"), ("swing", "bias"))
        self.assertEqual(self.a.gate_style("day"), ("swing", "structure"))    # 1D is chart-only, not scanned
        self.assertEqual(self.a.gate_style("swing"), (None, None))            # 1D and 1W are both chart-only
        self.assertEqual(self.a.CONTEXT_STYLE["cfd-scalping"], "cfd-swing")   # never the other market's style

    def test_runner_and_backtest_share_the_rule(self):
        r = load("strategy-runner.py"); b = load("backtest-methods.py")
        self.assertEqual({k: v for k, v in r.HTF_OF.items() if v}, b.HTF_OF)

    def test_scan_window_table_matches_the_loop(self):
        """The window the live scanner reads is a number the backtest must reproduce exactly; it lived only in
        scan-loop.sh, where nothing could import it."""
        self.assertEqual(self.a.SCAN_WINDOW["1m"], {"bars": 360, "recent": 4})
        self.assertEqual(self.a.SCAN_WINDOW["15m"], {"bars": 576, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["1H"], {"bars": 480, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["4H"], {"bars": 360, "recent": 2})
        self.assertEqual(self.a.SCAN_WINDOW["1D"], {"bars": 240, "recent": 1})
        self.assertEqual(self.a.SCAN_WINDOW["5m"], {"bars": 576, "recent": 4})


if __name__ == "__main__":
    unittest.main()
