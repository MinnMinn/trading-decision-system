"""The account<->setup table: who rents which methodology, on which version, at what risk.

docs/plans/2026-09-19-multi-account.md §0.1. The business is customers renting a methodology and handing over
their own account (user, 2026-09-19), so one account runs several setups and one setup serves many accounts.
Every test below is about a way that relation can be recorded WRONG in a way nobody notices until somebody's
money is trading on rules they did not agree to.
"""
import copy
import datetime
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _mod():
    spec = importlib.util.spec_from_file_location("mandates", os.path.join(ROOT, "scripts", "mandates.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MD = _mod()
import account_profile as AP
import trading_env as TE

ACCOUNT = next(pid for pid, p in AP.PROFILES.items()
               if p["environment"] not in AP.UNROUTABLE_ENVIRONMENTS)
SETUPS = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-selection.json"),
                        encoding="utf-8"))["setups"]
SETUP = SETUPS[0]["id"]
VERSION = SETUPS[0].get("rule_version")

ROW = {"id": "m-1", "account": ACCOUNT, "setup": SETUP, "setup_version": VERSION,
       "state": "ACTIVE", "started_at": "2026-01-01", "ended_at": None, "risk_pct": 0.005}


def _reg(rows, cap=10):
    return {"version": 1, "states": list(MD.STATES), "max_accounts_per_method_market": cap,
            "mandates": rows}


class TheShippedTableIsValid(unittest.TestCase):
    def test_it_loads_and_an_empty_table_is_a_legal_state(self):
        """Empty is not missing. There are no customers yet, and the reader must answer over zero rows rather
        than treat that as a configuration error."""
        self.assertIsInstance(MD.MANDATES, list)
        self.assertEqual(MD.accounts(), sorted({m["account"] for m in MD.MANDATES
                                                if m["state"] in MD.TRADEABLE}))

    def test_the_state_vocabulary_has_one_source_and_contains_the_tradeable_one(self):
        for t in MD.TRADEABLE:
            self.assertIn(t, MD.STATES)

    def test_paused_is_not_tradeable(self):
        """A paused mandate may still have open positions, which is why it is not ENDED -- but it is not
        permission to take a new signal either."""
        self.assertIn("PAUSED", MD.STATES)
        self.assertNotIn("PAUSED", MD.TRADEABLE)


class BothEndsOfEveryRowMustExist(unittest.TestCase):
    def test_a_mandate_naming_no_account_is_refused(self):
        with self.assertRaises(MD.RegistryError) as cm:
            MD._validate(_reg([dict(ROW, account="nobody")]))
        self.assertIn("trades nobody's money", str(cm.exception))

    def test_a_mandate_naming_no_setup_is_refused(self):
        with self.assertRaises(MD.RegistryError):
            MD._validate(_reg([dict(ROW, setup="not-a-setup")]))

    def test_an_unknown_state_is_refused(self):
        with self.assertRaises(MD.RegistryError):
            MD._validate(_reg([dict(ROW, state="RUNNING")]))

    def test_duplicate_ids_are_refused(self):
        with self.assertRaises(MD.RegistryError):
            MD._validate(_reg([dict(ROW), dict(ROW)]))


class RiskMayOnlyBeTightened(unittest.TestCase):
    def test_a_mandate_may_agree_to_less_risk(self):
        MD._validate(_reg([dict(ROW, risk_pct=TE.MAX_RISK_PCT / 2)]))

    def test_a_mandate_may_not_agree_to_more_than_the_platform_ceiling(self):
        with self.assertRaises(MD.RegistryError) as cm:
            MD._validate(_reg([dict(ROW, risk_pct=TE.MAX_RISK_PCT * 2)]))
        self.assertIn("never to more", str(cm.exception))

    def test_the_resolved_fraction_never_exceeds_the_accounts_own_ceiling(self):
        prof = AP.get(ACCOUNT)
        ceiling = AP.effective_risk_pct(prof)
        self.assertLessEqual(MD.risk_pct(dict(ROW, risk_pct=ceiling * 10)), ceiling)

    def test_no_agreed_fraction_falls_back_to_the_accounts_ceiling(self):
        prof = AP.get(ACCOUNT)
        self.assertEqual(MD.risk_pct(dict(ROW, risk_pct=None)), AP.effective_risk_pct(prof))


class TheVersionPinIsTheWholePoint(unittest.TestCase):
    """scripts/rank-setups.py rewrites pilot-selection.json in place -- four times on 2026-09-19 alone. The same
    setup id can mean different rules afterwards, so a customer's agreed version is recorded, not resolved."""

    def test_drift_is_reported_when_the_setup_moved_under_the_mandate(self):
        rows = MD._validate(_reg([dict(ROW, setup_version="oldversion00")]))
        saved = MD.MANDATES
        try:
            MD.MANDATES = rows
            d = MD.drift(at=datetime.date(2026, 6, 1))
            self.assertEqual(len(d), 1)
            self.assertEqual(d[0]["agreed"], "oldversion00")
            self.assertEqual(d[0]["current"], VERSION)
        finally:
            MD.MANDATES = saved

    def test_no_drift_when_the_pin_matches(self):
        rows = MD._validate(_reg([dict(ROW)]))
        saved = MD.MANDATES
        try:
            MD.MANDATES = rows
            self.assertEqual(MD.drift(at=datetime.date(2026, 6, 1)), [])
        finally:
            MD.MANDATES = saved

    def test_drift_reports_and_does_not_resolve(self):
        """A divergence must not quietly become 'now on the new version'; moving a customer is a decision."""
        src = open(os.path.join(ROOT, "scripts", "mandates.py"), encoding="utf-8").read()
        self.assertIn("Reported, never resolved", src)


class TheRelationIsManyToMany(unittest.TestCase):
    def test_one_account_can_hold_several_setups(self):
        if len(SETUPS) < 2:
            self.skipTest("selection has fewer than two setups")
        rows = MD._validate(_reg([
            dict(ROW, id="m-1", setup=SETUPS[0]["id"], setup_version=SETUPS[0].get("rule_version")),
            dict(ROW, id="m-2", setup=SETUPS[1]["id"], setup_version=SETUPS[1].get("rule_version"))]))
        saved = MD.MANDATES
        try:
            MD.MANDATES = rows
            self.assertEqual(len(MD.for_account(ACCOUNT, at=datetime.date(2026, 6, 1))), 2)
        finally:
            MD.MANDATES = saved

    def test_one_setup_can_serve_several_accounts(self):
        others = [pid for pid, p in AP.PROFILES.items()
                  if p["environment"] not in AP.UNROUTABLE_ENVIRONMENTS and pid != ACCOUNT]
        if not others:
            self.skipTest("registry has only one routable account")
        rows = MD._validate(_reg([dict(ROW, id="m-1"), dict(ROW, id="m-2", account=others[0])]))
        saved = MD.MANDATES
        try:
            MD.MANDATES = rows
            self.assertEqual(len(MD.for_setup(SETUP, at=datetime.date(2026, 6, 1))), 2)
        finally:
            MD.MANDATES = saved

    def test_two_live_mandates_for_the_same_pair_are_refused(self):
        """Otherwise "which rules is this account running for this setup" has two answers, and the pinned
        version is exactly what would differ between them."""
        with self.assertRaises(MD.RegistryError) as cm:
            MD._validate(_reg([dict(ROW, id="m-1"), dict(ROW, id="m-2")]))
        self.assertIn("both live", str(cm.exception))

    def test_an_ended_mandate_does_not_block_a_new_one_for_the_same_pair(self):
        """A returning customer gets a NEW mandate so the history of what they ran when stays readable."""
        MD._validate(_reg([dict(ROW, id="m-old", state="ENDED", ended_at="2026-03-01"),
                           dict(ROW, id="m-new", started_at="2026-03-02")]))


class DatesMustMakeSense(unittest.TestCase):
    def test_ending_before_starting_is_refused(self):
        with self.assertRaises(MD.RegistryError):
            MD._validate(_reg([dict(ROW, state="ENDED", started_at="2026-05-01", ended_at="2026-04-01")]))

    def test_ended_without_a_date_is_refused(self):
        with self.assertRaises(MD.RegistryError) as cm:
            MD._validate(_reg([dict(ROW, state="ENDED", ended_at=None)]))
        self.assertIn("whole content of that state", str(cm.exception))

    def test_a_tradeable_mandate_may_not_carry_an_end_date(self):
        with self.assertRaises(MD.RegistryError) as cm:
            MD._validate(_reg([dict(ROW, state="ACTIVE", ended_at="2026-04-01")]))
        self.assertIn("may not be tradeable", str(cm.exception))

    def test_a_mandate_that_has_not_started_yet_is_not_live(self):
        rows = MD._validate(_reg([dict(ROW, started_at="2026-12-31")]))
        saved = MD.MANDATES
        try:
            MD.MANDATES = rows
            self.assertEqual(MD.for_account(ACCOUNT, at=datetime.date(2026, 6, 1)), [])
        finally:
            MD.MANDATES = saved

    def test_a_malformed_date_is_refused(self):
        with self.assertRaises(MD.RegistryError):
            MD._validate(_reg([dict(ROW, started_at="last tuesday")]))


class OneListOneJsonOneReader(unittest.TestCase):
    def test_no_other_script_reads_the_mandates_file_directly(self):
        import re
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "scripts")):
            if "tests" in dirpath or "__pycache__" in dirpath:
                continue
            for f in files:
                if not f.endswith(".py") or f == "mandates.py":
                    continue
                src = open(os.path.join(dirpath, f), encoding="utf-8").read()
                self.assertNotRegex(src, r'open\([^)]*mandates\.json',
                                    f"{f} opens mandates.json directly; go through scripts/mandates.py")


if __name__ == "__main__":
    unittest.main()


class OneMethodOnOneMarketIsSharedByAtMostTenAccounts(unittest.TestCase):
    """User decision 2026-09-19. A cap on ATTACHMENT, answered before anybody has a position -- which is when
    a concentration limit is actionable. The alternative is telling the eleventh customer, mid-signal, that
    their order was refused."""

    def test_the_shipped_registry_declares_the_cap(self):
        d = json.load(open(os.path.join(ROOT, "docs", "architecture", "mandates.json"), encoding="utf-8"))
        self.assertEqual(d["max_accounts_per_method_market"], 10)
        self.assertIn("_max_accounts_per_method_market_why", d)

    def _rows(self, n, setup=SETUP, version=VERSION, start=1):
        return [dict(ROW, id=f"m-{i}", account=ACCOUNT if i == start else f"acc-{i:03d}",
                     setup=setup, setup_version=version) for i in range(start, start + n)]

    def _validate(self, rows, cap=10):
        # Accounts in these rows are synthetic, so the "account must exist" check is relaxed for this class
        # only -- what is under test is the COUNTING, not the existence rule (covered elsewhere).
        saved = dict(AP.PROFILES)
        try:
            for r in rows:
                AP.PROFILES.setdefault(r["account"], AP.PROFILES[ACCOUNT])
            return MD._validate(_reg(rows, cap=cap))
        finally:
            AP.PROFILES.clear(); AP.PROFILES.update(saved)

    def test_exactly_the_cap_is_allowed(self):
        self._validate(self._rows(10))

    def test_one_over_the_cap_is_refused_and_names_who_is_already_on_it(self):
        with self.assertRaises(MD.RegistryError) as cm:
            self._validate(self._rows(11))
        msg = str(cm.exception)
        self.assertIn("max_accounts_per_method_market", msg)
        self.assertIn("acc-", msg, "the refusal must name the accounts already sharing it")

    def test_a_second_setup_of_the_same_method_does_not_buy_a_second_allowance(self):
        """What is bounded is how many customers read the SAME market the SAME way, not how many rows exist."""
        same = [s for s in SETUPS if s["method"] == SETUPS[0]["method"] and s["market"] == SETUPS[0]["market"]
                and s["id"] != SETUPS[0]["id"]]
        if not same:
            self.skipTest("the selection has no second setup sharing a method and market")
        rows = self._rows(6) + self._rows(6, setup=same[0]["id"], version=same[0].get("rule_version"),
                                          start=100)
        with self.assertRaises(MD.RegistryError):
            self._validate(rows)

    def test_the_same_account_twice_on_one_method_counts_once(self):
        """The cap counts DISTINCT accounts: one customer on two setups of one method is one customer."""
        same = [s for s in SETUPS if s["method"] == SETUPS[0]["method"] and s["market"] == SETUPS[0]["market"]
                and s["id"] != SETUPS[0]["id"]]
        if not same:
            self.skipTest("the selection has no second setup sharing a method and market")
        rows = [dict(ROW, id="m-a", setup=SETUPS[0]["id"], setup_version=SETUPS[0].get("rule_version")),
                dict(ROW, id="m-b", setup=same[0]["id"], setup_version=same[0].get("rule_version"))]
        self._validate(rows, cap=1)          # one account, one allowance, two setups

    def test_a_different_market_has_its_own_allowance(self):
        other = [s for s in SETUPS if s["market"] != SETUPS[0]["market"]]
        if not other:
            self.skipTest("the selection covers only one market")
        rows = self._rows(10) + self._rows(10, setup=other[0]["id"],
                                           version=other[0].get("rule_version"), start=200)
        self._validate(rows)

    def test_an_ended_mandate_does_not_hold_a_slot(self):
        rows = self._rows(10) + [dict(ROW, id="m-old", account="acc-999", state="ENDED",
                                      ended_at="2026-02-01")]
        self._validate(rows)

    def test_a_missing_or_zero_cap_is_refused_rather_than_meaning_unlimited(self):
        for bad in (None, 0, -1, "10", 2.5):
            reg = {"version": 1, "states": list(MD.STATES), "mandates": []}
            if bad is not None:
                reg["max_accounts_per_method_market"] = bad
            with self.subTest(cap=bad), self.assertRaises(MD.RegistryError):
                MD._validate(reg)
