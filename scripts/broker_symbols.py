#!/usr/bin/env python3
"""Canonical instrument <-> broker symbol for the MT5 terminal behind the live bridge (CLAUDE.md §5: the canonical identity is
independent of provider spelling; provider spelling stays at the provider boundary).

The map is the broker's own export: data/history/costs/ftmo/symbol-map.json (FTMO-Demo, integrations/mt5/ExportSymbolSpec.mq5),
`{"map": {broker_name: canonical}}`. FTMO spells the US500 index "US500.cash"; the research, the executor and the instrument
allowlist say "US500". Readers of bridge files and the order path translate here, and nowhere else.

Refusals, both deliberate: a canonical symbol the map does not name raises (no guessing that the broker spells it the same),
and a map that sends two broker names to one canonical raises (an ambiguous identity)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "data", "history", "costs", "ftmo", "symbol-map.json")


class UnknownSymbol(KeyError):
    pass


def _load(path=MAP_PATH):
    doc = json.load(open(path, encoding="utf-8"))
    to_canon = dict(doc["map"])
    to_broker = {}
    for broker, canon in to_canon.items():
        if canon in to_broker:
            raise ValueError(f"{path}: {to_broker[canon]!r} and {broker!r} both map to {canon!r}")
        to_broker[canon] = broker
    return to_broker, to_canon


def to_broker(canonical, path=MAP_PATH):
    """'US500' -> 'US500.cash' on FTMO-Demo; 'XAUUSD' -> 'XAUUSD'."""
    to_b, _ = _load(path)
    if canonical not in to_b:
        raise UnknownSymbol(f"{canonical!r} has no broker symbol in {path}")
    return to_b[canonical]


def to_canonical(broker, path=MAP_PATH):
    """'US500.cash' -> 'US500'."""
    _, to_c = _load(path)
    if broker not in to_c:
        raise UnknownSymbol(f"{broker!r} is not in {path}")
    return to_c[broker]
