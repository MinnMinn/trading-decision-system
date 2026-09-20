"""Which Wyckoff events a narrative may carry, in time.

Until 2026-09-20 check-narrative.py refused any event dated before the scanner's working window (15m x 576 =
6 days). A Wyckoff structure does not start when the window does: BTC's SC/AR were 2026-09-10 and the UA sat
15 minutes before the window's first candle, so the first daily-full that actually ran (the launchd fix) could
write only Shakeout + BU -- two events -- while the prompt asked for 6-10, and the model was blamed for it.
The origin of the structure (`trading_range.from`, or the first phase band) is the correct lower bound; the
last candle stays the upper bound (point-in-time: never an event after the data). chart.js drops whatever
falls before its window by itself (idxOf -> -1), so an earlier event never draws in the wrong place.
"""
import importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mod():
    spec = importlib.util.spec_from_file_location("check_narrative", os.path.join(ROOT, "scripts", "check-narrative.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


CN = _mod()
WIN = ("2026-09-14T02:30:00Z", "2026-09-20T02:15:00Z")


class EventWindowFollowsTheStructure(unittest.TestCase):
    def test_lower_bound_is_the_trading_range_origin_when_it_predates_the_window(self):
        wy = {"trading_range": {"from": "2026-09-10T12:45:00Z"}}
        self.assertEqual(CN.event_window(wy, WIN), ("2026-09-10T12:45:00Z", WIN[1]))

    def test_lower_bound_is_the_first_phase_band_when_there_is_no_trading_range(self):
        wy = {"phases": [{"from": "2026-09-11T00:00:00Z"}, {"from": "2026-09-12T00:00:00Z"}]}
        self.assertEqual(CN.event_window(wy, WIN), ("2026-09-11T00:00:00Z", WIN[1]))

    def test_window_is_unchanged_when_the_structure_starts_inside_it(self):
        wy = {"trading_range": {"from": "2026-09-16T00:00:00Z"}}
        self.assertEqual(CN.event_window(wy, WIN), WIN)

    def test_no_structure_means_the_scanner_window(self):
        self.assertEqual(CN.event_window({}, WIN), WIN)

    def test_upper_bound_never_moves_past_the_last_candle(self):
        wy = {"trading_range": {"from": "2026-09-10T12:45:00Z"}, "phases": [{"from": "2026-09-21T00:00:00Z"}]}
        self.assertEqual(CN.event_window(wy, WIN)[1], WIN[1])


if __name__ == "__main__":
    unittest.main()
