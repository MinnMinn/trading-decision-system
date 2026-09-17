"""`automation.py instrument set` -- the declarative batch behind the panel's multi-select.
Rules CFG-11..CFG-15 in docs/security/2026-09-12-method-panel.md. The batch re-validates independently of
any caller: a future caller may not be the cron."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I

AUTO = os.path.join(ROOT, "scripts", "automation.py")
CONFIG = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


class InstrumentSet(unittest.TestCase):
    def setUp(self):
        self.backup = tempfile.NamedTemporaryFile(delete=False).name
        shutil.copy(CONFIG, self.backup)

    def tearDown(self):
        shutil.copy(self.backup, CONFIG); os.unlink(self.backup)

    def run_auto(self, *args):
        return subprocess.run([sys.executable, AUTO, *args], capture_output=True, text=True)

    def cfg(self):
        return json.load(open(CONFIG, encoding="utf-8"))

    def test_sets_the_whole_list_in_one_history_row(self):
        before = len(self.cfg()["history"])
        r = self.run_auto("instrument", "set", "BTCUSDT,ETHUSDT,SOLUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.assertEqual(len(self.cfg()["history"]), before + 1, "CFG-11: one batch, one row")

    def test_output_order_is_the_allowlist_order_not_the_input_order(self):
        """CFG-13: a canonical order makes 'did this change?' a value comparison, not a set comparison."""
        self.run_auto("instrument", "set", "SOLUSDT,BTCUSDT", "--market", "crypto")
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], ["BTCUSDT", "SOLUSDT"])

    def test_setting_the_same_list_again_records_nothing(self):
        """CFG-13: a true no-op must not spend a row of the 200-row audit ring."""
        self.run_auto("instrument", "set", "BTCUSDT", "--market", "crypto")
        n = len(self.cfg()["history"])
        r = self.run_auto("instrument", "set", "BTCUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(self.cfg()["history"]), n, "a no-op recorded a history row")

    def test_a_symbol_from_another_market_refuses_the_whole_batch(self):
        """CFG-11 + CFG-12: all-or-nothing, re-validated by the script regardless of caller.

        Was test_forex_anywhere_in_the_batch_refuses_the_whole_batch until 2026-09-17, asserting the word
        "Forex" appeared in the refusal. The prohibition is lifted, so the probe is now a symbol that is real
        and allowlisted but belongs to a DIFFERENT market -- which exercises the same all-or-nothing path while
        testing something that cannot be deleted by a policy change."""
        before = self.cfg()["markets"]["crypto"]["instruments"]
        r = self.run_auto("instrument", "set", "BTCUSDT,XAUUSD", "--market", "crypto")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("XAUUSD", r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], before, "partial batch applied")

    def test_off_allowlist_symbol_refuses_the_whole_batch(self):
        before = self.cfg()["markets"]["crypto"]["instruments"]
        r = self.run_auto("instrument", "set", "BTCUSDT,DOGEUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], before)

    def test_symbol_from_the_other_market_is_refused(self):
        r = self.run_auto("instrument", "set", "BTCUSDT,XAUUSD", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_lowercase_is_refused_not_silently_normalised(self):
        """CFG-12: no normalisation of untrusted input -- accept the canonical spelling or refuse."""
        r = self.run_auto("instrument", "set", "btcusdt", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_duplicates_are_refused(self):
        r = self.run_auto("instrument", "set", "BTCUSDT,BTCUSDT", "--market", "crypto")
        self.assertEqual(r.returncode, 2)

    def test_empty_list_is_allowed_and_explicit(self):
        """CFG-14: no instruments = no new entries in that market. A narrowing, and the safe direction."""
        r = self.run_auto("instrument", "set", "", "--market", "crypto")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.cfg()["markets"]["crypto"]["instruments"], [])
        self.assertEqual(self.cfg()["history"][-1]["result"], "applied")

    def test_never_adds_a_symbol_absent_from_instruments_json(self):
        """CFG-15: instruments.json is the ceiling; this command can never raise it."""
        for m in I.MARKETS:
            self.run_auto("instrument", "set", ",".join(I.analysis(m)), "--market", m)
            self.assertTrue(set(self.cfg()["markets"][m]["instruments"]) <= set(I.analysis(m)))

    def test_single_symbol_form_rejects_a_bad_value_with_usage_exit_1(self):
        """Regression: dropping argparse's choices=['on','off'] on `value` to make room for the 'set' sentinel
        must not let a typo reach cmd_instrument's logic. Usage errors are exit 1; exit 2 is reserved for REFUSED."""
        before = self.cfg()
        r = self.run_auto("instrument", "BTCUSDT", "banana")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.cfg(), before, "a usage error modified the config")


if __name__ == "__main__":
    unittest.main()
