"""CLAUDE.md §2 -- provider identity is data, and Binance is not the architectural center.

What §2 actually demands, and what each test here holds:

  "The architecture must be provider-agnostic"     -> the registry loads, validates, and is the one place a
                                                      connector path is written down.
  "Binance must NOT become the architectural center" -> no script outside the registry's reader may hard-code a
                                                      connector path the registry owns.
  "independent choices of market-data / analytics /
   aggregated intelligence / execution provider"   -> for_role() answers the four questions independently, and
                                                      a provider may hold one role without the others.
  "Data Source != Execution Venue"                 -> asking who supplies data and asking who receives orders
                                                      are different queries with different answers, provable
                                                      by a provider that is one and not the other.

The behaviour-preservation test matters as much as the rest: this change moved three constants in the LIVE
order engine (scripts/strategy-runner.py) from literals to registry lookups. A refactor of the order path that
silently changed which connector receives an order would be the worst possible outcome of a tidying exercise,
so the historical literals are pinned here by value.
"""
import importlib.util
import os
import unittest

import srcscan

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import providers as P

# The literal paths scripts/strategy-runner.py carried before 2026-09-18. Written out ON PURPOSE: this is the
# one place in the repo where restating them is correct, because the assertion IS "the value did not change".
HISTORICAL = {
    "ORDER": "scripts/binance-futures-testnet-order.sh",
    "MT5": "scripts/mt5-order-bridge.py",
    "FETCH": "scripts/fetch-binance-klines.sh",
}


def hardcoded(code, owned):
    """Connector basenames appearing as a string literal in `code`. Split out of the scan below so the rule
    can be mutation-tested against synthetic text -- a scan asserted only against the real tree passes
    vacuously the day its matching breaks, which is how test_doc_citations.py's first version stayed green
    against eleven stale citations."""
    return sorted(c for c in owned if f'"{c}"' in code or f"'{c}'" in code)


def runner():
    spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Registry(unittest.TestCase):
    def test_every_declared_adapter_exists_on_disk(self):
        """Import-time validation already raises on a missing adapter; this states it as a property so the
        reason survives. A registry naming a connector that was renamed reads as evidence the path is live."""
        for pid in P.ALL:
            for path in (P.adapter(pid), P.market_data_adapter(pid)):
                if path is not None:
                    self.assertTrue(os.path.exists(path), f"provider {pid} names a missing connector: {path}")

    def test_a_missing_adapter_refuses_to_load(self):
        """Mutation-proof of the above: the validator must REFUSE, not warn. Built on a minimal dict rather
        than by editing the real registry, the same way scripts/methods.py's invariants are tested."""
        bad = {"roles": {"execution": "x"}, "status_values": {"connected": "x"},
               "capabilities": {"order_submission": "x"},
               "providers": {"ghost": {"roles": ["execution"], "markets": ["crypto"],
                                       "adapter": "scripts/no-such-connector.sh", "status": "connected",
                                       "capabilities": ["order_submission"], "venue": "nowhere"}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("does not exist", str(cm.exception))

    def test_an_execution_provider_without_an_adapter_refuses_to_load(self):
        """'Can receive orders' is the one claim that must never be decorative."""
        bad = {"roles": {"execution": "x"}, "status_values": {"connected": "x"},
               "capabilities": {"order_submission": "x"},
               "providers": {"claimer": {"roles": ["execution"], "markets": ["crypto"], "adapter": None,
                                         "status": "connected", "capabilities": ["order_submission"],
                                         "venue": "nowhere"}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("execution role with no adapter", str(cm.exception))

    def test_an_unknown_market_refuses_to_load(self):
        """instruments.json owns the market vocabulary; a typo here would make a provider unreachable in
        silence rather than loudly."""
        bad = {"roles": {"market_data": "x"}, "status_values": {"connected": "x"},
               "capabilities": {},
               "providers": {"p": {"roles": ["market_data"], "markets": ["equities"], "adapter": None,
                                   "status": "connected", "capabilities": [], "venue": "v"}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("instruments.json", str(cm.exception))

    def test_mock_only_provider_is_not_live(self):
        """CoinGlass has no key. A mock_only provider may never satisfy a live decision requirement, so the
        registry must not report it as usable (CLAUDE.md §6, SYSTEM-DESIGN.md §6.1)."""
        self.assertEqual(P.status_of("coinglass"), "mock_only")
        self.assertFalse(P.is_live("coinglass"))


class DataSourceIsNotExecutionVenue(unittest.TestCase):
    """CLAUDE.md §4's separation, expressed as queries rather than as a convention."""

    def test_the_four_roles_are_answered_independently(self):
        for role in ("market_data", "analytics", "aggregated_intelligence", "execution"):
            self.assertTrue(P.for_role(role), f"no provider offers {role}; the role would be unchoosable")

    def test_a_market_data_provider_need_not_be_an_execution_venue(self):
        """binance_public reads klines over the public endpoint and holds no credentials; it must never appear
        as somewhere an order can go."""
        self.assertIn("binance_public", P.for_role("market_data", "crypto"))
        self.assertNotIn("binance_public", P.for_role("execution", "crypto"))

    def test_an_aggregated_intelligence_provider_is_not_an_execution_venue(self):
        self.assertIn("coinglass", P.for_role("aggregated_intelligence", "crypto"))
        self.assertNotIn("coinglass", P.for_role("execution", "crypto"))

    def test_one_provider_may_hold_two_roles(self):
        """mt5_bridge supplies CFD data AND receives its orders. Roles are a list precisely so this is
        expressible without collapsing the two questions into one field."""
        self.assertIn("mt5_bridge", P.for_role("market_data", "cfd"))
        self.assertIn("mt5_bridge", P.for_role("execution", "cfd"))
        self.assertNotEqual(P.adapter("mt5_bridge"), P.market_data_adapter("mt5_bridge"),
                            "the two roles are served by two different programs and must resolve separately")

    def test_crypto_market_data_and_crypto_execution_are_different_providers(self):
        """The concrete shape of 'Data Source != Execution Venue' for the market that has both today."""
        self.assertNotEqual(set(P.for_role("market_data", "crypto")), set(P.for_role("execution", "crypto")))


class LiveEngineResolvesThroughTheRegistry(unittest.TestCase):
    def test_the_runner_constants_are_unchanged_by_value(self):
        """The refactor must not have moved where an order goes."""
        mod = runner()
        for name, rel in HISTORICAL.items():
            self.assertEqual(getattr(mod, name), os.path.join(ROOT, rel),
                             f"strategy-runner.{name} no longer resolves to {rel}")

    def test_the_runner_no_longer_hardcodes_a_connector_path(self):
        """The point of §2. Prose may name a connector (and does, in the module docstring explaining the
        venues); CODE may not resolve one by literal path -- that is what srcscan separates."""
        code = srcscan.code_text("scripts/strategy-runner.py")
        for rel in HISTORICAL.values():
            literal = os.path.basename(rel)
            self.assertNotIn(f'"{literal}"', code,
                             f"strategy-runner.py code still hard-codes {literal}; resolve it through "
                             f"providers.py so the venue is a registry entry, not an edit to the order engine")

    def test_no_script_outside_the_reader_hardcodes_an_external_connector(self):
        """Binance is not the architectural center: no module may name an EXTERNAL provider's connector. The
        reader and the test that pins the historical values are the two deliberate exceptions.

        Scoped to external providers on purpose. The repo's own scanner is declared as the `local_derived`
        analytics provider so the seam is visible (CLAUDE.md §2 wants analytics to be a choice), but banning
        sibling modules from loading ict-scan.py would be cargo-culting the rule: scripts/live_rules.py:34
        loads it as an in-repo module, which is cohesion, not a vendor dependency."""
        owned = P.external_connectors()
        allowed = {"providers.py", "test_providers.py"}
        offenders = []
        for fn in sorted(os.listdir(os.path.join(ROOT, "scripts"))):
            if not fn.endswith(".py") or fn in allowed:
                continue
            for conn in hardcoded(srcscan.code_text(f"scripts/{fn}"), owned):
                offenders.append(f"scripts/{fn} hard-codes {conn}")
        self.assertEqual(offenders, [], "connector paths belong in docs/architecture/providers.json:\n  "
                                        + "\n  ".join(offenders))

    def test_the_hardcoding_scan_actually_detects_a_violation(self):
        """Mutation proof of the rule above: without this, the clean result could mean 'nothing hard-codes a
        connector' or 'the matching is broken', and those look identical from a green test."""
        owned = P.external_connectors()
        self.assertTrue(owned, "the registry declares no external connector; the scan would be vacuous")
        one = sorted(owned)[0]
        self.assertEqual(hardcoded(f'FETCH = os.path.join(ROOT, "scripts", "{one}")', owned), [one])
        self.assertEqual(hardcoded("FETCH = P.market_data_adapter('binance_public')", owned), [])

    def test_the_local_analytics_provider_is_not_subject_to_the_ban(self):
        """The scoping decision, stated as a property: in-repo code declared in a provider role is not a
        vendor, and its siblings may load it by name (scripts/live_rules.py:34 does, correctly)."""
        self.assertFalse(P.is_external("local_derived"))
        self.assertNotIn("ict-scan.py", P.external_connectors())

    def test_a_provider_without_the_external_flag_refuses_to_load(self):
        bad = {"roles": {"market_data": "x"}, "status_values": {"connected": "x"},
               "capabilities": {},
               "providers": {"p": {"roles": ["market_data"], "markets": ["crypto"], "adapter": None,
                                   "status": "connected", "capabilities": [], "venue": "v"}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("`external`", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
