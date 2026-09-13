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

    def test_invalidation_owners_come_from_the_registry(self):
        # The stop level's owner must be a dimension the registry says CAN own one — not a tuple hand-kept in
        # check-narrative.py and again in narrative.schema.json, which drift apart when a dimension is added.
        self.assertEqual(M.invalidation_owners(), ("wyckoff", "ict"))

    def test_narrative_schema_owner_enum_is_derived(self):
        doc = json.load(open(os.path.join(ROOT, "docs", "architecture", "schemas", "narrative.schema.json"), encoding="utf-8"))
        enum = doc["properties"]["symbols"]["additionalProperties"]["properties"]["invalidation"]["properties"]["owner"]["enum"]
        self.assertEqual(sorted(enum), sorted(M.invalidation_owners()))

    def test_cfd_has_no_coinglass_dimension(self):
        doc = json.load(open(SCHEMA, encoding="utf-8"))
        props = doc["properties"]["markets"]["properties"]["cfd"]["properties"]["dimensions"]["properties"]
        self.assertNotIn("footprint", props)
        self.assertNotIn("heatmap", props)


if __name__ == "__main__":
    unittest.main()
