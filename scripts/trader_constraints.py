"""CLAUDE.md §0.9 (docs/plans/2026-09-18-close-feature-gaps.md) -- THE reader for
docs/architecture/trader-constraints.json: constraints a TRADER has decided to trade under, from their own
experience, per methodology -- distinct from what the ACCOUNT requires (scripts/account_profile.py) and from
the platform's own thresholds (docs/architecture/analysis-params.json).

    import trader_constraints as TC

    TC.for_trader("tung")                       -> {"ict": [...], "wyckoff": [...]}
    TC.overlay(OPTS, "tung", "ict")              -> a NEW dict, tightened; `OPTS` itself is untouched

§4 of the audit (docs/audits/2026-09-18-feature-audit.md row 4) found no trader identity anywhere in the repo:
`custom_constraints` pointed at one shared config file, and nothing distinguished one trader's experience from
another's. This module is the first reader of a per-trader, per-methodology registry.

**Tighten-only, by construction.** `overlay()` never loosens a value -- it takes `max()` for a floor
(`min_rr`), an intersection for a narrowing set (`sessions`, `types`), a logical OR for an only-true switch
(`htf`, `sloped_gate`), and `min()` for a ceiling (`max_trades_per_day`). Every one of
those operations is loosening-proof by the operation itself, and `_validate()` additionally refuses an
AUTHORED value that already contradicts its own kind's tighten direction (a `false` for an only-true kind, a
`min_rr` below the platform floor) -- catching the authoring mistake at import rather than trusting the
arithmetic alone to save it.

**Two integration points, one function.** `overlay()` is generic over `opts` (any dict with the OPTS-shaped
keys) so it serves BOTH of §0.9's callers with no second implementation:
  * `scripts/backtest-methods.py` -- `--trader <id>`, applied PER RUNNER METHOD (`scan_for_trader()`), because
    a method requiring only `wyckoff` must never be tightened by an `ict` constraint and vice versa (§17: never
    merge across methodologies).
  * the LIVE runner, step 10 (`strategy-runner.py`, planned -- `automation-config.json execution.trader`,
    NOT wired by this task; see docs/plans/2026-09-18-close-feature-gaps.md WS-D scope note) -- would call
    `overlay(OPTS, trader_id, methodology)` at the same step account_profile's own rules apply, and would be
    the integration point for the `max_trades_per_day` kind (this module validates it; nothing in the backtest
    engine currently has a per-day trade-count gate to apply it to -- see `_kinds.max_trades_per_day` in the
    registry).

`sessions` and `max_trades_per_day` are not OPTS keys (session gating lives in
`scripts/backtest-methods.py simulate()`, not `scan()`; a per-day trade cap is an account-shaped rule).
`overlay()` still validates and tightens them, carrying the result on private keys (`_sessions`,
`_max_trades_per_day`) on the RETURNED dict for the caller's own integration point to read -- the function
never invents where those get enforced.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel

import sessions as _S
import trading_env as _TE

PATH = os.path.join(ROOT, "docs", "architecture", "trader-constraints.json")

# The kinds vocabulary. Each maps to exactly ONE existing knob (§0.9). An item whose `kind` is not a key here
# is refused at import -- an unenforceable constraint must not be able to look enforced.
BOOL_TRUE_ONLY = ("htf", "sloped_gate")   # ict_disp/ict_pd removed 2026-09-19: both are mandatory now, not switches
KINDS = ("min_rr", "sessions", "types") + BOOL_TRUE_ONLY + ("max_trades_per_day",)

_PLATFORM_MIN_RR = _TE.min_rr()


class RegistryError(ValueError):
    """The §0.9 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Asked for a trader this registry does not name."""


def _read(path=None):
    with open(path or PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _validate_item(trader_id, methodology, item, path):
    for k in ("kind", "value", "why"):
        if k not in item:
            raise RegistryError(f"{path}: trader {trader_id!r} methodology {methodology!r} has an item "
                                f"missing {k!r}: {item!r}")
    kind, value, why = item["kind"], item["value"], item["why"]
    if kind not in KINDS:
        raise RegistryError(f"{path}: trader {trader_id!r} methodology {methodology!r} names unknown "
                            f"constraint kind {kind!r}; the declared kinds are {list(KINDS)} (see `_kinds` in "
                            f"the registry)")
    if not str(why or "").strip():
        raise RegistryError(f"{path}: trader {trader_id!r} methodology {methodology!r} kind {kind!r} has no "
                            f"`why` -- a constraint with no stated reason is not distinguishable from a typo")
    if kind == "min_rr":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise RegistryError(f"{path}: trader {trader_id!r} min_rr must be a number, got {value!r}")
        if _PLATFORM_MIN_RR is not None and value < _PLATFORM_MIN_RR:
            raise RegistryError(
                f"{path}: trader {trader_id!r} declares min_rr={value}, which is BELOW the platform floor "
                f"({_PLATFORM_MIN_RR}, docs/architecture/analysis-params.json project_defined.ict.min_rr). "
                f"A trader constraint may only tighten -- a lower min_rr here would loosen the floor everyone "
                f"else trades under.")
    elif kind == "sessions":
        if not isinstance(value, list) or not value:
            raise RegistryError(f"{path}: trader {trader_id!r} sessions must be a non-empty list, got {value!r}")
        unknown = [s for s in value if s not in _S.LABELS]
        if unknown:
            raise RegistryError(f"{path}: trader {trader_id!r} sessions names {unknown}, which are not "
                                f"sessions in docs/architecture/sessions.json ({list(_S.LABELS)})")
    elif kind == "types":
        if not isinstance(value, list) or not value or not all(v in (1, 2, 3) for v in value):
            raise RegistryError(f"{path}: trader {trader_id!r} types must be a non-empty list drawn from "
                                f"[1, 2, 3] (the Wyckoff volume types), got {value!r}")
    elif kind in BOOL_TRUE_ONLY:
        if value is not True:
            raise RegistryError(
                f"{path}: trader {trader_id!r} kind {kind!r} declares {value!r}. This kind can only be turned "
                f"ON (tighten-only, §0.9): a declared `false` would loosen a filter that may already be on, "
                f"and turning it off is not a thing a trader constraint may do. Omit the item instead of "
                f"declaring false.")
    elif kind == "max_trades_per_day":
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RegistryError(f"{path}: trader {trader_id!r} max_trades_per_day must be a positive integer, "
                                f"got {value!r}")


def _validate(data, path=PATH):
    if not isinstance(data.get("version"), int):
        raise RegistryError(f"{path}: `version` must be an integer (CLAUDE.md §11 -- a research run's "
                            f"configuration snapshot records which rule set applied)")
    traders = data.get("traders") or {}
    for tid, td in traders.items():
        per = (td or {}).get("per_methodology") or {}
        if not per:
            raise RegistryError(f"{path}: trader {tid!r} declares no per_methodology constraints -- an empty "
                                f"trader entry is indistinguishable from a typo; remove it or add at least one")
        for methodology, items in per.items():
            if not isinstance(items, list) or not items:
                raise RegistryError(f"{path}: trader {tid!r} methodology {methodology!r} must be a non-empty "
                                    f"list of constraint items")
            for item in items:
                _validate_item(tid, methodology, item, path)
    return traders


_DATA = _read()
TRADERS = _validate(_DATA)


def for_trader(trader_id):
    """This trader's declared constraints, `{methodology: [items]}`. Raises `NotDeclared` for an unknown
    trader id -- a typo in `--trader` must fail loudly, not silently apply no constraints (CLAUDE.md: no
    silent fallback)."""
    if trader_id not in TRADERS:
        raise NotDeclared(f"no trader {trader_id!r} in {repo_rel(PATH, ROOT)}; declared traders are "
                          f"{sorted(TRADERS)}")
    return {m: [dict(it) for it in items] for m, items in TRADERS[trader_id]["per_methodology"].items()}


def load():
    """Every declared trader's constraints, `{trader_id: {methodology: [items]}}`."""
    return {tid: for_trader(tid) for tid in TRADERS}


def overlay(opts, trader_id, methodology):
    """A NEW dict, `opts` tightened by `trader_id`'s declared constraints for `methodology`. `opts` itself is
    never mutated. A trader/methodology pair with no declared items returns an unchanged copy.

    Every operation below is loosening-proof by construction (max / intersection / OR / min) -- see the module
    docstring. `sessions` and `max_trades_per_day` are not OPTS keys; their tightened values are carried on
    the RETURNED dict as `_sessions` / `_max_trades_per_day` for the caller's own integration point.
    """
    items = for_trader(trader_id).get(methodology, [])
    new = dict(opts)
    for item in items:
        kind, value = item["kind"], item["value"]
        if kind == "min_rr":
            cur = new.get("min_rr")
            new["min_rr"] = value if cur is None else max(cur, value)
        elif kind == "types":
            cur = new.get("types")
            new["types"] = tuple(sorted(set(cur) & set(value))) if cur is not None else tuple(sorted(value))
        elif kind in BOOL_TRUE_ONLY:
            new[kind] = bool(new.get(kind)) or True
        elif kind == "sessions":
            cur = new.get("_sessions")
            allowed = frozenset(value)
            new["_sessions"] = allowed if cur is None else (cur & allowed)
        elif kind == "max_trades_per_day":
            cur = new.get("_max_trades_per_day")
            new["_max_trades_per_day"] = value if cur is None else min(cur, value)
        # kind is guaranteed in KINDS by _validate_item at import; no else branch needed.
    return new


if __name__ == "__main__":
    print(f"CLAUDE.md §0.9 -- {len(TRADERS)} trader(s) declared in "
         f"{repo_rel(PATH, ROOT)}")
    for tid, per in load().items():
        for methodology, items in per.items():
            for item in items:
                print(f"  {tid} / {methodology}: {item['kind']} = {item['value']!r}")
