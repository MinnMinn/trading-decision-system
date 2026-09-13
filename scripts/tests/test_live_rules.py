"""The backtest must see exactly what the live scanner saw: the same trailing window, and not one bar more.

A look-ahead bug here is invisible in the results (it just makes them better), so it is pinned by construction:
read_at(i) must depend only on candles[:i+1], which is asserted by mutating the future and re-reading, and by
truncating the candle list at i+1 and checking the read is unchanged (docs/plans/2026-09-13-unify-backtest-with-live-rules.md).

Code-quality review of the first cut (commit acd65c5) found two Critical defects, fixed here:
- read_at must require the FULL live window (len(window) == bars), not merely "enough" bars -- a partial
  window is a window live never produces (different median range/pivots/equilibrium).
- window() must raise IndexError for i outside [0, len(candles)), not silently slice to something plausible.
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

    def test_window_raises_index_error_for_negative_i(self):
        c = candles(800)
        with self.assertRaises(IndexError):
            self.lr.window(c, -2, "15m")
        with self.assertRaises(IndexError):
            self.lr.window(c, -50, "15m")

    def test_window_raises_index_error_for_i_at_or_past_len_candles(self):
        c = candles(800)
        with self.assertRaises(IndexError):
            self.lr.window(c, len(c), "15m")
        with self.assertRaises(IndexError):
            self.lr.window(c, 1000, "15m")


class ReadAtRequiresFullWindow(unittest.TestCase):
    """Pins Critical 1's fix: read_at must return None until the window is the FULL live window, not merely
    'enough' bars. Both boundary indices are derived from scan_spec(tf)[0] -- not hardcoded -- so this test
    would have caught a MIN_BARS-style partial-window bug for any timeframe, not just the one checked."""

    def setUp(self):
        self.lr = load("live_rules.py")

    def test_read_at_is_none_before_there_are_enough_bars(self):
        self.assertIsNone(self.lr.read_at(candles(20), 10, "15m", methods=("ict",)))

    def test_read_at_is_none_one_bar_short_of_the_full_window(self):
        bars, _ = self.lr.scan_spec("15m")
        c = candles(bars + 50)
        one_short = bars - 2  # index i=bars-2 -> window has bars-1 candles, one short of full
        self.assertIsNone(self.lr.read_at(c, one_short, "15m", methods=("ict",)))

    def test_read_at_returns_a_result_at_the_first_fully_windowed_index(self):
        bars, _ = self.lr.scan_spec("15m")
        c = candles(bars + 50)
        first_full = bars - 1  # index i=bars-1 -> window has exactly `bars` candles
        self.assertIsNotNone(self.lr.read_at(c, first_full, "15m", methods=("ict",)))


class NoLookAhead(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_future_bars_cannot_change_the_read(self):
        c = candles()
        before = self.lr.read_at(c, 700, "15m", methods=("ict",))
        for x in c[701:]:
            x["high"] += 5000; x["low"] -= 5000; x["close"] += 5000
        after = self.lr.read_at(c, 700, "15m", methods=("ict",))
        self.assertEqual(before, after)

    def test_truncating_the_candle_list_at_i_plus_1_reads_the_same(self):
        """Catches a different class of bug than future-mutation: an index computed from len(candles)
        rather than from i would not notice future bars being untouched, but WOULD notice the list
        being shorter."""
        c = candles()
        full = self.lr.read_at(c, 700, "15m", methods=("ict",))
        truncated = self.lr.read_at(c[:701], 700, "15m", methods=("ict",))
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

    def test_scan_spec_raises_for_a_timeframe_live_never_scans(self):
        """The backtest must fail loudly on a timeframe live doesn't run, not invent a window for it."""
        with self.assertRaises(KeyError):
            self.lr.scan_spec("30m")
        with self.assertRaises(KeyError):
            self.lr.scan_spec("2H")


class BiasMatchesHtfContext(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")
        self.htf = load("htf_context.py")

    def test_bias_at_uses_htf_context_not_a_reimplementation(self):
        """methods=("wyckoff",) here, not ("ict",): ("ict",) happens to equal a plausible default, so a
        bias_at that forgot to forward `methods` at all could still pass by accident. wyckoff exercises the
        forwarding for real."""
        c = candles()
        facts = self.lr.read_at(c, 700, "15m", methods=("wyckoff",))
        self.assertEqual(self.lr.bias_at(c, 700, "15m", methods=("wyckoff",)),
                         self.htf.bias_of(None, facts, methods=("wyckoff",)))

    def test_bias_at_accepts_precomputed_facts_instead_of_recomputing(self):
        c = candles()
        facts = self.lr.read_at(c, 700, "15m", methods=("wyckoff",))
        self.assertEqual(self.lr.bias_at(c, 700, "15m", methods=("wyckoff",), facts=facts),
                          self.htf.bias_of(None, facts, methods=("wyckoff",)))


class MethodsIsRequired(unittest.TestCase):
    def setUp(self):
        self.lr = load("live_rules.py")

    def test_read_at_without_methods_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.lr.read_at(candles(), 700, "15m")

    def test_bias_at_without_methods_raises_type_error(self):
        with self.assertRaises(TypeError):
            self.lr.bias_at(candles(), 700, "15m")


if __name__ == "__main__":
    unittest.main()
