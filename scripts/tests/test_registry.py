"""ADR 0010 -- the account registry (docs/architecture/accounts.json, docs/architecture/setups.json, trading-systems.json
`books`), its validator (scripts/registry.py), the switch CLI (scripts/accounts.py) and the forward cycle's account order.

Every refusal below is a configuration the executor must never start on (CLAUDE.md §6, §15, §47, §51, §54-§55).

Run: python3 scripts/tests/test_registry.py
"""
import copy
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import registry as R  # noqa: E402
import trading_system as TS  # noqa: E402

_spec = importlib.util.spec_from_file_location("accounts_cli", os.path.join(ROOT, "scripts", "accounts.py"))
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)
_spec = importlib.util.spec_from_file_location("forward_cycle", os.path.join(ROOT, "scripts", "forward_cycle.py"))
FC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FC)

UTC = datetime.timezone.utc


def _json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


ACCOUNTS = _json(R.ACCOUNTS_PATH)
SETUPS = _json(R.SETUPS_PATH)
SYSTEMS = _json(TS.PATH)


def _write(doc):
    fd, p = tempfile.mkstemp(suffix=".json", dir=os.path.join(ROOT, "docs", "architecture"))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return p


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for p in self.paths:
            if os.path.exists(p):
                os.remove(p)

    def refuses(self, accounts=None, setups=None, expect=""):
        ap, sp = _write(accounts or ACCOUNTS), _write(setups or SETUPS)
        self.paths += [ap, sp]
        with self.assertRaises(R.RegistryError) as cm:
            R.validate(accounts_path=ap, setups_path=sp)
        self.assertIn(expect, str(cm.exception))


class TheShippedRegistry(unittest.TestCase):
    def test_it_validates(self):
        self.assertTrue(R.validate())

    def test_the_demo_account_runs_fvg_book_v2_now(self):
        r = R.resolve("ftmo-demo-01", datetime.datetime(2026, 10, 3, 12, tzinfo=UTC))
        self.assertEqual(r["system"]["id"], "fvg-book@v2")
        self.assertEqual(r["account"]["market"], "cfd")

    def test_history_is_point_in_time(self):
        self.assertEqual(R.active_assignment("ftmo-demo-01", datetime.datetime(2026, 10, 2, 23, 59, tzinfo=UTC))["id"],
                         "asg-0001")
        self.assertIsNone(R.active_assignment("ftmo-demo-01", datetime.datetime(2026, 10, 1, tzinfo=UTC)))

    def test_no_real_money_account_exists(self):
        self.assertTrue(all(a["real_money"] is False for a in R.ACCOUNTS.values()))

    def test_approved_versions_are_digest_locked(self):
        for book in TS.BOOKS.values():
            for v in book["versions"].values():
                if v["status"] != "DRAFT":
                    self.assertEqual(v["content_sha256"], TS.book_digest(v))


class AccountRefusals(_Tmp):
    def _acc(self, **kw):
        d = copy.deepcopy(ACCOUNTS)
        d["accounts"]["ftmo-demo-01"].update(kw)
        return d

    def test_two_live_assignments_on_one_account(self):
        d = copy.deepcopy(ACCOUNTS)
        d["assignments"][1]["effective_from"] = "2026-10-02T12:00:00Z"     # starts before asg-0001 ends
        self.refuses(d, expect="overlap")

    def test_a_trading_system_of_another_market(self):
        d = copy.deepcopy(ACCOUNTS)
        d["assignments"][1].update(trading_system="day", version="v1")
        self.refuses(d, expect="one account, one market")

    def test_real_money(self):
        self.refuses(self._acc(real_money=True), expect="real_money must be false")

    def test_a_secret_pasted_into_the_registry(self):
        self.refuses(self._acc(credential_ref="sk_live_" + "A1b2C3d4" * 6), expect="looks like a key")

    def test_a_broker_that_does_not_serve_the_market(self):
        self.refuses(self._acc(broker="binance_futures"), expect="does not serve market")

    def test_an_unknown_account_profile(self):
        self.refuses(self._acc(account_profile="nope"), expect="account_profile")

    def test_a_research_profile_cannot_be_traded(self):
        self.refuses(self._acc(account_profile="ftmo-challenge-phase1"), expect="unroutable")

    def test_two_mt5_accounts_on_one_bridge_channel(self):
        d = copy.deepcopy(ACCOUNTS)
        d["accounts"]["ftmo-demo-02"] = dict(d["accounts"]["ftmo-demo-01"])
        self.refuses(d, expect="bridge_channel")

    def test_a_second_mt5_account_requires_login_checks_on_both(self):
        d = copy.deepcopy(ACCOUNTS)
        d["accounts"]["ftmo-demo-02"] = dict(d["accounts"]["ftmo-demo-01"], bridge_channel="bridge-02")
        self.refuses(d, expect="login_ref")
        for aid, ref in (("ftmo-demo-01", "MT5_LOGIN_01"), ("ftmo-demo-02", "MT5_LOGIN_02")):
            d["accounts"][aid]["login_ref"] = ref
        ap, sp = _write(d), _write(SETUPS)
        self.paths += [ap, sp]
        self.assertTrue(R.validate(accounts_path=ap, setups_path=sp))

    def test_an_assignment_to_a_draft_version(self):
        d = copy.deepcopy(ACCOUNTS)
        with unittest.mock.patch.dict(TS.BOOKS["fvg-book"]["versions"]["v2"], {"status": "DRAFT"}):
            self.refuses(d, expect="DRAFT")

    def test_a_component_outside_the_symbol_map(self):
        sm = {"server": "x", "map": {"XAUUSD": "XAUUSD"}}
        p = _write(sm)
        self.paths.append(p)
        self.refuses(self._acc(symbol_map=os.path.relpath(p, ROOT)), expect="no broker symbol for US500")


class SetupRefusals(_Tmp):
    def test_an_approved_version_holding_a_watch_component(self):
        s = copy.deepcopy(SETUPS)
        s["setups"]["G9"]["evidence"]["XAUUSD"] = "WATCH"
        self.refuses(setups=s, expect="VALIDATED")

    def test_a_rule_ref_that_names_nothing(self):
        s = copy.deepcopy(SETUPS)
        s["setups"]["H7"]["rule_ref"] = "scripts/research/edge_f3.py ev_does_not_exist"
        self.refuses(setups=s, expect="defines no ev_does_not_exist")

    def test_evidence_on_an_instrument_off_the_allowlist(self):
        s = copy.deepcopy(SETUPS)
        s["setups"]["E5"]["evidence"]["EURUSD"] = "VALIDATED"
        self.refuses(setups=s, expect="allowlist")


class BookRefusals(unittest.TestCase):
    def _refuses(self, mutate, expect):
        d = copy.deepcopy(SYSTEMS)
        mutate(d["books"]["fvg-book"]["versions"]["v2"])
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(d, "trading-systems.json")
        self.assertIn(expect, str(cm.exception))

    def test_editing_an_approved_version_in_place(self):
        self._refuses(lambda v: v["components"][0]["params"].update(hold_bars=30), "immutable")

    def test_risk_above_the_ceiling(self):
        self._refuses(lambda v: v["risk"].update(risk_pct=0.02), "max_risk_pct")

    def test_an_unknown_throttle(self):
        self._refuses(lambda v: v["risk"].update(throttle="martingale"), "throttle")

    def test_a_duplicate_component(self):
        self._refuses(lambda v: v["components"].append(dict(v["components"][0])), "twice")


def _as_of(doc, iso):
    """The registry as it stood at `iso`: assignments that had started by then, the then-live row's end cleared. The real
    file is append-only history, so a fixture pinned to an instant stays valid after later (real) switches -- the 2026-10-03
    switch to fvg-book@v3 at 15:10 made every test that pinned NOW at 12:02 see a 'pending' assignment."""
    d = copy.deepcopy(doc)
    d["assignments"] = [a for a in d["assignments"] if a["effective_from"] <= iso]
    for a in d["assignments"]:
        if a["ended_at"] and a["ended_at"] > iso:
            a["ended_at"] = None
    return d


class Switch(unittest.TestCase):
    NOW = datetime.datetime(2026, 10, 3, 12, 2, tzinfo=UTC)
    ACC = _as_of(ACCOUNTS, "2026-10-03T12:02:00Z")

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _book(self, pending=(), opened=()):
        d = os.path.join(self.dir, "ftmo-demo-01")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "state.json"), "w") as fh:
            json.dump({"pending": list(pending), "open": list(opened)}, fh)

    def plan(self, target="fvg-book@v1", **kw):
        return A.plan_switch(copy.deepcopy(self.ACC), "ftmo-demo-01", target, kw.pop("reason", "test"),
                             now=self.NOW, accounts_dir=self.dir, **kw)

    def test_ends_the_live_row_and_appends_one_at_the_next_slot(self):
        doc = self.plan()
        rows = doc["assignments"]
        self.assertEqual(len(rows), len(self.ACC["assignments"]) + 1)
        self.assertEqual(rows[-2]["ended_at"], "2026-10-03T12:05:00Z")
        new = rows[-1]
        self.assertEqual((new["id"], new["version"], new["effective_from"], new["open_position_policy"]),
                         ("asg-0003", "v1", "2026-10-03T12:05:00Z", "DRAIN"))
        # every OTHER field of every earlier row is unchanged (append-only history)
        for old, now in zip(self.ACC["assignments"], rows):
            self.assertEqual({k: v for k, v in old.items() if k != "ended_at"},
                             {k: v for k, v in now.items() if k != "ended_at"})

    def test_switching_to_the_live_version_is_refused(self):
        with self.assertRaises(A.SwitchRefused):
            self.plan("fvg-book@v2")

    def test_block_refuses_while_positions_are_open(self):
        self._book(opened=[{"key": "x"}])
        with self.assertRaises(A.SwitchRefused) as cm:
            self.plan(policy="BLOCK")
        self.assertIn("BLOCK", str(cm.exception))
        self._book()
        self.assertEqual(self.plan(policy="BLOCK")["assignments"][-1]["open_position_policy"], "BLOCK")

    def test_a_switch_into_the_past_is_refused(self):
        with self.assertRaises(A.SwitchRefused):
            self.plan(at="2026-10-01T00:00:00Z")

    def test_one_pending_switch_at_a_time(self):
        doc = self.plan()
        with self.assertRaises(A.SwitchRefused):
            A.plan_switch(doc, "ftmo-demo-01", "fvg-book@v2", "again", now=self.NOW, accounts_dir=self.dir)

    def test_a_reason_is_required(self):
        with self.assertRaises(A.SwitchRefused):
            self.plan(reason=" ")

    def test_a_retired_target_is_refused_by_validation_and_nothing_is_written(self):
        # fvg-book v1 is RETIRED: planning succeeds, the full validation refuses, the file is untouched.
        target = _write(self.ACC)
        try:
            with open(target, encoding="utf-8") as fh:
                before = fh.read()
            with self.assertRaises(A.SwitchRefused) as cm:
                A.write_validated(self.plan(), path=target)
            self.assertIn("RETIRED", str(cm.exception))
            with open(target, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before)
        finally:
            os.remove(target)

    def test_a_valid_switch_is_written(self):
        target = _write(self.ACC)
        try:
            # an APPROVED target (v3, H7 + G9). Re-approving v1 by a patch no longer validates: its E5 components are
            # REJECTED since 2026-10-03 (docs/audits/2026-10-03-e5-lookahead-erratum.md), which the validator enforces.
            A.write_validated(self.plan("fvg-book@v3"), path=target)
            self.assertEqual(_json(target)["assignments"][-1]["version"], "v3")
        finally:
            os.remove(target)


class CycleOrder(unittest.TestCase):
    def test_deterministic_and_rotating(self):
        ids = [f"acc-{i}" for i in range(5)]
        t = datetime.datetime(2026, 10, 5, 9, 3, tzinfo=UTC)
        self.assertEqual(FC.tick_order(ids, t), FC.tick_order(ids, t + datetime.timedelta(minutes=1)))   # same slot
        firsts = {FC.tick_order(ids, t + datetime.timedelta(minutes=5 * k))[0] for k in range(60)}
        self.assertEqual(firsts, set(ids))          # over an hour of slots, every account goes first at least once


import unittest.mock  # noqa: E402  (patch.dict above)

if __name__ == "__main__":
    unittest.main()
