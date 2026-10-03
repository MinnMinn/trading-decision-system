"""CLAUDE.md §33 -- Account Profile as a first-class domain concept.

§33 names fifteen attributes and says "Account rules must be configurable". Before 2026-09-18 exactly one of
them was configuration (max risk/trade, `risk-config.json`) and four more were literals inside the live order
engine: `EQUITY_HALT_FRAC = 0.85`, `MAX_TRADES_PER_DAY = 3`, `LEVERAGE = 3`, `CONSEC_LOSS_HALT = 5`. That is
not a configurable account rule; it is a property of the runner's source code.

Three things these tests are built to prove, because the requirement is not satisfied by the registry merely
existing:

1. **The rules are ENFORCED, not merely declared.** The live profiles honestly declare `null` for the rules
   this platform's two demo accounts do not have, so a test that only drove the live profiles would prove
   almost nothing. `PROP` below is a complete PROP_CHALLENGE profile -- daily loss, trailing drawdown,
   consistency, profit target, minimum trading days, session / overnight / weekend / news restrictions -- run
   through the SAME validator and the SAME evaluators the live profiles use. No such account exists, so no
   such profile ships (§57); the rules for one do.
2. **A profile may only tighten.** A `max_risk_per_trade` above the platform ceiling, or a news buffer shorter
   than the calendar's, is refused rather than applied.
3. **An unevaluable rule is never permission.** A declared rule whose input is missing reports UNKNOWN, which
   blocks an entry -- and which never writes the kill switch, because "I could not read the balance" is not
   "the account is down 15 %".
"""
import copy
import os
import sys
import unittest

import fresh_calendar as FC  # noqa: E402  (a current, quiet copy of the real calendar)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP
import instruments as I
import trading_env as TE

from live_write_isolation import redirect as _redirect_writes

_RESTORE_WRITES = None


def setUpModule():
    # RunnerWiring and AccountLimitsOnTheOrderPath both load strategy-runner.py fresh and drive a real
    # sr.tick() (the latter's whole point is proving the account gate is consulted ON the order path, not
    # just in a unit test of the evaluator) -- which otherwise appends a real trace to data/live/latency/
    # (scripts/tests/live_write_isolation.py). sr.log itself is monkeypatched by every such test already, so
    # only the latency writer needs this.
    global _RESTORE_WRITES
    _RESTORE_WRITES = _redirect_writes()


def tearDownModule():
    _RESTORE_WRITES()


def _registry(profiles):
    return {"version": 1, "context_types": list(AP.CONTEXT_TYPES), "profiles": profiles}


# A complete prop-challenge account, exercising every rule shape the registry supports. It is validated by
# the real validator in `PropChallengeRulesActuallyRun.setUpClass`, so a shape this file gets wrong fails
# loudly rather than testing an illegal profile.
PROP_RULES = {
    "initial_balance": {"amount": 100000.0, "currency": "USD"},
    "max_daily_loss": {"pct": 0.05, "basis": "day_start_equity", "action": "HALT"},
    "max_total_drawdown": {"pct": 0.10, "basis": "initial_balance", "action": "HALT"},
    "trailing_drawdown": {"pct": 0.04, "basis": "peak_equity", "action": "HALT"},
    "profit_target": {"pct": 0.08, "basis": "initial_balance"},
    "min_trading_days": 5,
    "min_profitable_days": None,   # this fixture's day rule reads min_trading_days; see MinProfitableDays below
    "max_leverage": 30,
    "max_risk_per_trade": 0.005,
    "max_positions": {"mode": "fixed", "count": 2},
    "consistency_rules": [{"id": "best-day", "kind": "max_share_of_profit_from_best_day", "threshold": 0.40,
                           "action": "BLOCK_ENTRY", "what": "no single day may be over 40 % of total profit"}],
    "news_restrictions": {"impacts": ["HIGH", "MEDIUM"], "pre_minutes": 30, "post_minutes": 30},
    "overnight_restrictions": {"hold_allowed": False, "action": "BLOCK_ENTRY", "what": "flat by the close"},
    "weekend_restrictions": {"hold_allowed": False, "action": "BLOCK_ENTRY", "what": "flat by Friday"},
    "session_restrictions": {"allowed_sessions": ["london", "ny_am"], "action": "BLOCK_ENTRY"},
    "custom_failure_conditions": [{"id": "loss-streak", "kind": "consecutive_losses", "threshold": 3,
                                   "action": "HALT", "what": "three losses in a row ends the challenge"}],
    "max_trades_per_day_per_symbol": 2,
}
# `environment` is "demo" -- a ROUTABLE one -- on purpose: the uniqueness rule this fixture exercises below
# only applies to environments an order path can be switched to, so a fixture in an unroutable environment
# would test the exemption rather than the rule. Nothing here is ever routed to; the registry is standalone.
PROP = {"what": "a prop challenge account, for tests only", "context_type": "PROP_CHALLENGE",
        "venue": "mt5", "environment": "demo", "rules": PROP_RULES}


class RegistryShape(unittest.TestCase):
    def test_every_profile_declares_every_rule_key(self):
        for pid, prof in AP.PROFILES.items():
            with self.subTest(profile=pid):
                for key in AP.RULE_KEYS:
                    self.assertIn(key, prof["rules"], f"{pid} does not declare {key}")

    def test_a_missing_rule_key_is_refused(self):
        """A declared null and an absent key are different facts. If the reader accepted the absent one it
        would eventually enforce a limit nobody wrote, or skip one somebody did."""
        for key in AP.RULE_KEYS:
            rules = {k: v for k, v in PROP_RULES.items() if k != key}
            with self.subTest(missing=key), self.assertRaises(ValueError) as cm:
                AP._validate(_registry({"p": dict(PROP, rules=rules)}))
            self.assertIn(key, str(cm.exception))

    def test_the_five_context_types_are_exactly_section_5s(self):
        self.assertEqual(set(AP.CONTEXT_TYPES),
                         {"PERSONAL", "PROP_CHALLENGE", "PROP_FUNDED", "DEMO", "CUSTOM"})

    def test_an_unknown_context_type_is_refused(self):
        with self.assertRaises(ValueError):
            AP._validate(_registry({"p": dict(PROP, context_type="HEDGE_FUND")}))

    def test_two_profiles_on_one_venue_are_now_a_legal_configuration(self):
        """Running several accounts on one broker is the point of the multi-account work
        (docs/plans/2026-09-19-multi-account.md Pha 0). Until 2026-09-19 the validator raised HERE, which made
        it a refused configuration rather than an unimplemented one. The invariant it protected -- an order
        path must never GUESS which account's rules apply -- did not go away; it moved into the resolvers,
        which is what the next two tests check."""
        AP._validate(_registry({"a": PROP, "b": copy.deepcopy(PROP)}))      # must not raise

    def test_for_venue_still_refuses_when_the_venue_no_longer_identifies_one_account(self):
        reg = AP._validate(_registry({"a": PROP, "b": copy.deepcopy(PROP)}))
        saved = AP.PROFILES
        try:
            AP.PROFILES = reg
            with self.assertRaises(ValueError) as cm:
                AP.for_venue(PROP["venue"], PROP["environment"])
            msg = str(cm.exception)
            self.assertIn("exactly one is needed", msg)
            self.assertIn("for_account", msg, "the refusal must say how to disambiguate")
        finally:
            AP.PROFILES = saved

    def test_for_account_resolves_the_same_registry_by_id(self):
        reg = AP._validate(_registry({"a": PROP, "b": copy.deepcopy(PROP)}))
        saved = AP.PROFILES
        try:
            AP.PROFILES = reg
            self.assertEqual(AP.for_account("a")["id"], "a")
            self.assertEqual(AP.for_account("b")["id"], "b")
        finally:
            AP.PROFILES = saved

    def test_for_account_refuses_a_venue_the_caller_asserted_wrongly(self):
        """A runner launched with --account acc-001 against the wrong bridge must stop, not size orders on
        another venue's account rules."""
        reg = AP._validate(_registry({"a": PROP}))
        saved = AP.PROFILES
        try:
            AP.PROFILES = reg
            AP.for_account("a", venue=PROP["venue"])                 # matching assertion is fine
            with self.assertRaises(ValueError) as cm:
                AP.for_account("a", venue="not-this-venue")
            self.assertIn("Refusing", str(cm.exception))
        finally:
            AP.PROFILES = saved

    def test_for_account_refuses_a_research_template(self):
        """Same rule for_venue already enforced: a research profile must never become the account an order is
        sized against, however it is reached."""
        for pid, prof in AP.PROFILES.items():
            if prof["environment"] in AP.UNROUTABLE_ENVIRONMENTS:
                with self.assertRaises(ValueError) as cm:
                    AP.for_account(pid)
                self.assertIn("unroutable", str(cm.exception))
                AP.get(pid)                                          # get() still loads it, for evaluation
                break
        else:
            self.skipTest("no research profile in the shipped registry")

    def test_the_registry_declares_a_version(self):
        self.assertIsInstance(AP.VERSION, int)
        with self.assertRaises(ValueError):
            AP._validate({"version": "1", "context_types": ["DEMO"], "profiles": {"p": PROP}})


class OnlyReachableProfilesAreAccepted(unittest.TestCase):
    """The uniqueness rule is exempted for unroutable environments. These pin the edges of that exemption,
    because an exemption nobody has fenced is a way to smuggle an unenforced account rule into the registry."""

    def test_an_unknown_environment_is_refused_rather_than_stored_unreachable(self):
        """A misspelt environment is silent damage: `for_venue()` can never reach the profile, and it shares
        no (venue, environment) key with anything, so the uniqueness check never looks at it either."""
        with self.assertRaises(ValueError) as cm:
            AP._validate(_registry({"p": dict(PROP, environment="reserch")}))
        msg = str(cm.exception)
        self.assertIn("reserch", msg)
        self.assertIn("unroutable_environments", msg)

    def test_an_environment_declared_unroutable_may_be_shared_by_several_profiles(self):
        """Two prop templates on one venue is the whole point: a researcher names the template by id."""
        reg = dict(_registry({"a": dict(PROP, environment="research"),
                              "b": dict(copy.deepcopy(PROP), environment="research")}),
                   unroutable_environments=["research"])
        self.assertEqual(sorted(AP._validate(reg)), ["a", "b"])

    def test_declaring_a_live_environment_unroutable_is_refused(self):
        """The dangerous direction: it would switch the uniqueness check off for a path that still places
        orders, letting two accounts claim the same live venue."""
        for env in AP._TE.ENV_NAMES:
            reg = dict(_registry({"p": PROP}), unroutable_environments=[env])
            with self.subTest(environment=env), self.assertRaises(ValueError) as cm:
                AP._validate(reg)
            self.assertIn("routable by definition", str(cm.exception))

    def test_for_venue_refuses_an_unroutable_environment_even_with_one_candidate(self):
        """One research profile on a venue is the case a `len(hits) != 1` guard would wave through."""
        with self.assertRaises(ValueError) as cm:
            AP.for_venue("mt5", "research")
        self.assertIn("unroutable", str(cm.exception))

    def test_the_shipped_research_profiles_are_loadable_by_id_but_not_routable(self):
        research = [p for p, v in AP.PROFILES.items() if v["environment"] in AP.UNROUTABLE_ENVIRONMENTS]
        self.assertTrue(research, "the registry ships no research profile; this test would prove nothing")
        for pid in research:
            with self.subTest(profile=pid):
                self.assertEqual(AP.get(pid)["id"], pid)
                with self.assertRaises(ValueError):
                    AP.for_venue(AP.PROFILES[pid]["venue"], AP.PROFILES[pid]["environment"])


class OnlyTightening(unittest.TestCase):
    def test_a_profile_may_not_raise_the_platform_risk_ceiling(self):
        bad = copy.deepcopy(PROP_RULES); bad["max_risk_per_trade"] = TE.MAX_RISK_PCT * 2
        with self.assertRaises(ValueError) as cm:
            AP._validate(_registry({"p": dict(PROP, rules=bad)}))
        self.assertIn("ABOVE the platform ceiling", str(cm.exception))

    def test_a_profile_may_lower_it(self):
        prof = dict(PROP, id="p")
        self.assertEqual(AP.effective_risk_pct(prof), 0.005)
        self.assertLess(AP.effective_risk_pct(prof), TE.MAX_RISK_PCT)

    def test_a_null_inherits_the_one_authored_ceiling(self):
        """There is ONE authored risk number. A profile that restated it would create a second that drifts."""
        for venue in ("futures", "mt5"):
            prof = AP.for_venue(venue)
            self.assertIsNone(AP.rule(prof, "max_risk_per_trade"))
            self.assertEqual(AP.effective_risk_pct(prof), TE.MAX_RISK_PCT)

    def test_risk_outside_zero_to_one_is_refused(self):
        for bad_value in (0, -0.01, 3, "1%", True):
            bad = copy.deepcopy(PROP_RULES); bad["max_risk_per_trade"] = bad_value
            with self.subTest(value=bad_value), self.assertRaises(ValueError):
                AP._validate(_registry({"p": dict(PROP, rules=bad)}))


class RuleShapeValidation(unittest.TestCase):
    def _refuses(self, **rule_overrides):
        bad = copy.deepcopy(PROP_RULES); bad.update(rule_overrides)
        with self.assertRaises(ValueError) as cm:
            AP._validate(_registry({"p": dict(PROP, rules=bad)}))
        return str(cm.exception)

    def test_a_percentage_typed_as_five_instead_of_0_05_is_refused(self):
        self.assertIn("FRACTION", self._refuses(max_daily_loss={"pct": 5, "basis": "day_start_equity",
                                                                "action": "HALT"}))

    def test_an_unknown_drawdown_basis_is_refused(self):
        self._refuses(trailing_drawdown={"pct": 0.04, "basis": "vibes", "action": "HALT"})

    def test_an_unknown_action_is_refused(self):
        self._refuses(max_total_drawdown={"pct": 0.1, "basis": "initial_balance", "action": "SHRUG"})

    def test_a_limit_measured_against_an_undeclared_initial_balance_is_refused(self):
        msg = self._refuses(initial_balance=None, profit_target=None)
        self.assertIn("nothing to measure against", msg)

    def test_a_rule_kind_no_evaluator_knows_is_refused(self):
        """A rule this module cannot evaluate would be listed as enforced and enforce nothing."""
        msg = self._refuses(custom_failure_conditions=[{"id": "x", "kind": "bad_vibes", "threshold": 1,
                                                        "action": "HALT", "what": "?"}])
        self.assertIn("no evaluator knows", msg)

    def test_a_session_restriction_naming_a_nonexistent_window_is_refused(self):
        """A renamed window must not leave a rule behind that matches nothing and so blocks everything."""
        msg = self._refuses(session_restrictions={"allowed_sessions": ["tokyo_lunch"], "action": "BLOCK_ENTRY"})
        self.assertIn("tokyo_lunch", msg)

    def test_a_news_restriction_naming_an_unknown_impact_is_refused(self):
        self._refuses(news_restrictions={"impacts": ["CATASTROPHIC"]})

    def test_the_live_registry_passes_its_own_validator(self):
        AP._validate(AP._read())


class MinProfitableDays(unittest.TestCase):
    """docs/architecture/account-profiles.json `min_profitable_days` (addendum §8.3, 2026-09-28): The5ers
    High Stakes Step 1's OWN reading of "how many days" -- profitable days, not merely traded ones. Shape
    validation mirrors `RuleShapeValidation`'s own `_refuses` pattern; the live wiring (`account_state`'s
    `inactivity_days` -> `days_since_last_trade` fact, and `halt_check` propagation) is driven through the
    REAL `the5ers-high-stakes-step1` profile rather than a second synthetic fixture, so these tests prove the
    shipped registry entry actually behaves as declared."""

    def _refuses(self, **rule_overrides):
        bad = copy.deepcopy(PROP_RULES); bad.update(rule_overrides)
        with self.assertRaises(ValueError) as cm:
            AP._validate(_registry({"p": dict(PROP, rules=bad)}))
        return str(cm.exception)

    # ---- _validate_rules shape checks

    def test_a_zero_count_is_refused(self):
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": 0, "profit_threshold_pct": 0.005})
        self.assertIn("min_profitable_days.count", msg)

    def test_a_negative_count_is_refused(self):
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": -1, "profit_threshold_pct": 0.005})
        self.assertIn("min_profitable_days.count", msg)

    def test_a_non_integer_count_is_refused(self):
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": 3.5, "profit_threshold_pct": 0.005})
        self.assertIn("min_profitable_days.count", msg)

    def test_a_boolean_count_is_refused(self):
        """bool is a subclass of int in Python -- True/False must not silently pass as 1/0."""
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": True, "profit_threshold_pct": 0.005})
        self.assertIn("min_profitable_days.count", msg)

    def test_a_zero_profit_threshold_pct_is_refused(self):
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": 3, "profit_threshold_pct": 0.0})
        self.assertIn("profit_threshold_pct", msg)
        self.assertIn("FRACTION", msg)

    def test_a_profit_threshold_pct_above_one_is_refused(self):
        """Same discipline as every other pct field: a `5` typed for '5 %' must not become a 500 % rule."""
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": 3, "profit_threshold_pct": 5})
        self.assertIn("profit_threshold_pct", msg)

    def test_a_negative_profit_threshold_pct_is_refused(self):
        msg = self._refuses(min_trading_days=None,
                            min_profitable_days={"count": 3, "profit_threshold_pct": -0.005})
        self.assertIn("profit_threshold_pct", msg)

    def test_declaring_both_min_trading_days_and_min_profitable_days_is_refused(self):
        """Two different readings of 'how many days' on one profile leaves a reader to guess which the fund
        actually enforces."""
        msg = self._refuses(min_trading_days=5,   # PROP_RULES' own value; left in place on purpose
                            min_profitable_days={"count": 3, "profit_threshold_pct": 0.005})
        self.assertIn("BOTH min_trading_days", msg)

    def test_a_missing_count_or_threshold_is_refused(self):
        msg = self._refuses(min_trading_days=None, min_profitable_days={"count": 3})
        self.assertIn("profit_threshold_pct", msg)

    def test_a_well_formed_min_profitable_days_validates(self):
        rules = dict(PROP_RULES, min_trading_days=None,
                    min_profitable_days={"count": 3, "profit_threshold_pct": 0.005})
        AP._validate(_registry({"p": dict(PROP, rules=rules)}))   # must not raise

    # ---- account_state() / halt_check() wiring, driven through the REAL the5ers profile

    @classmethod
    def setUpClass(cls):
        cls.the5ers = AP.get("the5ers-high-stakes-step1")

    def _facts(self, **over):
        facts = {"equity": 100_000.0, "day_start_equity": 100_000.0, "peak_equity": 100_000.0,
                 "consec_losses": 0}
        facts.update(over)
        return facts

    def test_inactivity_below_the_threshold_is_not_a_breach(self):
        out = AP.account_state(self.the5ers, self._facts(days_since_last_trade=29))
        self.assertEqual([f for f in out if f["rule"] == "inactivity-30-days"], [])
        self.assertIsNone(AP.halt_check(self.the5ers, self._facts(days_since_last_trade=29))[0])

    def test_inactivity_at_the_threshold_breaches(self):
        out = [f for f in AP.account_state(self.the5ers, self._facts(days_since_last_trade=30))
              if f["rule"] == "inactivity-30-days"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["state"], "HALT")

    def test_inactivity_missing_the_fact_is_UNKNOWN_not_a_silent_pass(self):
        """CLAUDE.md §20: an unevaluable rule must report UNKNOWN, never OK -- 'the fact was not supplied' is
        not 'the account is active'."""
        out = [f for f in AP.account_state(self.the5ers, self._facts())   # no days_since_last_trade key
              if f["rule"] == "inactivity-30-days"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["state"], AP.UNKNOWN)

    def test_an_unknown_inactivity_reading_is_never_treated_as_a_halt(self):
        """Mirrors test_an_unevaluable_account_rule_is_UNKNOWN_and_never_a_halt: 'the fact was not supplied' is
        never read as 'the account is down' -- halt_check only ever surfaces HALT/HUMAN/BLOCK_ENTRY findings
        (its own docstring: "rules about the ACCOUNT's survival"), so a pure-UNKNOWN account_state() -- as
        here, every OTHER survival fact supplied and fine -- correctly comes back (None, None) from halt_check
        itself; the UNKNOWN is still visible to a caller that inspects account_state() directly (the
        previous test)."""
        self.assertEqual(AP.halt_check(self.the5ers, self._facts()), (None, None))

    def test_a_breach_propagates_through_halt_check(self):
        act, why = AP.halt_check(self.the5ers, self._facts(days_since_last_trade=45))
        self.assertEqual(act, AP.HALT)
        self.assertIn("30", why)
        self.assertIn("inactivity days", why)


class Lookup(unittest.TestCase):
    def test_each_venue_resolves_to_exactly_one_demo_account(self):
        self.assertEqual(AP.for_venue("futures")["id"], "pilot-binance-futures-testnet")
        self.assertEqual(AP.for_venue("mt5")["id"], "pilot-mt5-demo")

    def test_real_money_has_no_declared_account_and_therefore_refuses(self):
        """§51, one more lock: switching execution.environment to "real" cannot place an order until somebody
        has written that account's rules down."""
        with self.assertRaises(ValueError) as cm:
            AP.for_venue("futures", "real")
        self.assertIn("0 account profiles", str(cm.exception))

    def test_an_unknown_venue_refuses_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            AP.for_venue("kraken")


class DerivedCaps(unittest.TestCase):
    def test_the_crypto_book_is_one_slot_per_orderable_symbol(self):
        self.assertEqual(AP.max_positions(AP.for_venue("futures")), len(I.execution("crypto")))

    def test_the_mt5_book_counts_every_market_routed_to_that_account(self):
        """The A1 defect: the old constant was len(CFD) as a literal, so when forex (2026-09-17..2026-09-27)
        routed to the SAME MT5 account, the seven FX majors were not counted by the cap that is supposed to
        bound that account's book. forex is gone now (instruments.json history), but the derivation must still
        sum every market whose unattended venue is this profile's venue -- proven here by cfd being the ONLY
        such market today, so the book equals exactly cfd's execution count with nothing left uncounted and
        nothing double-counted."""
        prof = AP.for_venue("mt5")
        syms = AP.tradeable_symbols(prof)
        self.assertEqual(AP.max_positions(prof), len(syms))
        self.assertEqual(sorted(syms), sorted(I.execution("cfd")))

    def test_the_book_never_includes_an_analysis_only_symbol(self):
        """The execution list is the orderable subset; the allowlist is wider. A cap derived from the wrong
        one would permit more concurrent risk than there are tradeable instruments."""
        for venue in ("futures", "mt5"):
            orderable = {s for m in I.MARKETS for s in I.execution(m)}
            self.assertTrue(set(AP.tradeable_symbols(AP.for_venue(venue))) <= orderable)

    def test_a_fixed_cap_is_honoured_verbatim(self):
        self.assertEqual(AP.max_positions(dict(PROP, id="p")), 2)

    def test_leverage_comes_from_the_account_not_the_engine(self):
        self.assertEqual(AP.max_leverage(AP.for_venue("futures")), 3)
        self.assertIsNone(AP.max_leverage(AP.for_venue("mt5")),
                          "this platform sets no leverage on MT5; the broker's own applies")


class EntryGate(unittest.TestCase):
    def setUp(self):
        self.prof = AP.for_venue("futures")

    def _states(self, findings):
        return {f["rule"]: f["state"] for f in findings}

    def test_an_ordinary_signal_passes(self):
        self.assertEqual(AP.entry_gate(self.prof, {"open_positions": 0, "trades_today": 0}), [])

    def test_a_full_book_blocks(self):
        cap = AP.max_positions(self.prof)
        out = self._states(AP.entry_gate(self.prof, {"open_positions": cap, "trades_today": 0}))
        self.assertEqual(out["max_positions"], AP.BLOCK_ENTRY)

    def test_one_slot_short_of_the_cap_still_passes(self):
        cap = AP.max_positions(self.prof)
        self.assertEqual(AP.entry_gate(self.prof, {"open_positions": cap - 1, "trades_today": 0}), [])

    def test_the_daily_entry_cap_blocks(self):
        out = self._states(AP.entry_gate(self.prof, {"open_positions": 0, "trades_today": 3}))
        self.assertEqual(out["max_trades_per_day_per_symbol"], AP.BLOCK_ENTRY)

    def test_a_missing_input_is_UNKNOWN_and_UNKNOWN_blocks(self):
        """Never silently OK. This is §20's rule applied to account state."""
        out = self._states(AP.entry_gate(self.prof, {}))
        self.assertEqual(out["max_positions"], AP.UNKNOWN)
        self.assertEqual(out["max_trades_per_day_per_symbol"], AP.UNKNOWN)
        self.assertIn(AP.UNKNOWN, AP.BLOCKING)

    def test_objectives_are_never_entry_gates(self):
        """Reaching a profit target must not stop an account from trading."""
        prof = dict(PROP, id="p")
        rules = [f["rule"] for f in AP.entry_gate(prof, {"open_positions": 0, "trades_today": 0,
                                                         "at": "2026-09-18T14:00:00Z",
                                                         "holding_overnight": False,
                                                         "holding_over_weekend": False,
                                                         "news_state": "CLEAR"})]
        self.assertNotIn("profit_target", rules)
        self.assertNotIn("min_trading_days", rules)


class PropChallengeRulesActuallyRun(unittest.TestCase):
    """Every rule shape the registry supports, driven through the real evaluators."""

    @classmethod
    def setUpClass(cls):
        AP._validate(_registry({"prop-x": PROP}))       # the fixture is a LEGAL profile or these tests lie
        cls.prof = dict(PROP, id="prop-x")

    def _clear_facts(self, **over):
        facts = {"open_positions": 0, "trades_today": 0, "at": "2026-09-18T14:00:00Z",
                 "holding_overnight": False, "holding_over_weekend": False, "news_state": "CLEAR"}
        facts.update(over)
        return facts

    def test_inside_an_allowed_session_the_entry_passes(self):
        self.assertEqual(AP.entry_gate(self.prof, self._clear_facts()), [])

    def test_outside_the_allowed_sessions_the_entry_is_blocked(self):
        out = AP.entry_gate(self.prof, self._clear_facts(at="2026-09-18T02:00:00Z"))   # asia
        self.assertEqual([f["state"] for f in out if f["rule"] == "session_restrictions"], [AP.BLOCK_ENTRY])

    def test_an_overnight_hold_is_blocked_when_the_account_forbids_it(self):
        out = AP.entry_gate(self.prof, self._clear_facts(holding_overnight=True))
        self.assertEqual([f["rule"] for f in out], ["overnight_restrictions"])

    def test_a_weekend_hold_is_blocked_when_the_account_forbids_it(self):
        out = AP.entry_gate(self.prof, self._clear_facts(holding_over_weekend=True))
        self.assertEqual([f["rule"] for f in out], ["weekend_restrictions"])

    def test_an_unavailable_news_state_blocks_an_account_that_declares_a_news_rule(self):
        out = AP.entry_gate(self.prof, self._clear_facts(news_state="UNAVAILABLE"))
        self.assertEqual([f["rule"] for f in out], ["news_restrictions"])

    def test_the_fixed_position_cap_binds_before_the_full_book_would(self):
        out = AP.entry_gate(self.prof, self._clear_facts(open_positions=2))
        self.assertEqual([f["state"] for f in out if f["rule"] == "max_positions"], [AP.BLOCK_ENTRY])

    def test_max_total_drawdown_measured_against_the_initial_balance(self):
        act, why = AP.halt_check(self.prof, {"equity": 89_999.0})
        self.assertEqual(act, AP.HALT)
        self.assertIn("initial_balance", why)
        self.assertIsNone(AP.halt_check(self.prof, {"equity": 90_001.0, "day_start_equity": 90_001.0,
                                                    "peak_equity": 90_001.0, "consec_losses": 0})[0])

    def test_max_daily_loss_measured_against_the_day_start(self):
        act, why = AP.halt_check(self.prof, {"equity": 94_000.0, "day_start_equity": 100_000.0,
                                             "peak_equity": 100_000.0, "consec_losses": 0})
        self.assertEqual(act, AP.HALT)
        self.assertIn("daily loss", why)

    def test_trailing_drawdown_measured_against_the_peak(self):
        act, why = AP.halt_check(self.prof, {"equity": 105_000.0, "day_start_equity": 105_000.0,
                                             "peak_equity": 110_000.0, "consec_losses": 0})
        self.assertEqual(act, AP.HALT)
        self.assertIn("trailing drawdown", why)

    def test_a_loss_streak_ends_the_challenge_at_the_declared_threshold(self):
        base = {"equity": 100_000.0, "day_start_equity": 100_000.0, "peak_equity": 100_000.0}
        self.assertIsNone(AP.halt_check(self.prof, dict(base, consec_losses=2))[0])
        act, why = AP.halt_check(self.prof, dict(base, consec_losses=3))
        self.assertEqual(act, AP.HALT)
        self.assertIn("consecutive losses", why)

    def test_a_consistency_rule_fires_on_a_lopsided_profit_distribution(self):
        base = {"equity": 100_000.0, "day_start_equity": 100_000.0, "peak_equity": 100_000.0,
                "consec_losses": 0}
        even = dict(base, profit_by_day={"2026-09-14": 250, "2026-09-15": 250, "2026-09-16": 250,
                                         "2026-09-17": 250})
        self.assertIsNone(AP.halt_check(self.prof, even)[0])
        lopsided = dict(base, profit_by_day={"2026-09-14": 900, "2026-09-15": 100})
        act, why = AP.halt_check(self.prof, lopsided)
        self.assertEqual(act, AP.BLOCK_ENTRY)
        self.assertIn("2026-09-14", why)

    def test_a_consistency_rule_with_no_profit_yet_is_not_a_breach(self):
        out = AP.account_state(self.prof, {"equity": 100_000.0, "day_start_equity": 100_000.0,
                                           "peak_equity": 100_000.0, "consec_losses": 0,
                                           "profit_by_day": {"2026-09-14": -100.0}})
        self.assertEqual([f for f in out if f["rule"] == "best-day"], [])

    def test_an_unevaluable_account_rule_is_UNKNOWN_and_never_a_halt(self):
        """"I could not read the balance" is not "the account is down 10 %". UNKNOWN must block entries and
        must NOT write the kill switch."""
        states = [f["state"] for f in AP.account_state(self.prof, {})]
        self.assertTrue(states, "an account with declared rules and no facts reported nothing at all")
        self.assertEqual(set(states), {AP.UNKNOWN})
        self.assertNotEqual(AP.halt_check(self.prof, {})[0], AP.HALT)

    def test_objectives_report_progress_without_gating(self):
        facts = {"equity": 108_000.0, "trading_days": 5}
        by = {o["objective"]: o for o in AP.objectives(self.prof, facts)}
        self.assertEqual(by["profit_target"]["state"], "REACHED")
        self.assertEqual(by["min_trading_days"]["state"], "REACHED")
        by2 = {o["objective"]: o for o in AP.objectives(self.prof, {"equity": 104_000.0, "trading_days": 2})}
        self.assertEqual(by2["profit_target"]["state"], "OPEN")
        self.assertEqual(by2["min_trading_days"]["state"], "OPEN")
        self.assertEqual(by2["profit_target"]["progress"], 0.5)

    def test_an_objective_with_no_facts_is_UNKNOWN_not_zero(self):
        by = {o["objective"]: o for o in AP.objectives(self.prof, {})}
        self.assertEqual(by["profit_target"]["state"], AP.UNKNOWN)
        self.assertEqual(by["min_trading_days"]["state"], AP.UNKNOWN)


class NewsTightening(unittest.TestCase):
    """§33 news restrictions sit ON TOP of the §24-§32 calendar policy and may only tighten it."""

    def setUp(self):
        import event_risk as ER
        self.cal = {"policy": {"pre_minutes": 10, "post_minutes": 10,
                               "by_impact": {i: {"restricted": i == "HIGH"} for i in ER.IMPACTS}}}

    def test_an_account_with_no_news_rule_changes_nothing(self):
        for venue in ("futures", "mt5"):
            self.assertIs(AP.tighten_calendar(AP.for_venue(venue), self.cal), self.cal)

    def test_longer_buffers_and_more_impacts_are_applied(self):
        out = AP.tighten_calendar(dict(PROP, id="p"), self.cal)
        self.assertEqual(out["policy"]["pre_minutes"], 30)
        self.assertEqual(out["policy"]["post_minutes"], 30)
        self.assertTrue(out["policy"]["by_impact"]["MEDIUM"]["restricted"])
        self.assertTrue(out["policy"]["by_impact"]["HIGH"]["restricted"])
        self.assertEqual(self.cal["policy"]["pre_minutes"], 10, "the platform policy was mutated in place")

    def test_a_shorter_buffer_is_refused(self):
        rules = copy.deepcopy(PROP_RULES); rules["news_restrictions"] = {"impacts": ["HIGH"], "pre_minutes": 1}
        with self.assertRaises(ValueError) as cm:
            AP.tighten_calendar(dict(PROP, id="p", rules=rules), self.cal)
        self.assertIn("only TIGHTEN", str(cm.exception))

    def test_dropping_an_impact_the_platform_restricts_is_refused(self):
        """Otherwise an account opts out of HIGH-impact event risk by listing only MEDIUM."""
        rules = copy.deepcopy(PROP_RULES); rules["news_restrictions"] = {"impacts": ["MEDIUM"]}
        with self.assertRaises(ValueError) as cm:
            AP.tighten_calendar(dict(PROP, id="p", rules=rules), self.cal)
        self.assertIn("UNRESTRICT", str(cm.exception))


class RunnerWiring(unittest.TestCase):
    """The order engine reads the profile; the constants it replaced must not creep back."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        cls.sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.sr)

    def test_the_account_constants_are_gone_from_the_order_engine(self):
        for name in ("MAX_OPEN", "MAX_TRADES_PER_DAY", "EQUITY_HALT_FRAC", "CONSEC_LOSS_HALT", "LEVERAGE"):
            self.assertFalse(hasattr(self.sr, name),
                             f"{name} is back in strategy-runner.py; account rules live in "
                             f"docs/architecture/account-profiles.json (CLAUDE.md §33)")

    def test_each_venue_resolves_to_its_account_profile(self):
        self.assertEqual(self.sr.profile("futures")["id"], "pilot-binance-futures-testnet")
        self.assertEqual(self.sr.profile("mt5")["id"], "pilot-mt5-demo")

    def test_leverage_is_read_from_the_account(self):
        self.assertEqual(self.sr.futures_leverage(), AP.max_leverage(AP.for_venue("futures")))

    def test_the_values_the_engine_used_to_hold_are_unchanged(self):
        """This migration moved four numbers; it did not change any of them."""
        fut, mt5 = AP.for_venue("futures"), AP.for_venue("mt5")
        self.assertEqual(AP.rule(fut, "max_total_drawdown")["pct"], 0.15)
        self.assertEqual(AP.max_trades_per_day(fut), 3)
        self.assertEqual(AP.max_leverage(fut), 3)
        self.assertEqual(AP.rule(fut, "custom_failure_conditions")[0]["threshold"], 5)
        self.assertEqual(AP.max_positions(fut), 9)
        self.assertEqual(AP.rule(mt5, "max_total_drawdown")["pct"], 0.15)
        self.assertEqual(AP.max_trades_per_day(mt5), 3)

    def test_the_engine_does_not_restate_the_risk_ceiling(self):
        self.assertEqual(self.sr.RISK_CEILING, TE.MAX_RISK_PCT)
        self.assertEqual(AP.effective_risk_pct(AP.for_venue("futures")), TE.MAX_RISK_PCT)


class AccountLimitsOnTheOrderPath(unittest.TestCase):
    """The gate, driven through the runner's real `tick()` rather than through `entry_gate()` directly.

    A unit test of the evaluator proves the rule computes. It does not prove the ORDER PATH consults it --
    which is the half that matters, and the half that was previously satisfied by two literals in this file's
    own source. These drive a full dry tick with a fabricated signal and read the `signal` log the runner
    writes before it places anything."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        cls.sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.sr)

    def _tick(self, state):
        """One DRY tick (no network, no orders) returning the `signal` log rows."""
        import json
        import tempfile
        sr = self.sr
        sig = {"time": "2026-09-18T00:00:00Z", "mss_time": "2026-09-18T00:00:00Z", "entry": 100.0,
               "stop": 99.0, "target": 110.0, "r_planned": 10.0, "vol_type": 1, "side": "long"}
        setup = {"id": "t", "market": "crypto", "symbols": ["BTCUSDT"], "tf": "15m", "method": "ICT",
                 "htf": False, "mgmt": "none", "execution": "futures"}
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]},
                           "cfd": {"enabled": False, "instruments": []}},
               "execution": {"environment": "demo"}}
        tmps = []

        def tmp(obj):
            fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(obj, fh); fh.close(); tmps.append(fh.name); return fh.name

        cfg_p, sel_p, state_p = tmp(cfg), tmp({"setups": [setup]}), tmp(state)
        old = {k: getattr(sr, k) for k in ("AUTOMATION_CONFIG", "SELECTION", "STATE", "STOP", "automation_gate",
                                           "fetch_candles", "setups", "htf_pass", "event_blackout", "log",
                                           "due", "allowed_methods", "place_limit", "place_market",
                                           "manage_position", "manage_pending", "min_notional")}
        logs = []
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_p, sel_p, state_p
        sr.STOP = state_p + ".STOP"
        sr.automation_gate = lambda: None
        sr.fetch_candles = lambda *a, **k: [{"time": "2026-09-18T00:00:00Z", "open": 100.0, "high": 101.0,
                                             "low": 99.0, "close": 100.0, "volume": 1.0} for _ in range(400)]
        sr.setups = lambda *a, **k: [dict(sig)]
        sr.htf_pass = lambda *a, **k: True
        sr.event_blackout = lambda *a, **k: None
        sr.due = lambda *a, **k: True
        sr.allowed_methods = lambda *a, **k: ("ICT",)
        sr.place_limit = lambda *a, **k: None
        sr.place_market = lambda *a, **k: None
        sr.manage_position = lambda *a, **k: None
        sr.manage_pending = lambda *a, **k: ("waiting", None, None, None)
        # §36 step 12 now runs the sizing refusal inside the tick. Stubbed so the harness tests the
        # gate it means to test rather than whether the exchange answered a filters query.
        sr.min_notional = lambda *a, **k: 5.0
        sr.log = lambda kind, **kw: logs.append((kind, kw))
        old_load, sr.ER.load = sr.ER.load, FC.fresh_load    # the §36 step-3 precheck reads the calendar itself
        try:
            sr.tick(live=False, tick_time=sr.now(), ignore_gate=True)
        finally:
            sr.ER.load = old_load
            for k, v in old.items():
                setattr(sr, k, v)
            for p in tmps:
                os.unlink(p)
        return [kw for kind, kw in logs if kind == "signal"]

    def _state(self, positions=0, trades_today=0):
        sr = self.sr
        pos = {f"SYM{i}": {"execution": "futures", "tf": "15m"} for i in range(positions)}
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        return {"started": "2026-01-01T00:00:00Z", "positions": pos, "pending": {}, "seen": [],
                "day": today, "trades_today": {"BTCUSDT": trades_today} if trades_today else {},
                "errors": 0, "halted": None, "last_tick": None, "equity_basis": "equity",
                "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}

    def test_a_clear_signal_is_accepted(self):
        rows = self._tick(self._state())
        self.assertTrue(rows, "the harness produced no signal at all -- the rest of this class proves nothing")
        self.assertTrue(rows[0]["ok"], rows[0]["reasons"])

    def test_a_full_book_refuses_the_entry_on_the_order_path(self):
        cap = AP.max_positions(AP.for_venue("futures"))
        rows = self._tick(self._state(positions=cap))
        self.assertTrue(rows)
        self.assertFalse(rows[0]["ok"])
        self.assertIn(f"đủ {cap} vị thế (futures)", rows[0]["reasons"])

    def test_one_slot_short_of_the_book_still_passes(self):
        cap = AP.max_positions(AP.for_venue("futures"))
        rows = self._tick(self._state(positions=cap - 1))
        self.assertTrue(rows[0]["ok"], rows[0]["reasons"])

    def test_the_daily_entry_cap_refuses_the_entry_on_the_order_path(self):
        rows = self._tick(self._state(trades_today=AP.max_trades_per_day(AP.for_venue("futures"))))
        self.assertIn("đủ lệnh trong ngày", rows[0]["reasons"])

    def test_a_session_restriction_blocks_on_the_order_path(self):
        """A4 -- decision-order.json step 4 used to be tr.skip()'d unconditionally; a declared
        session_restrictions rule now actually gates. The harness's signal time (2026-09-18T00:00:00Z) is the
        'asia' session; a profile allowing only 'london' must refuse it at step 4, before account_constraints."""
        sr = self.sr
        prof = dict(AP.for_venue("futures"))
        prof["rules"] = dict(prof["rules"],
                             session_restrictions={"allowed_sessions": ["london"], "action": "BLOCK_ENTRY"})
        old = sr._PROFILES["futures"]
        sr._PROFILES["futures"] = prof
        try:
            rows = self._tick(self._state())
        finally:
            sr._PROFILES["futures"] = old
        self.assertTrue(rows)
        self.assertFalse(rows[0]["ok"], rows[0]["reasons"])
        self.assertTrue(any("london" in r for r in rows[0]["reasons"]), rows[0]["reasons"])
        self.assertIn("4:session=BLOCK_ENTRY", rows[0]["decision_trace"])

    def test_no_session_restriction_reports_ok_at_step_four(self):
        rows = self._tick(self._state())
        self.assertTrue(rows)
        self.assertIn("4:session", rows[0]["decision_trace"])
        self.assertNotIn("4:session=", rows[0]["decision_trace"],
                         "an OK outcome carries no '=OUTCOME' suffix in Trace.as_log()")

    def test_the_cap_the_order_path_applies_is_the_one_the_registry_declares(self):
        """Not just 'some cap fired': the number in the refusal is the account's, so a registry edit moves it."""
        cap = AP.max_positions(AP.for_venue("futures"))
        self.assertEqual(cap, len(I.execution("crypto")))
        rows = self._tick(self._state(positions=cap - 1))
        self.assertTrue(rows[0]["ok"])
        rows = self._tick(self._state(positions=cap))
        self.assertFalse(rows[0]["ok"])


class PropChallengeResearchProfiles(unittest.TestCase):
    """A2 (docs/plans/2026-09-18-close-feature-gaps.md §0.1) -- FTMO Challenge Phase 1 and The5ers High Stakes
    Step 1, for RESEARCH only. Loadable by id; never an order-path profile."""

    def test_both_ids_load_as_prop_challenge(self):
        for pid in ("ftmo-challenge-phase1", "the5ers-high-stakes-step1"):
            prof = AP.get(pid)
            self.assertEqual(prof["context_type"], "PROP_CHALLENGE", pid)
            self.assertEqual(prof["environment"], "research", pid)
            self.assertEqual(prof["venue"], "mt5", pid)

    def test_for_venue_mt5_demo_is_still_unique_and_unaffected(self):
        self.assertEqual(AP.for_venue("mt5", "demo")["id"], "pilot-mt5-demo")

    def test_for_venue_refuses_the_research_environment_outright(self):
        with self.assertRaises(ValueError):
            AP.for_venue("mt5", "research")

    def test_the_two_prop_profiles_share_a_venue_without_tripping_uniqueness(self):
        """They would collide under the plain (venue, environment) uniqueness check; `research` is declared
        unroutable, which is what lets both exist (CLAUDE.md §33 -- do not assume all CFD accounts match)."""
        ftmo, the5ers = AP.get("ftmo-challenge-phase1"), AP.get("the5ers-high-stakes-step1")
        self.assertEqual(ftmo["venue"], the5ers["venue"])
        self.assertEqual(ftmo["environment"], the5ers["environment"])


class Snapshotting(unittest.TestCase):
    def test_a_profile_serialises_with_its_rules_and_what_was_derived(self):
        """§11: a research run must be able to record WHICH account rules were in force."""
        snap = AP.snapshot(AP.for_venue("futures"))
        self.assertEqual(snap["profile_id"], "pilot-binance-futures-testnet")
        self.assertEqual(snap["registry_version"], AP.VERSION)
        for key in AP.RULE_KEYS:
            self.assertIn(key, snap["rules"])
        self.assertEqual(snap["derived"]["max_positions"], 9)
        self.assertEqual(snap["derived"]["effective_risk_pct"], TE.MAX_RISK_PCT)

    def test_the_snapshot_carries_no_commentary_keys(self):
        snap = AP.snapshot(AP.for_venue("mt5"))
        self.assertFalse([k for k in snap["rules"] if k.startswith("_")])


if __name__ == "__main__":
    unittest.main()


class OwnershipIsTheRiskPoolBoundary(unittest.TestCase):
    """docs/plans/2026-09-19-multi-account.md §0.2. Customers rent a methodology and hand over their own
    account, so "how concentrated is this bet" is a question about one OWNER's accounts. scripts/exposure.py
    refuses on an owner's own concentration and only reports the house-wide count."""

    def test_an_undeclared_account_is_its_own_pool(self):
        """The safe default: it cannot dilute anybody else's cap, and we do not claim to know whose it is."""
        for pid in AP.PROFILES:
            prof = AP.get(pid)
            if "owner" not in prof:
                self.assertEqual(AP.owner_of(prof), pid)
                break
        else:
            self.skipTest("every shipped profile declares an owner")

    def test_a_declared_owner_is_used(self):
        prof = dict(AP.get(next(iter(AP.PROFILES))), owner="cust-42")
        self.assertEqual(AP.owner_of(prof), "cust-42")

    def test_an_empty_owner_is_refused_rather_than_silently_meaning_the_account_id(self):
        base = copy.deepcopy(PROP)
        for bad in ("", "   ", 7, None):
            with self.subTest(owner=bad), self.assertRaises(ValueError):
                AP._validate(_registry({"p": dict(base, owner=bad)}))

    def test_a_real_owner_id_passes_validation(self):
        AP._validate(_registry({"p": dict(copy.deepcopy(PROP), owner="cust-42")}))
