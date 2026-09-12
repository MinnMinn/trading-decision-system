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
        t = {k: (v["structure"] and v["structure"]["tf"], v["bias"] and v["bias"]["tf"]) for k, v in self.a.TIERS.items()}
        self.assertEqual(t, {"scalping": ("15m", "1h"), "daytrade": ("1h", "4h"), "1h": ("4h", "1D"), "4h": ("1D", "1W"), "swing": ("1W", None),
                             "gold-scalp": ("1h", "4h"), "gold": ("1h", "4h"), "gold-1h": ("4h", "1D"), "gold-4h": ("1D", "1W"), "gold-swing": ("1W", None)})

    def test_gate_is_bias_when_scanned_else_structure(self):
        self.assertEqual(self.a.gate_style("daytrade"), ("4h", "bias"))
        self.assertEqual(self.a.gate_style("4h"), ("swing", "structure"))     # 1W is chart-only
        self.assertEqual(self.a.gate_style("swing"), (None, None))
        self.assertEqual(self.a.CONTEXT_STYLE["gold-scalp"], "gold-4h")

    def test_runner_and_backtest_share_the_rule(self):
        r = load("strategy-runner.py"); b = load("backtest-methods.py")
        self.assertEqual({k: v for k, v in r.HTF_OF.items() if v}, b.HTF_OF)


if __name__ == "__main__":
    unittest.main()
