"""One system: one engine, one style vocabulary, one risk decision.

User decision 2026-09-13: keep strategy-runner.py on three horizons (scalping 15m / day 1H / swing 4H) at
planned R:R >= 3 and 3 % risk; delete demo-pilot.py, the execution.pilot_profile switch, the ten-value STYLE
map and the gold-* names. These tests exist because every one of those was a SECOND way to express something
the system already expressed once, and the duplicates drifted: the floor drifted (2R vs 3R), the risk ceiling
drifted (1 % vs 3 %), and `scalping` meant 1m in one vocabulary and 15m in the other.

The method-preset switch is deliberately NOT covered here -- all six presets and the control panel stay.
"""
import json, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


def sources():
    """Every tracked python/bash source, minus this test file."""
    out = {}
    for d in (SCRIPTS, os.path.join(SCRIPTS, "tests")):
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".py", ".sh")) and fn != "test_one_system.py":
                out[os.path.relpath(os.path.join(d, fn), ROOT)] = open(os.path.join(d, fn), encoding="utf-8").read()
    return out


class LegacyEngineIsGone(unittest.TestCase):
    def test_the_file_does_not_exist(self):
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "demo-pilot.py")))

    def test_nothing_executes_it(self):
        """A dangling reference in the loop script is a crash at 3am, not a lint warning."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("demo-pilot.py", line, f"{path}:{i} still references the deleted engine")
                self.assertNotIn("demo_pilot", line, f"{path}:{i} still references the deleted engine")

    def test_the_profile_switch_is_gone(self):
        """Two profiles meant two rule sets on one account; there is one engine now, so a profile key can only
        select 'the engine' or 'nothing at all' -- and the second option is a footgun, not a feature."""
        for path, src in sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertNotIn("pilot_profile", line, f"{path}:{i} still reads the deleted profile key")

    def test_the_config_carries_no_profile_key(self):
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        self.assertNotIn("pilot_profile", cfg.get("execution", {}))
