"""The journal page's cumulative-R curve is drawn by the vendored Lightweight Charts build (same as the chart pages)."""
import importlib.util, json, os, re, shutil, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


CLOSED = [dict(id="2026-09-01-BTCUSDT-01", r_multiple=1.5, date_closed="2026-09-01T10:00:00Z", setup_type="Spring"),
          dict(id="2026-09-02-ETHUSDT-01", r_multiple=-1.0, date_closed="2026-09-02T10:00:00Z", setup_type="UTAD"),
          dict(id="2026-09-02-SOLUSDT-01", r_multiple=2.0, date_closed="2026-09-02T10:00:00Z", setup_type="Spring")]


class RCurve(unittest.TestCase):
    def setUp(self):
        self.jr = load("journal_render.py")

    def test_empty_state_without_closed_trades(self):
        self.assertIn("Chưa có lệnh đóng", self.jr.r_curve([]))
        self.assertNotIn("JournalChart", self.jr.r_curve([dict(id="x", r_multiple=None)]))

    def test_points_are_cumulative_and_strictly_increasing_in_time(self):
        html = self.jr.r_curve(CLOSED)
        m = re.search(r"JournalChart\.rcurve\([^,]+,[^,]+, (\[.*\])\);</script>", html, re.S)
        self.assertIsNotNone(m, "rcurve call missing")
        pts = json.loads(m.group(1))
        self.assertEqual([p["value"] for p in pts], [1.5, 0.5, 2.5])
        self.assertTrue(all(b["time"] > a["time"] for a, b in zip(pts, pts[1:])), "same-second closes must be nudged apart")
        self.assertEqual(pts[2]["id"], "2026-09-02-SOLUSDT-01")

    def test_journal_logo_off_and_notice_in_footer(self):
        self.assertTrue("attributionLogo:false" in self.jr.JOURNAL_JS)
        src = open(os.path.join(ROOT, "scripts", "journal_render.py"), encoding="utf-8").read()
        self.assertTrue("TradingView Lightweight Charts™ · Copyright (c) 2025 TradingView, Inc." in src and 'href="https://www.tradingview.com/"' in src)

    def test_vendor_script_is_inlined(self):
        s = self.jr.vendor_script()
        self.assertTrue("TradingView Lightweight Charts" in s and "JournalChart" in s)
        self.assertIsNone(re.search(r'src="https?://', s))


if __name__ == "__main__":
    unittest.main()
