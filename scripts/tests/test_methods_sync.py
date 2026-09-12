"""The schema's dimension shape is DERIVED from methods.json. Drift fails the build, exactly as
test_instruments_sync.py does for the symbol enums."""
import importlib.util, json, os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

SCHEMA = os.path.join(ROOT, "docs", "architecture", "schemas", "automation-config.schema.json")


class Sync(unittest.TestCase):
    def test_check_mode_is_clean(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-methods.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"drift:\n{r.stdout}\n{r.stderr}")

    def test_schema_dimension_shape_matches_registry(self):
        doc = json.load(open(SCHEMA, encoding="utf-8"))
        for m in M.markets():
            props = doc["properties"]["markets"]["properties"][m]["properties"]["dimensions"]
            self.assertEqual(sorted(props["properties"]), sorted(M.dimensions(m)))
            self.assertEqual(sorted(props["required"]), sorted(M.dimensions(m)))
            self.assertFalse(props["additionalProperties"],
                             "impossible states must be absent from the shape, not settable flags")

    def test_cfd_has_no_coinglass_dimension(self):
        doc = json.load(open(SCHEMA, encoding="utf-8"))
        props = doc["properties"]["markets"]["properties"]["cfd"]["properties"]["dimensions"]["properties"]
        self.assertNotIn("footprint", props)
        self.assertNotIn("heatmap", props)


if __name__ == "__main__":
    unittest.main()
