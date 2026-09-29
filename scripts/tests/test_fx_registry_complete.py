"""Cross-branch integrity of the fx_ key contract (docs/plans/2026-09-29-execution-plan.md "Shared contract"),
checked on the MERGED tree: every fx_ key in backtest-methods._OPTS_BASE is registered in all four places, the
live runner references none, and the pre-declared V grids (docs/architecture/v-grid-*.json) name only real keys
and reproduce the plan's N (ICT 41, Wyckoff 16 per cell)."""
import importlib.util, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", "") + "_reg",
                                                  os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Registry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py"); cls.sr = load("stability-report.py")
        cls.keys = sorted(k for k in cls.bt._OPTS_BASE if k.startswith("fx_"))

    def test_there_are_fx_keys(self):
        self.assertGreaterEqual(len(self.keys), 20)

    def test_every_fx_key_is_scan_relevant_and_stated_in_config_opts(self):
        overlay = self.sr.config_opts(self.sr.CONFIGS["A"], ict_target="range")
        for k in self.keys:
            self.assertIn(k, self.sr._SCAN_RELEVANT_KEYS, k)
            self.assertIn(k, overlay, k)
            self.assertEqual(overlay[k], self.bt._OPTS_BASE[k], f"{k}: config_opts must state the v1 default")

    def test_every_fx_key_reaches_the_config_snapshot(self):
        """ICT keys reach snapshot.py through bt.FX_ICT_KEYS / bt.FX_ICT_V_KEYS (read off bt at snapshot time); every
        other key must be named in snapshot.py itself."""
        src = open(os.path.join(ROOT, "scripts", "snapshot.py"), encoding="utf-8").read()
        via_bt = set(self.bt.FX_ICT_KEYS) | set(self.bt.FX_ICT_V_KEYS)
        for tup in ("FX_ICT_KEYS", "FX_ICT_V_KEYS"):
            self.assertIn(tup, src)
        for k in self.keys:
            if k not in via_bt:
                self.assertIn(k, src, k)

    def test_live_runner_never_references_an_fx_key(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("fx_", src)


class Grids(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bt = load("backtest-methods.py")
        cls.grids = {m: json.load(open(os.path.join(ROOT, "docs", "architecture", f"v-grid-{m}.json"), encoding="utf-8"))
                     for m in ("ict", "wyckoff")}

    def test_every_implemented_item_names_a_real_engine_key(self):
        for m, g in self.grids.items():
            for it in g["items"]:
                if not it.get("implemented"):
                    continue
                key = it.get("existing_opts_key") or it["key"]
                self.assertIn(key, self.bt._OPTS_BASE, f"{m}:{it['id']} -> {key}")

    def test_unimplemented_items_have_no_engine_key_and_a_reason(self):
        for m, g in self.grids.items():
            for it in g["items"]:
                if it.get("implemented"):
                    continue
                self.assertNotIn(it["key"], self.bt._OPTS_BASE, it["id"])
                self.assertTrue(it.get("reason") or it.get("note"), it["id"])

    def test_declared_n_per_cell_matches_the_plan(self):
        def n(g):
            non_base = 0
            for it in g["items"]:
                vals = it["values"]
                if it["id"] == "W-TW":
                    non_base += len(vals) - 1
                elif it["id"] == "W4a":
                    non_base += len([v for v in vals if v is not None]) - 1 if None in vals else len(vals) - 1
                else:
                    non_base += len(vals) - 1
            return 1 + non_base + 1
        self.assertEqual(n(self.grids["ict"]), 41)
        self.assertEqual(n(self.grids["wyckoff"]), 16)


if __name__ == "__main__":
    unittest.main()
