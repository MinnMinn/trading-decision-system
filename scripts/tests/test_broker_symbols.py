"""scripts/broker_symbols.py + the order bridge's resolve(): canonical identity inside, broker spelling only at the MT5 boundary.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_broker_symbols
"""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import broker_symbols as BS  # noqa: E402

spec = importlib.util.spec_from_file_location("mt5_order_bridge", os.path.join(ROOT, "scripts", "mt5-order-bridge.py"))
OB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(OB)


class Map(unittest.TestCase):
    def test_ftmo_spellings(self):
        self.assertEqual(BS.to_broker("US500"), "US500.cash")
        self.assertEqual(BS.to_broker("USTEC"), "US100.cash")
        self.assertEqual(BS.to_broker("DE40"), "GER40.cash")
        self.assertEqual(BS.to_broker("XAUUSD"), "XAUUSD")
        self.assertEqual(BS.to_canonical("US500.cash"), "US500")

    def test_every_mt5_execution_symbol_has_a_broker_name(self):
        for sym in OB.ALLOWED:
            self.assertTrue(BS.to_broker(sym))

    def test_unknown_and_ambiguous_refuse(self):
        with self.assertRaises(BS.UnknownSymbol):
            BS.to_broker("NOPE")
        p = os.path.join(tempfile.mkdtemp(), "m.json")
        json.dump({"map": {"A.cash": "A", "A.x": "A"}}, open(p, "w"))
        with self.assertRaises(ValueError):
            BS.to_broker("A", p)


class OrderBridgeResolve(unittest.TestCase):
    def test_canonical_in_broker_out(self):
        self.assertEqual(OB.resolve("US500", ""), ("US500", "US500.cash"))
        self.assertEqual(OB.resolve("US500.cash", ""), ("US500", "US500.cash"))
        self.assertEqual(OB.resolve("XAUUSD", "none"), ("XAUUSD", "XAUUSD"))

    def test_allowlist_is_checked_on_the_canonical_symbol(self):
        for bad in ("HK50", "HK50.cash", "BTCUSDT"):             # analysis / research-only / other venue: never orderable here
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                OB.resolve(bad, "")
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
