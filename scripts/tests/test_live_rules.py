"""The backtest must see exactly what the live scanner saw: the same trailing window, and not one bar more.

A look-ahead bug here is invisible in the results (it just makes them better), so it is pinned by construction:
read_at(i) must depend only on candles[:i+1], which is asserted by mutating the future and re-reading, and by
truncating the candle list at i+1 and checking the read is unchanged (docs/plans/2026-09-13-unify-backtest-with-live-rules.md).
"""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def candles(n=800, base=100.0):
    out = []
    for i in range(n):
        out.append({"time": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}Z", "open": base + (i % 3),
                    "high": base + 2 + (i % 7), "low": base - 2 - (i % 5), "close": base + (i % 3),
                    "volume": 10.0})
    return out


class Window(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_window_is_the_live_scan_window_for_that_timeframe(self):
        c = candles()
        w = self.lr.window(c, 700, "15m")
        self.assertEqual(len(w), 576)
        self.assertIs(w[-1], c[700])

    def test_window_is_short_near_the_start_not_padded(self):
        c = candles(100)
        self.assertEqual(len(self.lr.window(c, 40, "15m")), 41)

    def test_read_at_is_none_before_there_are_enough_bars(self):
        self.assertIsNone(self.lr.read_at(candles(20), 10, "15m"))


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_future_bars_cannot_change_the_read(self):
        c = candles()
        before = self.lr.read_at(c, 700, "15m")
        for x in c[701:]:
            x["high"] += 5000; x["low"] -= 5000; x["close"] += 5000
        after = self.lr.read_at(c, 700, "15m")
        self.assertEqual(before, after)

    def test_truncating_the_candle_list_at_i_plus_1_reads_the_same(self):
        """Catches a different class of bug than future-mutation: an index computed from len(candles)
        rather than from i would not notice future bars being untouched, but WOULD notice the list
        being shorter."""
        c = candles()
        full = self.lr.read_at(c, 700, "15m")
        truncated = self.lr.read_at(c[:701], 700, "15m")
        self.assertEqual(full, truncated)


class SetupLookback(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.auto = load("automation.py")

    def test_setup_lookback_matches_live_default_for_every_scanned_timeframe(self):
        """ict-scan.py:466 -- args.setup_lookback or max(12, args.recent * 6). Must be derived from
        SCAN_WINDOW's recent, not hardcoded per timeframe."""
        for tf, w in self.auto.SCAN_WINDOW.items():
            self.assertEqual(self.lr.setup_lookback(tf), max(12, w["recent"] * 6))


class UnknownTimeframe(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_spec_raises_for_a_timeframe_live_never_scans(self):
        """The backtest must fail loudly on a timeframe live doesn't run, not invent a window for it."""
        with self.assertRaises(KeyError):
            self.lr.spec("30m")
        with self.assertRaises(KeyError):
            self.lr.spec("2H")


class BiasMatchesHtfContext(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.htf = load("htf_context.py")

    def test_bias_at_uses_htf_context_not_a_reimplementation(self):
        c = candles()
        facts = self.lr.read_at(c, 700, "15m")
        self.assertEqual(self.lr.bias_at(c, 700, "15m", ("ict",)),
                         self.htf.bias_of(None, facts, methods=("ict",)))


if __name__ == "__main__":
    unittest.main()
