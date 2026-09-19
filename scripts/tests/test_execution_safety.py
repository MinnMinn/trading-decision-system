"""CLAUDE.md §51 EXECUTION SAFETY -- seven requirements that were already held, and one that was not.

The previous audit recorded §51 as PRESENT with a single gap, and named it exactly:

    "Only gap: withdrawal permission is never requested but never asserted either -- no key-scope check at
    load."

That distinction is the whole section. "No code in this repository calls a withdrawal endpoint" was true and
is not the same claim as "this key cannot withdraw". A key minted with withdrawal rights would have traded
exactly as well as one without, and nothing anywhere would have said so -- which matters only once, on the day
the key leaks, and by then the difference is the entire balance.

So the seven held requirements become a registry whose citations are **resolved** (a requirement satisfied by
prose is not satisfied), and the eighth becomes a real guard with the repo's three-valued rule applied to
credentials for the first time: `UNKNOWN` is not `NO_WITHDRAWAL`. It refuses in `real`, and it is recorded
rather than laundered in demo -- because Binance publishes `apiRestrictions` on the mainnet host only, so a
testnet key genuinely cannot be probed, and saying otherwise would be a lie with a reassuring shape.

`DoNotWeaken` re-verifies the four guarantees that were already there. §51 is the one section where a
regression is measured in money.
"""
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import execution_safety as ES      # noqa: E402
import account_profile as AP       # noqa: E402
import providers as P              # noqa: E402
import trading_env                 # noqa: E402

REGISTRY = os.path.join(ROOT, "docs", "architecture", "execution-safety.json")
SPEC = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
S51 = SPEC.split("51. EXECUTION SAFETY", 1)[1].split("52. REALTIME DATA", 1)[0]
RUNNER_SRC = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
PROBE_SRC = open(os.path.join(ROOT, "scripts", "binance-testnet-order.sh"), encoding="utf-8").read()


def _resolve(citation):
    path, fn = citation.split("::", 1)
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return f"{path} does not exist"
    src = open(full, encoding="utf-8").read()
    if not re.search(rf"^def {re.escape(fn)}\(", src, re.M):
        return f"{path} has no function named {fn}"
    return None


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_every_requirement_quotes_51_verbatim(self):
        # A paraphrase drifts; the spec's own sentence cannot.
        for line in ES.spec_lines():
            first = line.split(".")[0].strip()
            self.assertIn(first, " ".join(S51.split()), first)

    def test_all_eight_requirements_are_declared(self):
        self.assertEqual(len(ES.REQUIREMENTS), 8)

    def test_every_requirement_names_a_function_that_exists(self):
        # The difference between a registry and a promise.
        for rid in ES.REQUIREMENTS:
            self.assertIsNone(_resolve(ES.requirement(rid)["enforced_by"]), rid)

    def test_the_nine_pre_execution_validations_are_pointed_at_not_restated(self):
        # They are §36's ordering and have one source. A second copy here would drift the first time a step
        # moved (rules/single-source-of-truth.md).
        r = ES.requirement("validate_before_execution")
        self.assertEqual(r["_pointer"], "docs/architecture/decision-order.json")
        # The STRUCTURED data must not carry a second copy of §36's nine steps. (The `_not_restated_here`
        # note quotes them once, to say what it is not restating; a sentence explaining an absence is not the
        # duplicate the rule is about.)
        rows = json.dumps(json.load(open(REGISTRY, encoding="utf-8"))["requirements"])
        for step_word in ("provider capability", "order constraints"):
            self.assertNotIn(step_word, rows, f"{step_word!r} is §36's list; this registry points at it")


class TheLoaderRefusesWhatWouldInvert51(unittest.TestCase):
    def _mutate(self, fn):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        fn(data)
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-exec.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(ES.RegistryError) as cm:
                ES._load(p)
            return str(cm.exception)
        finally:
            os.remove(p)

    def test_an_unknown_scope_declared_safe_is_refused(self):
        # The one edit that inverts the section while looking like a clarification.
        def launder(d):
            d["key_scope"]["states"]["UNKNOWN"] = "Not read yet; treated as no withdrawal permission."
        self.assertIn("silent downgrade", self._mutate(launder))

    def test_removing_every_refusal_environment_is_refused(self):
        def empty(d):
            d["key_scope"]["refusal_environments"] = []
        self.assertIn("never assume mainnet API credentials are safe".lower(),
                      self._mutate(empty).lower())

    def test_a_requirement_enforced_by_prose_is_refused(self):
        def prose(d):
            d["requirements"][0]["enforced_by"] = "we are careful about this"
        self.assertIn("a requirement nothing holds", self._mutate(prose))


class UnknownIsNotNoWithdrawal(unittest.TestCase):
    """The three-valued rule §20 applies to data, arriving at credentials."""

    def test_an_unread_scope_is_unknown(self):
        st, why = ES.assess("binance_spot", "demo", scope=None, path=os.path.join(tempfile.mkdtemp(), "x.json"))
        self.assertEqual(st, ES.UNKNOWN)
        self.assertIn("no key-scope reading", why)

    def test_an_unread_scope_refuses_in_real(self):
        with self.assertRaises(ES.UnsafeKey) as cm:
            ES.assert_safe("binance_spot", "real", path=os.path.join(tempfile.mkdtemp(), "x.json"))
        self.assertIn("never assume mainnet api credentials are safe", str(cm.exception).lower())

    def test_an_unread_scope_does_not_refuse_in_demo_but_is_still_unknown(self):
        # The testnet has no apiRestrictions endpoint at all, so UNKNOWN is the honest answer there -- and it
        # is returned AS unknown, never rewritten into the reassuring one.
        st, _ = ES.assert_safe("binance_spot", "demo", path=os.path.join(tempfile.mkdtemp(), "x.json"))
        self.assertEqual(st, ES.UNKNOWN)
        self.assertNotEqual(st, ES.NO_WITHDRAWAL)

    def test_a_key_that_can_withdraw_is_refused_in_every_environment(self):
        # Including demo: what is being refused is what the KEY can do, not what this run intends.
        for env in ("demo", "real"):
            with self.assertRaises(ES.UnsafeKey, msg=env) as cm:
                ES.assert_safe("binance_spot", env, scope={"enableWithdrawals": True, "checked_at": "2026-09-18T00:00:00Z"})
            self.assertIn("never require withdrawal permission", str(cm.exception).lower())

    def test_a_key_that_cannot_withdraw_passes_everywhere(self):
        for env in ("demo", "real"):
            st, _ = ES.assert_safe("binance_spot", env,
                                   scope={"enableWithdrawals": False, "checked_at": "2026-09-18T00:00:00Z"})
            self.assertEqual(st, ES.NO_WITHDRAWAL, env)

    def test_a_provider_that_could_not_report_is_unknown_not_safe(self):
        st, why = ES.assess("binance_spot", "demo",
                            scope={"unavailable": True, "why": "endpoint is mainnet-only"})
        self.assertEqual(st, ES.UNKNOWN)
        self.assertIn("mainnet-only", why)

    def test_a_reading_with_no_field_at_all_is_unknown(self):
        st, _ = ES.assess("binance_spot", "demo", scope={"checked_at": "2026-09-18T00:00:00Z"})
        self.assertEqual(st, ES.UNKNOWN)

    def test_the_record_round_trips(self):
        p = os.path.join(tempfile.mkdtemp(), "key-scope.json")
        ES.record("binance_spot", enable_withdrawals=False, checked_at="2026-09-18T00:00:00Z", path=p)
        self.assertEqual(ES.assess("binance_spot", "real", path=p)[0], ES.NO_WITHDRAWAL)
        ES.record("binance_spot", unavailable=True, why="testnet", checked_at="2026-09-18T00:00:00Z", path=p)
        self.assertEqual(ES.assess("binance_spot", "real", path=p)[0], ES.UNKNOWN)

    def test_an_unreadable_record_is_unknown_not_a_crash(self):
        p = os.path.join(tempfile.mkdtemp(), "broken.json")
        open(p, "w").write("{not json")
        self.assertEqual(ES.assess("binance_spot", "demo", path=p)[0], ES.UNKNOWN)


class WiredIntoTheOnlyGateThatCanStopATick(unittest.TestCase):
    def test_the_runner_consults_the_key_scope(self):
        self.assertIn("ES.gate_reason(", RUNNER_SRC)

    def test_it_sits_in_the_stop_only_gate(self):
        # automation_gate "can only stop, never start" -- the right shape for a safety check, and the wrong
        # place for anything that could enable a trade.
        gate = RUNNER_SRC.split("def automation_gate", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("ES.gate_reason(", gate)
        self.assertNotIn("return None if", gate.split("ES.gate_reason(", 1)[1][:200])

    def test_gate_reason_is_a_sentence_in_real_and_silence_in_demo(self):
        tmp = os.path.join(tempfile.mkdtemp(), "x.json")
        self.assertIsNotNone(ES.gate_reason("binance_spot", "real", path=tmp))
        self.assertIsNone(ES.gate_reason("binance_spot", "demo", path=tmp))

    def test_the_probe_is_a_separate_deliberate_act(self):
        # Nothing on a decision path reaches the network for this; the scope is read by one command and
        # recorded.
        src = open(os.path.join(ROOT, "scripts", "execution_safety.py"), encoding="utf-8").read()
        for forbidden in ("urllib", "requests", "subprocess", "socket"):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertIn("api-restrictions)", PROBE_SRC)

    def test_the_probe_never_prints_the_key(self):
        block = PROBE_SRC.split("api-restrictions)", 1)[1].split("\n  ;;", 1)[0]
        for secret in ("API_KEY", "SECRET_KEY", "$BINANCE"):
            self.assertNotIn(secret, block, secret)

    def test_a_testnet_refusal_is_recorded_as_unavailable_not_as_safe(self):
        block = PROBE_SRC.split("api-restrictions)", 1)[1].split("\n  ;;", 1)[0]
        self.assertIn("unavailable=True", block)
        self.assertNotIn("enable_withdrawals=False", block.split("else", 1)[-1])


class DoNotWeaken(unittest.TestCase):
    """The four guarantees that were already there. §51 is the section where a regression costs money."""

    def test_the_pilot_still_refuses_environment_real(self):
        gate = RUNNER_SRC.split("def automation_gate", 1)[1].split("\ndef ", 1)[0]
        self.assertIn('== "real"', gate)
        self.assertIn("refusing", gate)

    def test_a_placeholder_credential_still_refuses(self):
        self.assertEqual(trading_env.PLACEHOLDER, "__FILL_ME__")
        ok, missing, _ = trading_env.completeness("real", ("BINANCE_FUTURES_API_KEY",))
        self.assertIsInstance(ok, bool)

    def test_there_is_still_no_account_profile_for_real(self):
        # An order path with no declared account rules refuses; that is what keeps `real` unreachable even if
        # every other guard were removed.
        with self.assertRaises(ValueError):
            AP.for_venue("futures", "real")

    def test_the_manual_provider_can_still_never_be_selected_by_a_loop(self):
        pid = P.unattended_venue_for("crypto")
        manual = [p for p in P.for_role("execution", "crypto") if not P.PROVIDERS[p]["unattended"]]
        self.assertTrue(manual, "binance_spot is the human-confirmation provider and must stay non-unattended")
        for p in manual:
            self.assertNotEqual(P.alias_of(p), pid)

    def test_describe_reports_the_state_rather_than_a_verdict(self):
        out = ES.describe("demo")
        self.assertIn("UNKNOWN", out)
        self.assertIn("§51", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
