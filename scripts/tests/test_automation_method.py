"""`automation.py method` -- the named preset as a set of the four dimension flags.
Rules CFG-03, CFG-04, CFG-10 in docs/security/2026-09-12-method-panel.md."""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class MethodCommand(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def cfg(self):
        return json.load(open(CONFIG, encoding="utf-8"))

    def test_sets_exactly_the_flags_the_preset_names(self):
        r = self.run_auto("method", "wyckoff+ict", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["dimensions"],
                         {"wyckoff": True, "ict": True, "footprint": False, "heatmap": False})

    def test_records_history(self):
        # the committed config's crypto dimensions may already equal 'full' (all four on), which would make
        # this a no-op independent of the code under test -- force a real change first so "applied" is checked
        # for the right reason.
        self.run_auto("dimension", "footprint", "off", "--market", "crypto")
        self.run_auto("method", "full", "--market", "crypto", "--who", "tester", "--reason", "unit test")
        row = self.cfg()["history"][-1]
        self.assertEqual(row["result"], "applied")
        self.assertIn("full", row["action"])
        self.assertEqual(row["actor"], "tester")

    def test_touches_nothing_but_the_four_flags(self):
        """CFG-10: the write scope is the dimension block, not a licence to rewrite the config."""
        before = self.cfg()
        self.run_auto("method", "wyckoff+footprint", "--market", "crypto")
        after = self.cfg()
        for key in ("enabled", "execution", "layers", "pilot_process", "services"):
            self.assertEqual(before.get(key), after.get(key), f"{key} changed")
        self.assertEqual(before["markets"]["crypto"]["instruments"], after["markets"]["crypto"]["instruments"])
        self.assertEqual(before["markets"]["crypto"]["timeframes"], after["markets"]["crypto"]["timeframes"])
        self.assertEqual(before["markets"]["cfd"], after["markets"]["cfd"])

    def test_refuses_a_preset_the_market_cannot_have(self):
        """cfd has no CoinGlass source: footprint/heatmap presets are structurally impossible there."""
        r = self.run_auto("method", "full", "--market", "cfd")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout + r.stderr)
        self.assertEqual(self.cfg()["history"][-1]["result"], "refused")

    def test_refuses_an_unknown_preset_without_touching_the_config(self):
        before = self.cfg()
        r = self.run_auto("method", "wyckoff+telepathy", "--market", "crypto")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(before["markets"], self.cfg()["markets"])

    def test_no_market_applies_to_every_market_that_can_have_the_preset(self):
        r = self.run_auto("method", "wyckoff+ict")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for m in ("crypto", "cfd"):
            self.assertTrue(self.cfg()["markets"][m]["dimensions"]["wyckoff"])
            self.assertTrue(self.cfg()["markets"][m]["dimensions"]["ict"])

    def test_status_prints_the_derived_preset_label(self):
        self.run_auto("method", "wyckoff+ict", "--market", "crypto")
        r = self.run_auto("status")
        self.assertIn("wyckoff+ict", r.stdout)

    def test_status_says_custom_when_no_preset_names_the_flags(self):
        self.run_auto("method", "full", "--market", "crypto")
        self.run_auto("dimension", "ict", "off", "--market", "crypto")
        r = self.run_auto("status")
        self.assertIn("custom", r.stdout)


class MinimumWarningIsModeAware(unittest.TestCase):
    """The warning used to hardcode `< 2` and the words "NORMAL minimum of 2". After SOLO landed (2026-09-12) a
    single-dimension PRESET is a valid trading configuration, so that warning fired on a correct setup and told
    the user no TRADE could pass when one could. It must read the preset's mode instead."""

    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def set_dims(self, dims):
        c = json.load(open(CONFIG, encoding="utf-8"))
        c["markets"]["crypto"]["dimensions"] = dims
        json.dump(c, open(CONFIG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    def status(self):
        return subprocess.run([sys.executable, AUTO, "status"], capture_output=True, text=True).stdout

    def test_a_solo_preset_does_not_warn(self):
        self.set_dims({"wyckoff": False, "ict": True, "footprint": False, "heatmap": False})
        out = self.status()
        self.assertIn("SOLO", out)
        self.assertNotIn("no live TRADE verdict can pass for crypto", out)

    def test_a_hand_toggled_custom_single_dimension_still_warns(self):
        """SOLO must stay reachable only through a declared preset -- never by toggling flags one by one."""
        self.set_dims({"wyckoff": False, "ict": False, "footprint": True, "heatmap": False})
        out = self.status()
        self.assertIn("NORMAL mode", out)
        self.assertIn("no live TRADE verdict can pass for crypto", out)

    def test_the_stale_flat_minimum_text_is_gone(self):
        src = open(AUTO, encoding="utf-8").read()
        self.assertNotIn("below the NORMAL minimum of 2", src)


class AllowsMaster(unittest.TestCase):
    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def test_allows_master_exists_and_uses_the_refusal_exit_code(self):
        """CRON-01: the applier gates on exit 0. Exit 2 is REFUSED, exit 1 is a usage error -- an
        applier that treated 'not 2' as permission would run on a typo."""
        r = self.run_auto("allows", "master")
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)

    def test_unknown_allows_target_is_a_usage_error_not_a_refusal(self):
        r = self.run_auto("allows", "masterr")
        self.assertEqual(r.returncode, 1, "usage errors must stay exit 1 so a gate can tell them apart")


class EnvironmentPresetDoesNotStompMethod(unittest.TestCase):
    """`demo`/`real` share cmd_preset() -> apply_preset() -> bring_up(). bring_up() installs real launchd
    agents and starts a real `caffeinate` keep-awake (scripts/automation.py bring_up(), cmd_preset()) --
    none of that is safe to trigger from a test, and the documented AUTOMATION_PILOT_DRYRUN=1 override does
    NOT gate the scanner-agent install or the keep-awake start (only `pilot start`/`pilot stop`/`off`), so a
    subprocess `automation.py demo` would still install a real agent and spawn a real `caffeinate` on the
    developer's machine even with every documented override set. Instead we load automation.py as a module
    and call apply_preset() directly -- the exact function this bug is in -- without going through
    cmd_preset()/bring_up()."""

    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def test_demo_preset_preserves_the_chosen_method(self):
        """apply_preset used to do mk["dimensions"] = {d: True ...}, silently erasing the user's preset."""
        r = self.run_auto("method", "wyckoff+ict", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        before = json.load(open(CONFIG, encoding="utf-8"))["markets"]["crypto"]["dimensions"]

        spec = importlib.util.spec_from_file_location("automation_under_test", AUTO)
        auto = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(auto)
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        auto.apply_preset(cfg, None, "demo")  # the buggy call path, minus bring_up() -- no launchd, no caffeinate

        after = cfg["markets"]["crypto"]["dimensions"]
        self.assertEqual(before, after, "demo's apply_preset reset the dimensions and wiped the preset")
