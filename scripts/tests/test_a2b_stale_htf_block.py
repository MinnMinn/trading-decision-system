"""A2b decision side (docs/plans/2026-09-28-methodology-improvement-plan.md §2 "A2b Staleness is a quality state",
knowledge R20; CLAUDE.md §20 "never silently convert STALE -> FRESH"): `fx_a2b_stale_htf_block`.

When the key is ON, `htf_bias_gate` refuses (False) if the last CLOSED higher-timeframe bar is older, at the
decision time, than `normalized.STALE_AFTER_BARS` x that timeframe -- the threshold `quality.assess` uses. When
OFF (v1, the default) the gate is unchanged. The live runner never sets the key."""
import importlib.util, os, sys, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


KEY = "fx_a2b_stale_htf_block"


class StaleHtfBlock(unittest.TestCase):
    def setUp(self):
        self.bt = load("backtest-methods.py")
        self.candles = [{"time": f"2026-01-01T{i:02d}:00:00Z"} for i in range(5)]   # 1H bars, closes 01:00..05:00
        self.key = ("BTCUSDT", "1H", 5, self.candles[0]["time"], self.candles[-1]["time"])
        self.bt._HTF_TIMES[self.key] = [f"2026-01-01T{i + 1:02d}:00:00Z" for i in range(5)]
        self.addCleanup(self.bt._HTF_TIMES.pop, self.key, None)
        p = mock.patch.object(self.bt, "load", return_value=(self.candles, "x")); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(self.bt.lr, "bias_at", return_value=("long", None)); p.start(); self.addCleanup(p.stop)

    def gate(self, decision_time, on):
        with mock.patch.dict(self.bt.OPTS, {KEY: on}):
            return self.bt.htf_bias_gate("BTCUSDT", "15m", "long", decision_time, ("wyckoff",))

    def test_default_is_off_and_v1_gate_ignores_staleness(self):
        self.assertFalse(self.bt.OPTS[KEY]); self.assertFalse(self.bt._OPTS_BASE[KEY])
        self.assertTrue(self.gate("2026-01-01T12:00:00Z", on=False))       # 7 h after the last HTF close

    def test_on_and_fresh_tier_still_agrees(self):
        self.assertTrue(self.gate("2026-01-01T05:00:00Z", on=True))         # age 0
        self.assertTrue(self.gate("2026-01-01T08:00:00Z", on=True))         # age exactly 3 h: not yet stale

    def test_on_and_stale_tier_refuses_with_false_not_none_and_not_true(self):
        self.assertIs(self.gate("2026-01-01T08:00:01Z", on=True), False)    # just past 3 x 1H
        self.assertIs(self.gate("2026-01-01T12:00:00Z", on=True), False)

    def test_on_does_not_turn_a_disagreeing_fresh_tier_into_agreement(self):
        with mock.patch.object(self.bt.lr, "bias_at", return_value=("short", None)):
            self.assertIs(self.gate("2026-01-01T05:00:00Z", on=True), False)


class Registration(unittest.TestCase):
    def test_key_is_in_opts_base_scan_relevant_keys_config_opts_and_snapshot_and_defaults_off(self):
        bt = load("backtest-methods.py"); sr = load("stability-report.py")
        self.assertIn(KEY, bt._OPTS_BASE); self.assertFalse(bt._OPTS_BASE[KEY])
        self.assertIn(KEY, sr._SCAN_RELEVANT_KEYS)
        overlay = sr.config_opts(sr.CONFIGS["A"], ict_target="range")
        self.assertIn(KEY, overlay); self.assertFalse(overlay[KEY])
        src = open(os.path.join(ROOT, "scripts", "snapshot.py"), encoding="utf-8").read()
        self.assertIn(KEY, src)

    def test_live_runner_never_sets_the_key(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn(KEY, src)


if __name__ == "__main__":
    unittest.main()
