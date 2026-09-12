"""The applier cron template. Rules CRON-01, CRON-02, CRON-03, CRON-06, CRON-10 in
docs/security/2026-09-12-method-panel.md."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL = os.path.join(ROOT, "integrations", "crons", "method-switch.md")


class MethodSwitchTemplate(unittest.TestCase):
    def setUp(self):
        self.src = open(TPL, encoding="utf-8").read()

    def test_gate_proceeds_only_on_exit_zero(self):
        """CRON-01: exit 2 is REFUSED and exit 1 is a usage error, so 'stop on exit 2' is fail-open."""
        self.assertIn("allows master", self.src)
        self.assertIn("exit 0", self.src)
        self.assertNotRegex(self.src, r"exits?\s*2\s*[-—,]?\s*(skip|stop)")

    def test_declares_a_layer_and_no_market(self):
        fm = self.src.split("---")[1]
        self.assertIn("layer:", fm)
        self.assertNotIn("market:", fm)
        self.assertNotIn("timeframe:", fm)

    def test_names_exact_document_paths_not_a_collection_scan(self):
        """CRON-06: reading three known paths bounds what an arbitrary writer can feed the session."""
        self.assertIn("control/request.crypto", self.src)
        self.assertIn("control/request.cfd", self.src)

    def test_forbids_treating_db_content_as_instructions(self):
        """CRON-03: the session's own capability IS the escalation; only the prompt stops it."""
        low = self.src.lower()
        self.assertTrue("not instructions" in low or "data, not" in low or "never as instructions" in low)
        self.assertIn("automation.py", self.src)

    def test_whitelists_the_preset_ids_and_hardcodes_who(self):
        """CRON-04 + CRON-02: validate before acting; never pass a db string as an argument."""
        self.assertIn("artifact-panel", self.src)

    def test_edge_trigger_is_inequality_not_ordering(self):
        """CRON-05: a future-dated timestamp from a skewed phone clock must not wedge the watermark."""
        self.assertNotRegex(self.src, r"requested_at\s*>\s*applied")

    def test_watermark_advances_only_when_every_half_is_resolved(self):
        """CRON-13: with two independent halves under one requested_at, advancing after a half-failure
        loses the other half silently and forever."""
        low = self.src.lower()
        self.assertTrue("both" in low or "every half" in low or "cả hai" in low)

    def test_heartbeat_every_tick(self):
        self.assertIn("control/heartbeat", self.src)


if __name__ == "__main__":
    unittest.main()
