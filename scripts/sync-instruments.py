#!/usr/bin/env python3
"""Regenerate every DERIVED copy of the instrument allowlist from the single source
(docs/architecture/instruments.json). JSON Schema cannot $ref an enum out of an arbitrary file in a way
every validator honours, so the enums are generated here instead of hand-maintained -- and
scripts/tests/test_instruments_sync.py runs this in --check mode so drift fails the build.

    python3 scripts/sync-instruments.py --check    # exit 1 and name the drift
    python3 scripts/sync-instruments.py --write    # rewrite the derived spots

Derived spots (add new ones HERE, never a new hand-kept list):
  - schemas/automation-config.schema.json  markets.{crypto,cfd}.instruments.items.enum  <- analysis
  - schemas/trade-file.schema.json         instrument.enum                              <- analysis (all)
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import instruments as I

SCHEMAS = os.path.join(ROOT, "docs", "architecture", "schemas")
AUTOMATION_SCHEMA = os.path.join(SCHEMAS, "automation-config.schema.json")
TRADE_SCHEMA = os.path.join(SCHEMAS, "trade-file.schema.json")


def _targets():
    """(path, json-pointer-ish accessor, expected list) for every derived spot."""
    out = []
    for market in I.MARKETS:
        out.append((AUTOMATION_SCHEMA,
                    ["properties", "markets", "properties", market, "properties", "instruments", "items", "enum"],
                    I.analysis(market)))
    out.append((TRADE_SCHEMA, ["properties", "instrument", "enum"], I.analysis()))
    return out


def _dig(doc, path):
    for k in path:
        doc = doc[k]
    return doc


def _set(doc, path, value):
    for k in path[:-1]:
        doc = doc[k]
    doc[path[-1]] = value


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()

    drift, touched = [], set()
    docs = {}
    for path, ptr, want in _targets():
        docs.setdefault(path, json.load(open(path, encoding="utf-8")))
        have = _dig(docs[path], ptr)
        if have != want:
            drift.append(f"{repo_rel(path, ROOT)} :: {'.'.join(ptr)}\n    is:     {have}\n    should: {want}")
            if a.write:
                _set(docs[path], ptr, want)
                touched.add(path)

    if a.check:
        if drift:
            print("DRIFT from docs/architecture/instruments.json:\n" + "\n".join(drift), file=sys.stderr)
            print("\nFix: python3 scripts/sync-instruments.py --write", file=sys.stderr)
            return 1
        print("OK: every derived instrument list matches docs/architecture/instruments.json")
        return 0

    for path in touched:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(docs[path], fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    print(f"wrote {len(touched)} file(s)" if touched else "nothing to do -- already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
