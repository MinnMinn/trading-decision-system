"""engine-speed (b3-speed): every optimisation must leave the trades BYTE-IDENTICAL to the engine as it was at BASE
(fef6d6b, "before any speed work"). This file is the proof, and it is differential -- the reference is the pre-change
code itself (`git archive` of BASE into a temp tree, run in its own process), never a restated expectation:

  * scan_many() == N independent bt.scan() calls, per overlay, on REAL history slices (FTMO feed) for ICT and
    WYCKOFF-BOOK, over overlays that exercise every V key, the F keys, both analysis groups, the htf gate and B3;
    compared as `==` AND as `repr` (types, key order, float text);
  * the same under a forced multi-chunk decomposition, and with 4 real worker processes vs 1 (worker-count
    independence: workers=1 and workers=4 return identical outputs);
  * the analyze-affecting-key registry (`ict-scan.ANALYZE_OPT_KEYS`) equals what analyze() actually reads -- derived from
    its source with `ast`, and by perturbing every registered fx_ key against real windows -- so an overlay can never be
    handed another overlay's analysis; the Wyckoff detection-key registry is checked the same way;
  * the pivot precomputation (`wyckoff_rules.pivot_index/window_pivots`), the rewritten `swings()` and the
    `_wyckoff_candidates(pivots=)` hook equal BASE's per-window detection on real windows and on random tie-heavy data;
  * fund-search: the two-wave prefetch requests exactly what the evaluation later asks for, changes no result and no N.

Real data: data/history/ftmo (tracked in this repo). Slices are written to a temp history root and selected with
BT_HISTORY_ROOT, so nothing outside the temp dir is written. Run from scripts/tests, one module per invocation:
  PYTHONPATH=.. python3 -B -W ignore -m unittest test_speed_equivalence
"""
import ast
import collections
import contextlib
import importlib.util
import json
import os
import pickle
import random
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

BASE = "fef6d6b"
FTMO = os.path.join(ROOT, "data", "history", "ftmo")
TFS = ("1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W")


def _have_data():
    return os.path.isdir(os.path.join(FTMO, "ohlcv.US500.5m")) and os.path.isdir(os.path.join(FTMO, "ohlcv.XAUUSD.15m"))


def _git_ok():
    try:
        subprocess.check_output(["git", "cat-file", "-e", BASE + "^{commit}"], cwd=ROOT, stderr=subprocess.STDOUT)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def write_slice_root(out_root, sym, tf, n_bars, end="2024-03-01T00:00:00Z"):
    """A temp history root holding `sym` on every timeframe, cut to the time span of the LAST `n_bars` bars of `tf`
    before `end` (single-file docs, same fields as the split originals). Returns (start, end) of the span."""
    import history_store as HS
    doc, _ = HS.read_doc(sym, tf, root=FTMO)
    cs = [c for c in doc["candles"] if c["time"] < end][-n_bars:]
    start, stop = cs[0]["time"], cs[-1]["time"]
    os.makedirs(out_root, exist_ok=True)
    for t in TFS:
        d, _ = HS.read_doc(sym, t, root=FTMO)
        if d is None:
            continue
        sub = dict((k, v) for k, v in d.items() if k not in ("candles", "years"))
        sub["candles"] = [c for c in d["candles"] if start <= c["time"] <= stop]
        with open(os.path.join(out_root, f"ohlcv.{sym}.{t}.json"), "w", encoding="utf-8") as fh:
            json.dump(sub, fh)
    return start, stop


REF_SCRIPT = textwrap.dedent('''
    import os, pickle, sys, importlib.util
    root, hist, sym, tf, method, ov_path, out_path = sys.argv[1:8]
    os.environ["BT_HISTORY_ROOT"] = hist
    sys.path.insert(0, os.path.join(root, "scripts"))
    os.chdir(os.path.join(root, "scripts"))
    spec = importlib.util.spec_from_file_location("bt", os.path.join(root, "scripts", "backtest-methods.py"))
    bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
    overlays = pickle.load(open(ov_path, "rb"))
    res = [bt.scan(sym, tf, only=(method,), opts=o) for o in overlays]
    pickle.dump([None if r is None else dict(symbol=r["symbol"], tf=r["tf"], bars=r["bars"], first=r["first"], last=r["last"],
                                             trades=dict(r["trades"])) for r in res], open(out_path, "wb"))
''')


class BaseSnapshot:
    """scripts/ + the configuration they read, as of BASE, in a temp dir; `run()` executes BASE's bt.scan in a child."""
    _dir = None

    @classmethod
    def get(cls):
        if cls._dir is None:
            d = tempfile.mkdtemp(prefix="speed-base-")
            tar = subprocess.Popen(["git", "archive", BASE, "scripts", "docs/architecture", "knowledge", "config", "integrations"],
                                   cwd=ROOT, stdout=subprocess.PIPE)
            subprocess.check_call(["tar", "-x", "-C", d], stdin=tar.stdout)
            tar.wait()
            os.symlink(os.path.join(ROOT, "data"), os.path.join(d, "data"))
            with open(os.path.join(d, "ref.py"), "w") as fh:
                fh.write(REF_SCRIPT)
            cls._dir = d
        return cls._dir

    @classmethod
    def run(cls, hist_root, sym, tf, method, overlays):
        d = cls.get()
        ov, out = os.path.join(d, "ov.pkl"), os.path.join(d, "out.pkl")
        with open(ov, "wb") as fh:
            pickle.dump(overlays, fh)
        subprocess.check_call([sys.executable, "-B", "-W", "ignore", os.path.join(d, "ref.py"), d, hist_root, sym, tf,
                               method, ov, out], stdout=subprocess.DEVNULL)
        with open(out, "rb") as fh:
            return pickle.load(fh)

    @classmethod
    def cleanup(cls):
        if cls._dir:
            shutil.rmtree(cls._dir, ignore_errors=True)
            cls._dir = None


def _fixed():
    import real_costs as RC
    return {"flat_before_rollover": True, "rollover_provider": RC.PROFILES["ftmo_demo_2026_09"]["provider"]}


def ict_overlays():
    fx = _fixed()
    vs = [dict(), dict(fx_b_ex="ce"), dict(fx_b_pd="r13"), dict(fx_b_pool="on"), dict(fx_b_buf="0.1atr"),
          dict(fx_b_exit="-2.25|1.5H|floor"), dict(fx_b_lb="8|2K"), dict(fx_b6="yes"), dict(fx_b3="tfa_p5"),
          dict(fx_b7="killzone"), dict(fx_braid_optional=True, fx_b2a_fvg_in_leg=True),
          dict(fx_b2b_ce_fail=True), dict(fx_b1_pivot1=True), dict(htf=True), dict(fx_b_pool="on", fx_b_ex="fill"),
          dict(mgmt="be"), dict(sides=("long",)), dict(fx_b_exit="-2.5|none|no_floor")]
    return [dict(v, **fx) for v in vs]


def wy_overlays():
    fx = _fixed()
    vs = [dict(), dict(fx_w_stop="spring_low"), dict(fx_w4a_linger_closes=2), dict(fx_w6_window=600),
          dict(fx_w_spt="ceiling"), dict(fx_w_touch="on"), dict(fx_w_tw=(8, 2)), dict(fx_w_spt="VAH"),
          dict(fx_w1_tr_low_st=True), dict(fx_w3_mSOW_spring=True), dict(fx_w7_htf_target=True), dict(htf=True),
          dict(sides=("short",)), dict(st_gate=True, phase_b_gate=True), dict(fx_w_tw=(8, 2), fx_w_stop="spring_low"),
          dict(entry="test", phase_d=False)]
    return [dict(v, **fx) for v in vs]


def _reprs(trades_by_overlay):
    return [repr(sorted((k, v) for k, v in t.items())) for t in trades_by_overlay]


class _DiffMixin:
    """Shared: a temp history slice, BASE's reference output computed once, the current tree's bt loaded on the
    same slice."""
    SYM = TF = METHOD = None
    BARS = 0
    overlays = None
    tmp = ref = bt = SM = None

    @classmethod
    def setUpClass(cls):
        if not _have_data():
            raise unittest.SkipTest("data/history/ftmo is not present")
        if not _git_ok():
            raise unittest.SkipTest(f"git object {BASE} is not reachable")
        cls.tmp = tempfile.mkdtemp(prefix="speed-slice-")
        cls.hist = os.path.join(cls.tmp, "hist")
        write_slice_root(cls.hist, cls.SYM, cls.TF, cls.BARS)
        cls.ov = cls.overlays()
        cls.ref = BaseSnapshot.run(cls.hist, cls.SYM, cls.TF, cls.METHOD, cls.ov)
        cls._env = os.environ.get("BT_HISTORY_ROOT")
        os.environ["BT_HISTORY_ROOT"] = cls.hist
        cls.bt = _load_module("bt_speed_cur", os.path.join(SCRIPTS, "backtest-methods.py"))
        import scan_many as SM
        cls.SM = SM

    @classmethod
    def tearDownClass(cls):
        if cls._env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls._env
        shutil.rmtree(cls.tmp, ignore_errors=True)
        BaseSnapshot.cleanup()

    def _check(self, got):
        self.assertEqual(len(got), len(self.ref))
        for i, (g, r) in enumerate(zip(got, self.ref)):
            ctx = f"overlay #{i} {self.ov[i]}"
            self.assertEqual((g["symbol"], g["tf"], g["bars"], g["first"], g["last"]),
                             (r["symbol"], r["tf"], r["bars"], r["first"], r["last"]), ctx)
            gt, rt = dict(g["trades"]), r["trades"]
            self.assertEqual(gt, rt, ctx)                                   # same list, fields, order
            self.assertEqual(repr(sorted(gt.items())), repr(sorted(rt.items())), ctx)   # same types / float text

    def test_reference_is_not_vacuous(self):
        counts = [len(r["trades"].get(self.METHOD, [])) for r in self.ref]
        self.assertGreater(sum(counts), 10, f"too few reference trades to prove anything: {counts}")
        self.assertGreater(len(set(_reprs([r["trades"] for r in self.ref]))), 3, "overlays should differ")

    def test_scan_many_equals_n_independent_scans_of_the_old_engine(self):
        self._check(self.SM.scan_many(self.bt, self.SYM, self.TF, self.METHOD, self.ov, workers=1))

    def test_bar_chunking_changes_nothing(self):
        for chunks in (3, 7):
            with self.subTest(chunks=chunks):
                self._check(self.SM.scan_many(self.bt, self.SYM, self.TF, self.METHOD, self.ov, workers=1,
                                              chunks=chunks, min_chunk_bars=200))

    def test_worker_count_independence(self):
        """workers=1 (in-process) and workers=4 (four real spawned processes) give identical outputs, and both equal
        the old engine's."""
        one = self.SM.scan_many(self.bt, self.SYM, self.TF, self.METHOD, self.ov, workers=1)
        four = self.SM.scan_many(self.bt, self.SYM, self.TF, self.METHOD, self.ov, workers=4, min_chunk_bars=200)
        self.assertEqual([repr(sorted(dict(r["trades"]).items())) for r in one],
                         [repr(sorted(dict(r["trades"]).items())) for r in four])
        self._check(four)

    def test_overlay_order_does_not_matter(self):
        rev = self.SM.scan_many(self.bt, self.SYM, self.TF, self.METHOD, list(reversed(self.ov)), workers=1)
        self._check(list(reversed(rev)))


class IctDifferential(_DiffMixin, unittest.TestCase):
    SYM, TF, METHOD, BARS = "US500", "5m", "ICT", 7000
    overlays = staticmethod(ict_overlays)


class WyckoffDifferential(_DiffMixin, unittest.TestCase):
    SYM, TF, METHOD, BARS = "XAUUSD", "15m", "WYCKOFF-BOOK", 30000
    overlays = staticmethod(wy_overlays)


class FallbackAndValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_data():
            raise unittest.SkipTest("data/history/ftmo is not present")
        cls.tmp = tempfile.mkdtemp(prefix="speed-slice-")
        cls.hist = os.path.join(cls.tmp, "hist")
        write_slice_root(cls.hist, "XAUUSD", "15m", 6000)
        cls._env = os.environ.get("BT_HISTORY_ROOT")
        os.environ["BT_HISTORY_ROOT"] = cls.hist
        cls.bt = _load_module("bt_speed_cur2", os.path.join(SCRIPTS, "backtest-methods.py"))
        import scan_many as SM
        cls.SM = SM

    @classmethod
    def tearDownClass(cls):
        if cls._env is None:
            os.environ.pop("BT_HISTORY_ROOT", None)
        else:
            os.environ["BT_HISTORY_ROOT"] = cls._env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_combined_book_falls_back_to_plain_scans(self):
        ov = [dict(), dict(fx_w_stop="spring_low")]
        got = self.SM.scan_many(self.bt, "XAUUSD", "15m", "COMBINED-BOOK", ov)
        want = [self.bt.scan("XAUUSD", "15m", only=("COMBINED-BOOK",), opts=o) for o in ov]
        self.assertEqual([dict(g["trades"]) for g in got], [dict(w["trades"]) for w in want])

    def test_unknown_history_gives_none_per_overlay(self):
        self.assertEqual(self.SM.scan_many(self.bt, "NOSUCH", "15m", "ICT", [{}, {"fx_b6": "yes"}]), [None, None])

    def test_a_bad_overlay_is_refused_before_any_scan_exactly_as_scan_refuses_it(self):
        for method, bad in (("ICT", {"fx_not_a_key": 1}), ("ICT", {"fx_b_ex": "typo"}), ("WYCKOFF-BOOK", {"fx_w_stop": "typo"}),
                            ("WYCKOFF-BOOK", {"fx_w6_window": 10 ** 9})):
            with self.subTest(method=method, bad=bad):
                with self.assertRaises(ValueError) as a:
                    self.bt.scan("XAUUSD", "15m", only=(method,), opts=bad)
                with self.assertRaises(ValueError) as b:
                    self.SM.scan_many(self.bt, "XAUUSD", "15m", method, [{}, bad])
                self.assertEqual(str(a.exception), str(b.exception))

    def test_module_opts_are_left_as_found(self):
        before = dict(self.bt.OPTS)
        self.SM.scan_many(self.bt, "XAUUSD", "15m", "WYCKOFF-BOOK", [{}, {"fx_w_spt": "ceiling"}])
        self.assertEqual(before, self.bt.OPTS)

    def test_memory_clamp(self):
        SM = self.SM
        gib = 2 ** 30
        self.assertEqual(SM.clamp_workers(10, 1000, physical=64 * gib), 10)
        self.assertEqual(SM.clamp_workers(1, 10 ** 9, physical=64 * gib), 1)                 # 1 stays 1 (in-process)
        four_m = 4_100_000                      # XAUUSD 1m, development span
        est = SM.worker_memory_estimate(four_m)
        self.assertGreater(est, 3 * gib)
        self.assertLess(est, 4 * gib)
        # the parent process holds the series too, so it counts as one more `est`
        self.assertEqual(SM.clamp_workers(10, four_m, physical=38 * gib), int(38 * gib * 0.6 // est) - 1)
        self.assertEqual(SM.clamp_workers(10, four_m, physical=1 * gib), 1)                  # never below one
        self.assertEqual(SM.clamp_workers(10, four_m, physical=0), 10)                       # unknown RAM: no clamp, no guess
        # the estimate is an upper bound of what was measured on the real series (docs/audits/2026-09-30-...)
        for bars, measured_mib in ((453_893, 346), (1_316_783, 971), (4_096_182, 3045)):
            self.assertGreaterEqual(SM.worker_memory_estimate(bars) / 2 ** 20, measured_mib)


# ------------------------------------------------------------------------------------------------------ registry
def _analyze_read_keys(tree):
    """Every string key analyze() reads from `opts` (opts.get("k"...) / opts["k"]), and whether `opts` is handed on."""
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "analyze")
    reads, handed_on = set(), []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "opts" and node.args \
                and isinstance(node.args[0], ast.Constant):
            reads.add(node.args[0].value)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "opts" \
                and isinstance(node.slice, ast.Constant):
            reads.add(node.slice.value)
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            for a in list(node.args) + [k.value for k in node.keywords]:
                if isinstance(a, ast.Name) and a.id == "opts":
                    handed_on.append(ast.dump(node.func))
    return reads, handed_on


class AnalyzeKeyRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(os.path.join(SCRIPTS, "ict-scan.py"), encoding="utf-8").read()
        cls.ict = _load_module("ict_scan_reg", os.path.join(SCRIPTS, "ict-scan.py"))

    def test_registry_equals_what_analyze_reads_from_its_source(self):
        reads, handed_on = _analyze_read_keys(ast.parse(self.src))
        self.assertEqual(set(self.ict.ANALYZE_OPT_KEYS), reads,
                         "ict-scan.ANALYZE_OPT_KEYS must list exactly the opts keys analyze() reads -- scan_many shares "
                         "one analysis between overlays that agree on them")
        self.assertEqual(handed_on, [], "analyze() passes `opts` on to another callable: the registry would need to "
                                        "cover what that callable reads too -- extend this test and the registry")

    def test_structures_ict_analysis_is_a_pure_pass_through(self):
        tree = ast.parse(open(os.path.join(SCRIPTS, "structures.py"), encoding="utf-8").read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ict_analysis")
        body = [n for n in fn.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        self.assertEqual(len(body), 1)
        call = body[0].value
        self.assertEqual(ast.unparse(call), "ict_scan.analyze(window, recent, tf=tf, methods=methods, opts=opts)")

    def test_every_registered_fx_key_is_classified_and_the_registry_is_behaviourally_exact(self):
        """Perturb EVERY key of the engine's overlay against real windows: analyze()'s output may change only for a key
        in ANALYZE_OPT_KEYS, and each listed key must change it somewhere (a listed key that does nothing would only
        cost sharing, but a test that cannot tell is not a test)."""
        if not _have_data():
            self.skipTest("data/history/ftmo is not present")
        tmp = tempfile.mkdtemp(prefix="speed-slice-")
        env = os.environ.get("BT_HISTORY_ROOT")
        try:
            hist = os.path.join(tmp, "hist")
            write_slice_root(hist, "US500", "5m", 5200)
            os.environ["BT_HISTORY_ROOT"] = hist
            bt = _load_module("bt_speed_reg", os.path.join(SCRIPTS, "backtest-methods.py"))
            c, _ = bt.load("US500", "5m")
            bars, recent = bt.lr.scan_spec("5m")
            windows = [c[i - bars + 1:i + 1] for i in range(bars - 1, len(c), 47)]
            methods = ("wyckoff", "ict")
            fx_keys = sorted(k for k in bt._OPTS_BASE if k.startswith("fx_"))
            alternatives = {k: [] for k in fx_keys}
            for k in fx_keys:
                base = bt._OPTS_BASE[k]
                if k in self.ict.V_ICT:
                    alternatives[k] = [v for v in self.ict.V_ICT[k] if v != base]
                elif isinstance(base, bool):
                    alternatives[k] = [not base]
                elif k in bt.WY_V_VALUES:
                    alternatives[k] = [v for v in bt.WY_V_VALUES[k] if v != base]
                else:
                    alternatives[k] = [True]
            base_out = [self.ict.analyze(w, recent, tf="5m", methods=methods, opts={}) for w in windows]
            changed = set()
            for k in fx_keys:
                for alt in alternatives[k]:
                    outs = [self.ict.analyze(w, recent, tf="5m", methods=methods, opts={k: alt}) for w in windows]
                    if outs != base_out:
                        changed.add(k)
            self.assertEqual(changed, set(self.ict.ANALYZE_OPT_KEYS),
                             "the fx_ keys that change analyze()'s output must be exactly ict-scan.ANALYZE_OPT_KEYS")
            # and the engine hands analyze() a superset overlay: extra keys must be inert
            noisy = {k: alternatives[k][0] for k in fx_keys if alternatives[k] and k not in self.ict.ANALYZE_OPT_KEYS}
            self.assertEqual([self.ict.analyze(w, recent, tf="5m", methods=methods, opts=noisy) for w in windows], base_out)
        finally:
            if env is None:
                os.environ.pop("BT_HISTORY_ROOT", None)
            else:
                os.environ["BT_HISTORY_ROOT"] = env
            shutil.rmtree(tmp, ignore_errors=True)


class WyckoffDetectionKeyRegistry(unittest.TestCase):
    """`_wy_detection_ck()` (the two registries `_FX_WYCKOFF_DETECTION_KEYS` + `_FX_WYCKOFF_V_DETECTION_KEYS`) must cover
    every OPTS key that changes what `_wyckoff_candidates` detects: scan_many groups overlays on it."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(os.path.join(SCRIPTS, "backtest-methods.py"), encoding="utf-8").read()

    def test_the_detection_path_reads_only_registered_keys_from_its_source(self):
        tree = ast.parse(self.src)
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        read = set()
        for name in ("_tw", "_fx_v_detection_opts", "_fx_detection_opts", "_wy_params"):
            for node in ast.walk(fns[name]):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "OPTS" and node.args \
                        and isinstance(node.args[0], ast.Constant):
                    read.add(node.args[0].value)
        # `_fx_detection_opts` reads its keys through the tuple constant (`OPTS.get(k, False) for k in _FX_...`)
        read |= set(_literal_tuple(tree, "_FX_WYCKOFF_DETECTION_KEYS"))
        registered = set(_literal_tuple(tree, "_FX_WYCKOFF_DETECTION_KEYS")) | set(_literal_tuple(tree, "_FX_WYCKOFF_V_DETECTION_KEYS"))
        self.assertEqual(read, registered)
        names = {n.id for n in ast.walk(fns["_wyckoff_candidates"]) if isinstance(n, ast.Name)}
        self.assertNotIn("OPTS", names, "_wyckoff_candidates reads OPTS directly: scan_many's detection grouping would miss it")

    def test_perturbing_every_key_changes_detection_only_for_registered_ones(self):
        if not _have_data():
            self.skipTest("data/history/ftmo is not present")
        tmp = tempfile.mkdtemp(prefix="speed-slice-")
        env = os.environ.get("BT_HISTORY_ROOT")
        try:
            hist = os.path.join(tmp, "hist")
            write_slice_root(hist, "XAUUSD", "15m", 9000)
            os.environ["BT_HISTORY_ROOT"] = hist
            bt = _load_module("bt_speed_wreg", os.path.join(SCRIPTS, "backtest-methods.py"))
            c, _ = bt.load("XAUUSD", "15m")
            O = [x["open"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]
            C = [x["close"] for x in c]; V = [x.get("volume", 0) for x in c]
            wins = [(a, a + 300) for a in range(0, len(c) - 300, 37)]

            def detect(opts):
                bt.OPTS = dict(bt._OPTS_BASE, **opts)
                try:
                    wp = bt._wy_params(bt.P["15m"]["sob"])
                    return [bt._structures.wyckoff_records(O[a:b], H[a:b], L[a:b], C[a:b], V[a:b], P=wp,
                                                           volume_kind="tick", side=s)
                            for a, b in wins for s in ("long", "short")]
                finally:
                    bt.OPTS = dict(bt._OPTS_BASE)
            base = detect({})
            self.assertGreater(sum(len(x) for x in base), 30, "no structure in the sample: vacuous")
            registered = set(bt._FX_WYCKOFF_DETECTION_KEYS) | set(bt._FX_WYCKOFF_V_DETECTION_KEYS)
            changed = set()
            for k, v in bt._OPTS_BASE.items():
                if k in bt.FX_ICT_KEYS or k in bt.FX_ICT_V_KEYS or k in ("min_rr", "rollover_provider", "methods"):
                    continue
                if k in bt.WY_V_VALUES:
                    alts = [a for a in bt.WY_V_VALUES[k] if a != (v if k != "fx_w_tw" else (12, 2))]
                elif isinstance(v, bool):
                    alts = [not v]
                else:
                    continue
                for alt in alts:
                    if detect({k: alt}) != base:
                        changed.add(k)
            self.assertLessEqual(changed, registered, f"keys that change Wyckoff detection but are not registered: {changed - registered}")
            self.assertTrue({"fx_w_tw", "fx_w4a_linger_closes"} & changed, "the perturbation never reached detection: vacuous")
        finally:
            if env is None:
                os.environ.pop("BT_HISTORY_ROOT", None)
            else:
                os.environ["BT_HISTORY_ROOT"] = env
            shutil.rmtree(tmp, ignore_errors=True)


def _literal_tuple(tree, name):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return tuple(ast.literal_eval(n.value))
    raise AssertionError(name)


# ------------------------------------------------------------------------------------------------- pivot precompute
class PivotPrecomputeEqualsBase(unittest.TestCase):
    """wyckoff_rules.swings / pivot_index / window_pivots and the `pivots=` hook of `_wyckoff_candidates` against BASE's
    per-window detection."""

    @classmethod
    def setUpClass(cls):
        if not _git_ok():
            raise unittest.SkipTest(f"git object {BASE} is not reachable")
        import wyckoff_rules as W
        cls.W = W
        src = subprocess.check_output(["git", "show", f"{BASE}:scripts/wyckoff_rules.py"], cwd=ROOT, text=True)
        import types
        cls.B = types.ModuleType("wyckoff_rules_base")
        cls.B.__file__ = os.path.join(SCRIPTS, "wyckoff_rules.py")
        exec(compile(src, cls.B.__file__, "exec"), cls.B.__dict__)

    def test_swings_random_tie_heavy_series(self):
        rng = random.Random(11)
        W, B = self.W, self.B
        for _ in range(1500):
            n = rng.randint(8, 70)
            H = [round(100 + rng.random() * 4, 1) for _ in range(n)]
            L = [round(h - rng.random() * 2, 1) for h in H]
            for k in (1, 2, 3):
                self.assertEqual(W.swings(H, L, k), B.swings(H, L, k))
                idx = W.pivot_index(H, L, k)
                a = rng.randint(0, max(0, n - (2 * k + 1)) // 2)
                m = rng.randint(2 * k + 1, n - a)
                self.assertEqual(W.swings(H[a:a + m], L[a:a + m], k, pivots=W.window_pivots(idx, a, m, k)),
                                 B.swings(H[a:a + m], L[a:a + m], k))
                Hi = [-x for x in L[a:a + m]]
                Li = [-x for x in H[a:a + m]]
                self.assertEqual(W.swings(Hi, Li, k, pivots=W.window_pivots(idx, a, m, k, swap=True)), B.swings(Hi, Li, k))

    def test_detection_on_random_walks_matches_base(self):
        """Random walks make many swings and many downtrend-before-SC candidates: the branches a smooth real window seldom
        reaches (the lows/highs bookkeeping of detect_accumulations, both mirror sides, the pivot hook)."""
        W, B = self.W, self.B
        rng = random.Random(29)
        k = W.PARAMS["pivot"]
        n_rec = 0
        for trial in range(160):
            m = rng.choice([120, 300, 300, 450])
            drift = rng.choice([-0.05, -0.02, 0.0, 0.03])
            px, O, H, L, C, V = 100.0, [], [], [], [], []
            for i in range(m):
                o = px
                c = round(px + drift + rng.gauss(0, 0.6), 2)
                O.append(o); C.append(c)
                H.append(round(max(o, c) + abs(rng.gauss(0, 0.3)), 2)); L.append(round(min(o, c) - abs(rng.gauss(0, 0.3)), 2))
                V.append(round(abs(rng.gauss(1000, 400)), 1))
                px = c
            idx = W.pivot_index(H, L, k)
            for kind in ("traded", "tick"):
                ref_a = B.detect_accumulations(O, H, L, C, V, volume_kind=kind)
                self.assertEqual(W.detect_accumulations(O, H, L, C, V, volume_kind=kind), ref_a)
                self.assertEqual(W.detect_accumulations(O, H, L, C, V, volume_kind=kind, pivots=W.window_pivots(idx, 0, m, k)), ref_a)
                ref_d = B.detect_distributions(O, H, L, C, V, volume_kind=kind)
                self.assertEqual(W.detect_distributions(O, H, L, C, V, volume_kind=kind), ref_d)
                self.assertEqual(W.detect_distributions(O, H, L, C, V, volume_kind=kind, pivots=W.window_pivots(idx, 0, m, k, swap=True)), ref_d)
                n_rec += len(ref_a) + len(ref_d)
        self.assertGreater(n_rec, 30, "random walks produced no structure: vacuous")

    def test_detection_on_real_windows_matches_base_with_and_without_the_hook(self):
        if not _have_data():
            self.skipTest("data/history/ftmo is not present")
        import history_store as HS
        doc, _ = HS.read_doc("XAUUSD", "15m", root=FTMO)
        cs = [c for c in doc["candles"] if c["time"] < "2024-03-01T00:00:00Z"][-12000:]
        O = [x["open"] for x in cs]; H = [x["high"] for x in cs]; L = [x["low"] for x in cs]
        C = [x["close"] for x in cs]; V = [x.get("volume", 0) for x in cs]
        W, B = self.W, self.B
        k = W.PARAMS["pivot"]
        idx = W.pivot_index(H, L, k)
        n_rec = 0
        for a in range(0, len(cs) - 300, 43):
            s = slice(a, a + 300)
            for side in ("long", "short"):
                if side == "long":
                    ref = B.detect_accumulations(O[s], H[s], L[s], C[s], V[s], volume_kind="tick")
                    got = W.detect_accumulations(O[s], H[s], L[s], C[s], V[s], volume_kind="tick")
                    hook = W.detect_accumulations(O[s], H[s], L[s], C[s], V[s], volume_kind="tick",
                                                  pivots=W.window_pivots(idx, a, 300, k))
                else:
                    ref = B.detect_distributions(O[s], H[s], L[s], C[s], V[s], volume_kind="tick")
                    got = W.detect_distributions(O[s], H[s], L[s], C[s], V[s], volume_kind="tick")
                    hook = W.detect_distributions(O[s], H[s], L[s], C[s], V[s], volume_kind="tick",
                                                  pivots=W.window_pivots(idx, a, 300, k, swap=True))
                self.assertEqual(got, ref)
                self.assertEqual(hook, ref)
                n_rec += len(ref)
        self.assertGreater(n_rec, 20, "no Wyckoff structure in the sample: the comparison would be vacuous")


class AnalyzeAndSetupCandidateEqualBase(unittest.TestCase):
    """ict-scan.analyze() / setup_candidate() against BASE's, window by window, on real history and on tie-heavy
    synthetic bars: the micro-optimisations inside them (early-exit pivot tests, per-kind sweep scans, sorted pool
    dedupe, per-type FVG mitigation scan, no per-bar dict for the day table, lazy column lists) change no output."""

    @classmethod
    def setUpClass(cls):
        if not _git_ok():
            raise unittest.SkipTest(f"git object {BASE} is not reachable")
        import types
        cls.new = _load_module("ict_scan_new", os.path.join(SCRIPTS, "ict-scan.py"))
        src = subprocess.check_output(["git", "show", f"{BASE}:scripts/ict-scan.py"], cwd=ROOT, text=True)
        cls.old = types.ModuleType("ict_scan_base")
        cls.old.__file__ = os.path.join(SCRIPTS, "ict-scan.py")
        exec(compile(src, cls.old.__file__, "exec"), cls.old.__dict__)

    OPTS = ({}, {"fx_b1_pivot1": True}, {"fx_b2b_ce_fail": True}, {"fx_b_pool": "on"},
            {"fx_b1_pivot1": True, "fx_b2b_ce_fail": True, "fx_b_pool": "on"})
    SU_OPTS = ({}, {"fx_braid_optional": True}, {"fx_b2a_fvg_in_leg": True, "fx_b2b_ce_fail": True},
               {"fx_b_ex": "ce", "fx_b_pd": "r13", "fx_b_buf": "0.1atr", "fx_b_exit": "-2.25|1.5H|floor"},
               {"fx_b_ex": "fill", "fx_b_buf": "0.25atr", "fx_braid_optional": True})

    def _compare(self, c, recent, tf, n_windows_hint):
        import copy
        n_complete = 0
        for methods in (("wyckoff", "ict"), ("ict",), ("wyckoff",)):
            for o in self.OPTS:
                a_new = self.new.analyze(c, recent, tf=tf, methods=methods, opts=dict(o))
                a_old = self.old.analyze(c, recent, tf=tf, methods=methods, opts=dict(o))
                self.assertEqual(a_new, a_old, (methods, o))
                self.assertEqual(repr(a_new), repr(a_old), (methods, o))
                if "ict" not in methods:
                    continue
                for so in self.SU_OPTS:
                    o2 = dict(o, **so)
                    a2 = self.new.analyze(c, recent, tf=tf, methods=methods, opts=dict(o2))
                    before = copy.deepcopy(a2)
                    su_new = self.new.setup_candidate(a2, c, max(12, recent * 6), opts=dict(o2))
                    su_old = self.old.setup_candidate(a2, c, max(12, recent * 6), opts=dict(o2))
                    self.assertEqual(su_new, su_old, (methods, o2))
                    self.assertEqual(repr(su_new), repr(su_old), (methods, o2))
                    self.assertEqual(a2, before, "setup_candidate mutated the analysis it was handed: sharing one "
                                                 "analysis between overlays would be unsafe")
                    n_complete += bool(su_new and su_new.get("complete"))
        return n_complete

    def test_real_windows(self):
        if not _have_data():
            self.skipTest("data/history/ftmo is not present")
        import history_store as HS
        complete = 0
        for sym, tf, bars, recent, count in (("US500", "5m", 576, 4, 110), ("XAUUSD", "15m", 576, 2, 110),
                                             ("US30", "1m", 360, 4, 60), ("XAGUSD", "30m", 480, 2, 60)):
            doc, _ = HS.read_doc(sym, tf, root=FTMO)
            cs = [c for c in doc["candles"] if c["time"] < "2024-03-01T00:00:00Z"][-9000:]
            for i in range(bars - 1, len(cs), (len(cs) - bars) // count):
                complete += self._compare(cs[i - bars + 1:i + 1], recent, tf, count)
        self.assertGreater(complete, 5, "no complete setup among the sampled windows: the setup_candidate check is vacuous")

    def test_tie_heavy_synthetic_windows_and_tiny_windows(self):
        rng = random.Random(5)
        for trial in range(40):
            n = rng.choice([3, 5, 9, 17, 40, 120, 300])
            px, cs = 100.0, []
            for i in range(n):
                o = round(px + rng.choice([-0.2, -0.1, 0, 0.1, 0.2]), 1)
                h = round(max(o, px) + rng.choice([0, 0.1, 0.1, 0.3]), 1)
                l = round(min(o, px) - rng.choice([0, 0.1, 0.1, 0.3]), 1)
                cl = round(rng.uniform(l, h), 1)
                cs.append({"time": f"2024-01-{1 + i // 96:02d}T{(i % 96) // 4:02d}:{(i % 4) * 15:02d}:00Z", "open": o,
                           "high": h, "low": l, "close": cl, "volume": rng.choice([0, 10, 10, 55])})
                px = cl
            self._compare(cs, 2, "15m", 1)


# ------------------------------------------------------------------------------------------------ fund-search waves
class FundSearchWaves(unittest.TestCase):
    """The two-wave prefetch: requests exactly what the evaluation later asks for, and changes no result / no N."""

    @classmethod
    def setUpClass(cls):
        cls.fs = _load_module("fund_search_speed", os.path.join(SCRIPTS, "fund-search.py"))
        import fund_stats as FS
        cls.FS = FS

    def _grid(self):
        return self.FS.Grid({"method": "ICT", "items": [
            {"id": "a", "key": "fx_a", "values": ["x", "y", "z"], "implemented": True},
            {"id": "b", "key": "fx_b", "values": [0, 1, 2], "implemented": True},
            {"id": "c", "key": "fx_c1", "joint_group": "jc", "values": [False, True], "implemented": True},
            {"id": "d", "key": "fx_c2", "joint_group": "jc", "values": ["p", "q"], "implemented": True}]})

    def _cell(self):
        return {"id": "t", "timeframe": "5m", "symbols": ["XAUUSD", "US500"], "development_start": "2018-01-01T00:00:00Z"}

    def _trades(self, values):
        rng = random.Random(json.dumps(values, sort_keys=True))
        import datetime
        t0 = datetime.datetime(2018, 1, 1, tzinfo=datetime.timezone.utc)
        out = []
        for i in range(700):
            t = t0 + datetime.timedelta(hours=i * 90 + rng.randint(0, 40))
            if t >= datetime.datetime(2024, 3, 1, tzinfo=datetime.timezone.utc):
                break
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            out.append({"symbol": ("XAUUSD", "US500")[i % 2], "entry_time": ts, "exit_time": ts, "net_R": rng.gauss(0.05, 1.0),
                        "R": rng.gauss(0.05, 1.0), "adx14": 20.0, "volume_kind": "tick", "side": "long"})
        return out

    def _engine_cls(self, prefetching):
        outer = self

        class Eng:
            def __init__(self):
                self.calls, self.scans, self._held = [], [], {}
                self._pre = set()

            def trades_for(self, values):
                key = outer.FS.CountingSource._key(values)
                self.calls.append(key)
                if key not in self._pre:
                    self.scans.append(key)          # a value set scanned on demand, not prefetched
                return outer._trades(values)

            def prop_pass(self, pooled):
                return {"ftmo": {"value": 0.9}, "the5ers": {"value": 0.9}}

            def has(self, values):
                return outer.FS.CountingSource._key(values) in self._pre

            def prefetch(self, values_list):
                self.waves = getattr(self, "waves", []) + [[outer.FS.CountingSource._key(v) for v in values_list]]
                self._pre |= {outer.FS.CountingSource._key(v) for v in values_list}

        if not prefetching:
            del Eng.has, Eng.prefetch
        return Eng

    def test_waves_cover_every_request_and_change_neither_result_nor_n(self):
        fs, FS = self.fs, self.FS
        grid, cell = self._grid(), self._cell()
        plain = self._engine_cls(False)()
        res_plain = fs.evaluate_with_engine(plain, grid, cell, 205)
        wav = self._engine_cls(True)()
        res_waves = fs.evaluate_with_engine(wav, grid, cell, 205)
        self.assertEqual(json.dumps(res_plain, sort_keys=True, default=repr), json.dumps(res_waves, sort_keys=True, default=repr))
        self.assertEqual(res_plain["runs_evaluated"], res_waves["runs_evaluated"])      # N accounting unchanged
        self.assertGreater(res_waves["runs_evaluated"], 1 + sum(len(g["candidates"]) for g in grid.groups))
        self.assertEqual(wav.scans, [], "a value set the evaluation asked for was not prefetched by either wave")
        # every prefetched set was really requested later (nothing was scanned that N would not count)
        self.assertLessEqual(set(k for w in wav.waves for k in w), set(wav.calls))
        # wave 1 = baseline + every single-factor candidate, exactly; wave 2 = the rest, disjoint from wave 1
        w1, w2 = wav.waves
        expect = {FS.CountingSource._key(grid.baseline())} | {FS.CountingSource._key(grid.full(c))
                                                              for g in grid.groups for c in g["candidates"]}
        self.assertEqual(set(w1), expect)
        self.assertEqual(len(w1), len(expect))
        self.assertFalse(set(w1) & set(w2))
        # the order in which the CountingSource first met each set -- what the run's ledger of N follows -- is the
        # order the plain engine saw
        first_use = []
        for k in wav.calls:
            if k not in first_use:
                first_use.append(k)
        plain_first = []
        for k in plain.calls:
            if k not in plain_first:
                plain_first.append(k)
        self.assertEqual(first_use, plain_first)

    def test_probe_never_scores_or_counts(self):
        fs, FS = self.fs, self.FS
        eng = self._engine_cls(True)()
        probe = fs._WaveProbe(eng)
        self.assertEqual(probe({"a": "y", "b": 0, "c": False, "d": "p"}), [])
        self.assertEqual(eng.calls, [])                # nothing was computed
        self.assertEqual(list(probe.missing), [FS.CountingSource._key({"a": "y", "b": 0, "c": False, "d": "p"})])


class BtEngineParity(unittest.TestCase):
    """The REAL BtEngine on real history slices: `prefetch` (scan_many) then `trades_for` returns exactly what
    `trades_for` alone (plain bt.scan) returns -- trades, admission rows and rollover-edge rows -- in-process and with
    a 3-process scan pool."""

    def _parity(self, method_key, runner_method, sym, tf, bars, workers):
        if not _have_data():
            self.skipTest("data/history/ftmo is not present")
        tmp = tempfile.mkdtemp(prefix="speed-slice-")
        env = os.environ.get("BT_HISTORY_ROOT")
        try:
            hist = os.path.join(tmp, "hist")
            write_slice_root(hist, sym, tf, bars)
            os.environ["BT_HISTORY_ROOT"] = hist
            fs = _load_module("fund_search_parity", os.path.join(SCRIPTS, "fund-search.py"))
            grids, _paths = fs.load_grids()
            grid = grids[method_key].runnable()
            sets = [grid.baseline()] + [grid.full(g["candidates"][0]) for g in grid.groups[:4]]
            a = fs.BtEngine(grid, runner_method, tf, [sym], workers=workers)
            a.prefetch(sets)
            self.assertTrue(all(a.has(v) for v in sets))
            b = fs.BtEngine(grid, runner_method, tf, [sym])
            n = 0
            for v in sets:
                ta, tb = a.trades_for(v), b.trades_for(v)
                self.assertEqual(repr(ta), repr(tb), v)
                key = self.FS.CountingSource._key(v)
                self.assertEqual(a._admission[key], b._admission[key])
                self.assertEqual(a._edge[key], b._edge[key])
                n += len(tb)
            return n
        finally:
            if env is None:
                os.environ.pop("BT_HISTORY_ROOT", None)
            else:
                os.environ["BT_HISTORY_ROOT"] = env
            shutil.rmtree(tmp, ignore_errors=True)

    @classmethod
    def setUpClass(cls):
        import fund_stats as FS
        cls.FS = FS

    def test_ict_in_process(self):
        self._parity("ict", "ICT", "US500", "5m", 5000, 1)

    def test_wyckoff_in_process(self):
        self.assertGreater(self._parity("wyckoff", "WYCKOFF-BOOK", "XAUUSD", "15m", 30000, 1), 0)

    def test_ict_with_a_scan_pool(self):
        self._parity("ict", "ICT", "US500", "5m", 5000, 3)

    def test_wyckoff_with_a_scan_pool(self):
        self._parity("wyckoff", "WYCKOFF-BOOK", "XAUUSD", "15m", 30000, 3)


if __name__ == "__main__":
    unittest.main()
