"""Setup rule versions (CLAUDE.md §14): a setup's behaviour, identified.

    import setup_version as SV
    SV.rule_version(setup_row, global_params)   -> 'a1b2c3d4e5f6'

§14 requires setup logic to be *explicit, independently testable, versioned, explainable*. Three of the four
held; **versioned did not**. A setup's `id` encodes its parameters -- `crypto-scalping-combined-15m-border-b`
-- but not a version, and `scripts/rank-setups.py` rewrites `docs/architecture/pilot-top20.json` in place. So a
rule change that keeps the same (market, horizon, method, timeframe, target, config) produces the *same id
with different behaviour*, and `trade-file.schema.json` records `strategy` as exactly that id. A closed trade
therefore points at an identifier whose meaning may have changed since the trade was taken, with nothing to
say so.

**A content version, not a hand-bumped integer.** The version is a digest of the inputs that actually decide
what the setup does, so it changes exactly when behaviour changes and cannot be forgotten. A manual counter
has the opposite failure: it is remembered when someone is thinking about versioning and skipped when they are
thinking about the rule.

**What is in, and what is deliberately out.** A Setup is "a specific market condition that can qualify for
entry" (§14). So the version covers the condition and its entry/exit rules -- but NOT position sizing, NOT the
account. `RISK`, `START` and `RUIN_FRAC` are excluded on purpose: halving risk does not change which bars
qualify, and folding them in would churn every setup's version whenever the ceiling moved, which is exactly
the kind of noise that trains people to ignore a version field. Risk *is* version-significant for a TRADING
SYSTEM (§47) -- a different object, which does not exist yet (§35).

`min_rr` IS included: it is an entry filter and changes which setups qualify (38 % of a year's setups planned
under 2R before the floor was raised, `analysis-params.json` `project_defined.ict.min_rr`).
"""
import hashlib
import json

VERSION_ALGO = "sha256-12"

# Fields of a setup row that decide what it does. `id` is excluded: it is a NAME, and including it would make
# the version change when a label changed and stay put when a rule changed -- backwards on both counts.
# `rank`, `backtest`, `symbols`, `negative_backtest` and `fee_assumed` are excluded as well: they describe how
# a setup was selected or how it scored, not what it detects.
RULE_FIELDS = ("market", "tf", "method", "htf", "mgmt", "execution")

# Per-setup deck-faithful switches (scripts/rank-setups.py FLAG_KEYS): a row may still carry a key that
# genuinely changes detection, and such a key is part of the version when set. Empty since 2026-09-19 --
# ict_disp / ict_pd / std_origin were removed because none of them could change an ICT setup (knowledge audit
# finding 11). Kept as a named seam so the next real switch has one place to be declared.
FLAG_FIELDS = ()

# Global detection parameters the caller resolves and passes in. Named here so the set is declared in one
# place rather than assembled differently at each call site.
GLOBAL_PARAM_KEYS = ("min_rr", "stop_buffer_pct", "displacement", "volume", "per_timeframe")


def rule_inputs(setup, global_params):
    """Exactly what the version is computed over, as a plain dict -- inspectable, so a surprising version
    change can be explained rather than guessed at."""
    unknown = [k for k in global_params if k not in GLOBAL_PARAM_KEYS]
    if unknown:
        raise ValueError(f"unknown global rule parameter(s) {unknown}; declared: {list(GLOBAL_PARAM_KEYS)}")
    row = {k: setup.get(k) for k in RULE_FIELDS}
    row.update({k: setup[k] for k in FLAG_FIELDS if k in setup})
    return {"setup": row, "global": {k: global_params[k] for k in sorted(global_params)}}


def rule_version(setup, global_params):
    """Stable short digest of a setup's behaviour-determining inputs."""
    blob = json.dumps(rule_inputs(setup, global_params), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def stamp(selection, global_params_for):
    """Add `rule_version` to every setup in a selection file, in place.

    `global_params_for(setup)` returns the resolved global parameters for that setup -- a callable because the
    per-timeframe block differs per row. Must run AFTER any flag carrying, since a carried switch changes the
    rules and therefore the version.
    """
    for st in selection.get("setups", []):
        st["rule_version"] = rule_version(st, global_params_for(st))
        st["rule_version_algo"] = VERSION_ALGO
    return selection


def qualified_id(setup):
    """`<id>@<rule_version>` -- what a trade should record, so a closed trade names the rules that produced
    it and not just the label they were filed under."""
    v = setup.get("rule_version")
    return f"{setup['id']}@{v}" if v else setup["id"]


def split_qualified(value):
    """('crypto-scalping-ict-15m-a', 'a1b2c3d4e5f6') -- version None for a legacy unqualified id."""
    if "@" in value:
        head, _, tail = value.partition("@")
        return head, tail
    return value, None
