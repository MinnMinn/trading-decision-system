"""scripts/research/edge_c1b.py on the SYNTHETIC history of test_edge_c1 (no real data, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_c1b
(docs/plans/2026-10-04-edge-c1b-post-publication-preregistration.md)
"""
import contextlib
import gzip
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

import test_edge_c1 as T                     # the synthetic history builder and its windows

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_c1b", os.path.join(ROOT, "scripts", "research", "edge_c1b.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
C1 = B.C1


def _patch(roots):
    C1.SPOT_ROOT, C1.UM_ROOT = roots
    C1.symbols = lambda: list(T.SYN)
    C1.WINDOWS = T.SYN_WINDOWS
    C1.N1_SYMBOLS = ("AAAUSDT", "BBBUSDT")
    C1.ELIGIBLE_FROM = dict(T.SYN_ELIGIBLE)
    C1._book_daily = lambda: ({"2021-03-01": 0.5, "2021-03-02": -1.0}, T.pearson)
    T.F.SPOT_ROOT, T.F.UM_ROOT = roots
    T.F.symbols = lambda: list(T.SYN)
    T.F.WINDOWS = T.SYN_WINDOWS
    T.F.N1_SYMBOLS = ("AAAUSDT", "BBBUSDT")
    T.F.ELIGIBLE_FROM = dict(T.SYN_ELIGIBLE)
    T.F._book_daily = C1._book_daily


def _perturb_before(root, t_cut, factor=1.3):
    """Multiply every 5m price strictly before epoch t_cut (spot and perp) and every funding rate before it by `factor`."""
    for base in ("spot", "um"):
        d0 = os.path.join(root, base)
        for name in os.listdir(d0):
            p = os.path.join(d0, name)
            if name.startswith("ohlcv.") and name.endswith(".5m"):
                for part in os.listdir(p):
                    if not part.endswith(".json.gz"):
                        continue
                    fp = os.path.join(p, part)
                    doc = json.load(gzip.open(fp, "rt"))
                    for c in doc["candles"]:
                        if T.F._epoch(c["time"]) < t_cut:
                            for k in ("open", "high", "low", "close"):
                                c[k] *= factor
                    with gzip.open(fp, "wt") as fh:
                        json.dump(doc, fh)
            elif name.startswith("funding") and name.endswith(".json.gz"):
                doc = json.load(gzip.open(p, "rt"))
                for r in doc["rows"]:
                    if T.F._epoch(r["time"]) < t_cut:
                        r["rate"] *= factor
                with gzip.open(p, "wt") as fh:
                    json.dump(doc, fh)


class Rules(unittest.TestCase):
    def test_pass_needs_every_condition(self):
        ok = {"p_one_sided": 0.04}
        self.assertTrue(B.passes(ok, 1e-4, 1e-4, 0.05))
        self.assertFalse(B.passes({"p_one_sided": 0.05}, 1e-4, 1e-4, 0.05))       # strict p < 0.05
        self.assertFalse(B.passes(ok, -1e-6, 1e-4, 0.05))
        self.assertFalse(B.passes(ok, 1e-4, -1e-6, 0.05))
        self.assertFalse(B.passes(ok, 1e-4, 1e-4, 0.11))
        self.assertFalse(B.passes({"p_one_sided": None}, 1e-4, 1e-4, 0.05))
        self.assertFalse(B.passes(ok, 1e-4, 1e-4, None))

    def test_label_wording(self):
        self.assertIn("never read for this hypothesis", B.label(True, False))
        self.assertNotIn("validated", B.label(True, False).lower())
        self.assertIn("C1 closed", B.label(False, False))
        self.assertTrue(B.label(True, True).endswith("regime-driven"))

    def test_shrinkage_and_ci(self):
        self.assertAlmostEqual(B.shrink(0.12, 0.10), 0.06)                     # equal variances: halfway to 0
        self.assertAlmostEqual(B.shrink(0.12, 0.0001), 0.12, places=5)
        lo, hi = B.ci90(0.1, 0.05)
        self.assertAlmostEqual(lo, 0.1 - 1.6448536269514722 * 0.05)
        self.assertAlmostEqual(hi, 0.1 + 1.6448536269514722 * 0.05)
        self.assertIsNone(B.shrink(None, 0.1))


class Read(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edge_c1b_test_")
        cls.saved = {k: getattr(C1, k) for k in ("SPOT_ROOT", "UM_ROOT", "symbols", "WINDOWS", "N1_SYMBOLS", "_book_daily",
                                                 "ELIGIBLE_FROM")}
        cls.saved_t = {k: getattr(T.F, k) for k in cls.saved}
        cls.roots = T.make_history(os.path.join(cls.tmp, "a"))
        _patch(cls.roots)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.b = B.run(os.path.join(cls.tmp, "b.json"), draws=25, require_clean=False)
            out = {r: os.path.join(cls.tmp, f"{r}.json") for r in T.F.READS}
            T.F.run("discovery", out["discovery"], draws=25, require_clean=False)
            T.F.run("confirmation", out["confirmation"], out["discovery"], draws=25, require_clean=False)
            cls.c1 = T.F.run("exposed", out["exposed"], out["confirmation"], draws=25, require_clean=False)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.saved.items():
            setattr(C1, k, v)
        for k, v in cls.saved_t.items():
            setattr(T.F, k, v)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_t1_equals_c1s_own_exposed_read(self):
        a, b = self.b["T1"], self.c1["tests"][0]
        self.assertAlmostEqual(a["regression"]["alpha"], b["regression"]["alpha"], places=12)
        self.assertAlmostEqual(a["regression"]["p_one_sided"], b["regression"]["p_one_sided"], places=12)
        self.assertAlmostEqual(a["net"]["mean"], b["net"]["mean"], places=12)
        self.assertAlmostEqual(a["p_placebo"], b["p_placebo"], places=12)
        self.assertEqual([r["date"] for r in self.b["daily"]], [r["date"] for r in self.c1["daily"]])

    def test_window_is_the_exposed_window_only(self):
        a, b = T.SYN_WINDOWS["exposed"]
        got = [r["date"] for r in self.b["daily"]]
        self.assertEqual((got[0], got[-1], len(got)), (str(a), str(b), (b - a).days + 1))
        self.assertFalse(self.b["meta"]["pre_window_pnl_computed"])

    def test_prices_and_funding_before_the_window_change_nothing(self):
        start = T.SYN_WINDOWS["exposed"][0]
        roots = T.make_history(os.path.join(self.tmp, "p"))
        _perturb_before(os.path.join(self.tmp, "p"), T.F.t_fill(start))
        _patch(roots)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                p = B.run(os.path.join(self.tmp, "p.json"), draws=25, require_clean=False)
        finally:
            _patch(self.roots)
        self.assertEqual(p["T1"]["regression"], self.b["T1"]["regression"])
        self.assertEqual(p["daily"], self.b["daily"])
        self.assertEqual(p["T1"]["p_placebo"], self.b["T1"]["p_placebo"])

    def test_read_once(self):
        with self.assertRaises(SystemExit):
            B.run(os.path.join(self.tmp, "b.json"), draws=25, require_clean=False)

    def test_guard_needs_the_tag(self):
        saved_req, saved_pre = C1._require_committed, B.PREREG
        tmp_pre = os.path.join(self.tmp, "pre.md")
        open(tmp_pre, "w").write("no tag here")
        try:
            C1._require_committed = lambda paths: {}
            B.PREREG = os.path.relpath(tmp_pre, ROOT)
            with self.assertRaises(SystemExit) as cm:
                B._guard()
            self.assertIn("[C1b-P1]", str(cm.exception))
        finally:
            C1._require_committed, B.PREREG = saved_req, saved_pre


if __name__ == "__main__":
    unittest.main()
