"""scripts/scan_cache.py -- a cached scan is served only for the exact inputs it was computed under.

The end-to-end byte-identity of a cached stability run against an uncached one is checked by the acceptance run
(see the commit message); these tests pin the key, the store and the two integration points without running a
real scan.
"""
import contextlib, functools, importlib.util, io, os, shutil, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scan_cache as SC  # noqa: E402


def _tmp():
    return tempfile.mkdtemp(dir=os.environ.get("TMP"))


class _FakeBt:
    """Just what scan_cache reads: the two cutoffs, scan() and load()."""
    _PIT_CUTOFF = None
    _BARS_LIMIT = None

    def __init__(self):
        self.scans, self.loaded = 0, []

    def load(self, s, t):
        self.loaded.append((s, t))
        return [], None

    def scan(self, sym, tf, only=None, opts=None):
        self.scans += 1
        self.load(sym, tf); self.load(sym, "4H"); self.load(sym, tf)
        return {"symbol": sym, "tf": tf, "only": only, "trades": {"ICT": [{"R": 1.25}]}}


def _fake_root():
    root = _tmp()
    for d in ("scripts", os.path.join("docs", "architecture"), os.path.join("data", "history")):
        os.makedirs(os.path.join(root, d))
    for rel, body in (("scripts/a.py", "x = 1\n"), ("docs/architecture/p.json", "{}"),
                      ("data/history/ohlcv.XAUUSD.1H.json", "[1]"), ("data/history/ohlcv.XAUUSD.4H.json", "[2]"),
                      ("data/history/ohlcv.XAGUSD.1H.json", "[3]")):
        with open(os.path.join(root, rel), "w") as fh:
            fh.write(body)
    return root


class TheKey(unittest.TestCase):
    def setUp(self):
        self.root = _fake_root(); self.bt = _FakeBt(); SC._DIGESTS.clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def key(self, **kw):
        return SC.full_key(self.root, self.bt, kw.get("sym", "XAUUSD"), kw.get("scan_key", ("XAUUSD", "1H", "A")),
                           only=kw.get("only"))

    def _rewrite(self, rel, body):
        p = os.path.join(self.root, rel)
        with open(p, "w") as fh:
            fh.write(body)
        st = os.stat(p); os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

    def test_same_inputs_same_key(self):
        self.assertEqual(self.key(), self.key())

    def test_any_history_file_of_the_symbol_changes_the_key(self):
        k = self.key(); self._rewrite("data/history/ohlcv.XAUUSD.4H.json", "[9]")   # an HTF companion, not tf
        self.assertNotEqual(k, self.key())

    def test_another_symbols_history_does_not(self):
        k = self.key(); self._rewrite("data/history/ohlcv.XAGUSD.1H.json", "[9]")
        self.assertEqual(k, self.key())

    def test_code_or_architecture_config_changes_the_key(self):
        k = self.key(); self._rewrite("scripts/a.py", "x = 2\n"); k2 = self.key()
        self.assertNotEqual(k, k2)
        self._rewrite("docs/architecture/p.json", '{"a": 1}')
        self.assertNotEqual(k2, self.key())

    def test_pit_cutoff_bars_limit_only_and_scan_key_change_the_key(self):
        k = self.key()
        self.bt._PIT_CUTOFF = "2025-03-01T00:00:00Z"; self.assertNotEqual(k, self.key()); self.bt._PIT_CUTOFF = None
        self.bt._BARS_LIMIT = 500; self.assertNotEqual(k, self.key()); self.bt._BARS_LIMIT = None
        self.assertNotEqual(k, self.key(only=("ICT",)))
        self.assertNotEqual(k, self.key(scan_key=("XAUUSD", "1H", "B")))
        self.assertEqual(k, self.key())


class TheStore(unittest.TestCase):
    def setUp(self):
        self.dir = _tmp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_round_trip_is_exact(self):
        c = SC.ScanCache(self.dir, ROOT)
        res = {"trades": {"ICT": [{"R": 0.1 + 0.2, "entry_time": "2024-01-01T00:00:00Z"}]}, "bars": 3}
        c.put(("k",), res, [("XAUUSD", "1H")])
        self.assertEqual(c.get(("k",)), (res, [("XAUUSD", "1H")]))
        self.assertEqual((c.hits, c.misses, c.writes), (1, 0, 1))

    def test_an_entry_under_a_different_key_is_never_served(self):
        c = SC.ScanCache(self.dir, ROOT)
        c.put(("k1",), {"x": 1}, [])
        os.replace(c._path(("k1",)), c._path(("k2",)))     # a collided / hand-copied file
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(c.get(("k2",)))
        self.assertIn("different key", err.getvalue())
        self.assertIsNone(c.get(("absent",)))
        self.assertEqual(c.misses, 2)


class CachedScan(unittest.TestCase):
    def setUp(self):
        self.root = _fake_root(); self.dir = _tmp(); SC._DIGESTS.clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True); shutil.rmtree(self.dir, ignore_errors=True)

    def test_no_cache_is_a_plain_scan(self):
        bt = _FakeBt()
        self.assertEqual(SC.cached_scan(None, self.root, bt, "XAUUSD", "1H", ("k",), only=("ICT",))["only"], ("ICT",))
        self.assertEqual(bt.scans, 1)

    def test_a_hit_scans_nothing_and_replays_the_first_loads_in_order(self):
        first = _FakeBt()
        r1 = SC.cached_scan(SC.ScanCache(self.dir, self.root), self.root, first, "XAUUSD", "1H", ("k",), only=("ICT",))
        second = _FakeBt()
        r2 = SC.cached_scan(SC.ScanCache(self.dir, self.root), self.root, second, "XAUUSD", "1H", ("k",), only=("ICT",))
        self.assertEqual(r1, r2)
        self.assertEqual(second.scans, 0)
        self.assertEqual(second.loaded, [("XAUUSD", "1H"), ("XAUUSD", "4H")])

    def test_a_different_only_is_a_different_scan(self):
        bt = _FakeBt(); disk = SC.ScanCache(self.dir, self.root)
        SC.cached_scan(disk, self.root, bt, "XAUUSD", "1H", ("k",), only=("ICT",))
        SC.cached_scan(disk, self.root, bt, "XAUUSD", "1H", ("k",), only=("WYCKOFF-BOOK",))
        self.assertEqual(bt.scans, 2)


class RunScansThroughTheDisk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("stability_report_sc", os.path.join(ROOT, "scripts", "stability-report.py"))
        cls.SR = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.SR)

    def setUp(self):
        self.dir = _tmp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    TASKS = [("BTCUSDT", "1H", {"mgmt": "none"}, ("BTCUSDT", "1H", "none")),
             ("ETHUSDT", "1H", {"mgmt": "none"}, ("ETHUSDT", "1H", "none"))]

    def _run(self, **kw):
        calls = []

        def worker(sym, tf, overlay):
            calls.append(sym)
            return {"symbol": sym}, [(sym, tf)]
        with mock.patch.object(self.SR, "_worker_scan", side_effect=worker):
            out = self.SR.run_scans(list(self.TASKS), workers=1, disk=self.SR._sc.ScanCache(self.dir, ROOT), **kw)
        return out, calls

    def test_second_run_is_all_hits_with_identical_results(self):
        first, calls1 = self._run()
        second, calls2 = self._run()
        self.assertEqual(calls1, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(calls2, [])
        self.assertEqual(first, second)

    def test_require_cached_refuses_to_compute(self):
        with self.assertRaises(SystemExit):
            self._run(require_cached=True)

    def test_require_cached_passes_when_everything_is_there(self):
        self._run()
        out, calls = self._run(require_cached=True)
        self.assertEqual((sorted(out), calls), (sorted(t[3] for t in self.TASKS), []))


class PropSearchScans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prop_search_sc", os.path.join(ROOT, "scripts", "prop-search.py"))
        cls.PS = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.PS)

    def test_distinct_scans_cover_every_candidate_once(self):
        plan = self.PS.load_plan()
        scans = self.PS._distinct_scans(plan)
        keys = [(s["symbol"], s["tf"], s["method"], s["config"]) for s in scans]
        self.assertEqual(len(keys), len(set(keys)))
        for c in plan["candidates"]:
            for sym in c["symbols"]:
                if self.PS._has_predevelopment_history(sym, c["timeframe"]):
                    self.assertIn((sym, c["timeframe"], c["method"], c["config"]), keys)

    def test_fill_scan_refuses_a_scan_outside_the_plan(self):
        with mock.patch.object(self.PS, "SCAN_CACHE_DIR", _tmp()):
            with self.assertRaises(SystemExit):
                self.PS.cmd_fill_scan("BTCUSDT", "1H", "ICT", "A")

    def test_candidates_scan_through_the_cache_with_the_method_as_only(self):
        seen = {}

        def fake(disk, root, bt, sym, tf, scan_key, only=None, opts=None):
            seen.update(disk=disk, sym=sym, only=only, pit=bt._PIT_CUTOFF)
            return None
        sr = self.PS._load_sr()
        with mock.patch.object(self.PS._sc, "cached_scan", side_effect=fake),                 mock.patch.object(self.PS, "SCAN_CACHE_DIR", None):
            self.PS._scan(sr, "XAUUSD", "1H", "ICT", sr.config_opts(sr.CONFIGS["A"], ict_target="range"))
        self.assertEqual((seen["disk"], seen["sym"], seen["only"]), (None, "XAUUSD", ("ICT",)))


if __name__ == "__main__":
    unittest.main()
