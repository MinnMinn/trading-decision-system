"""THE producer for scripts/expectation.py records (CLAUDE.md §17 plan §0.5) -- the piece the audit found
missing: `docs/audits/2026-09-18-feature-audit.md` row 11 named "no producer: outside test no file calls
create()". This module is that caller, and only this module -- `strategy-runner.py` and `journal.py`'s callers
import it rather than constructing an `expectation` record by hand, so the eight required fields (§17) are
always sealed the same way.

    import expectation_producer as EP
    EP.from_plan(plan_row, "ict")                 # from a trades/index.jsonl row
    EP.from_signal(sig, st, "BTCUSDT")             # from the runner's own signal/setup, one record per dimension

Kind mapping. §0.5 names exactly two: `ict -> structural_objective`, `wyckoff -> trading_range_objective` (both
already declared in docs/architecture/methods.json `dimensions.<m>.expectation_kinds`). The runner's rule
families (docs/architecture/methods.json `runner_methods`) only ever require `wyckoff`/`ict`/both, so
`from_signal` never needs a third mapping; `from_plan` raises for anything else rather than guessing a kind
that was never declared for that methodology.

Why the legs look the way they do. §17 says "Do not reduce expectations to target prices" -- a path is a
SEQUENCE across the three phases, not one number. The runner and the plan rows here carry exactly one price
before the entry (the entry level itself; nothing finer is tracked mechanically), so `before_entry` and
`entry_area` both key off `entry` -- two legs, not a duplicate, because §17's phases are a vocabulary the
renderer keys on (`chart.js expectationShapes` draws `before_entry` legs to the LEFT of the entry index and
`after_entry` legs to the right; a plan with only an `after_entry` leg would draw nothing before the entry
bar). `after_entry` gets one leg per target, in order (`target_1`, `target_2`, ...).
"""
import methods as M
import expectation as X

# §0.5's own table. A methodology not in it has no runner-method caller today (RUNNER_METHODS only ever
# requires wyckoff/ict/both) and no declared producer mapping -- raising here is cheaper than guessing a kind
# that CLAUDE.md §17 never sanctioned for that methodology.
KIND_BY_METHODOLOGY = {
    "ict": "structural_objective",
    "wyckoff": "trading_range_objective",
}

# The before_entry leg has no finer boundary than the entry itself in the data this producer is given (a plan
# row or a mechanical signal carry no separate "entry zone" bound) -- so its label says exactly that, in the
# language the thesis was authored in. This module is not a renderer (docs/architecture/i18n.json's
# `chart.*`/`legend.*` slice never needs this string -- see scripts/tests/test_i18n.py RENDERERS), so the
# CLAUDE.md-sanctioned rule for authored prose (vi_source) applies: Vietnamese DATA is fine, only renderer CODE
# may not hardcode it.
BEFORE_ENTRY_LABEL = "vùng vào lệnh"


def _kind_for(methodology):
    kind = KIND_BY_METHODOLOGY.get(methodology)
    if kind is None:
        raise ValueError(
            f"expectation_producer has no expectation-kind mapping for methodology {methodology!r}; "
            f"declared mappings: {sorted(KIND_BY_METHODOLOGY)} (docs/plans/2026-09-18-close-feature-gaps.md §0.5)")
    return kind


def _path_for(entry, targets):
    if not targets:
        raise ValueError(
            "an expectation needs at least one target to build an after_entry leg; CLAUDE.md §17: 'Do not "
            "reduce expectations to target prices' -- a plan with no targets cannot produce a path at all")
    path = [X.leg("before_entry", entry, BEFORE_ENTRY_LABEL),
            X.leg("entry_area", entry, "entry")]
    for i, t in enumerate(targets, start=1):
        path.append(X.leg("after_entry", t, f"target_{i}"))
    return path


def _statement(methodology, direction, entry, targets):
    tlist = ", ".join(f"{t:g}" for t in targets)
    return f"{methodology} {direction or '?'} entry {entry:g} -> {tlist}"


def from_plan(plan, methodology, *, series=None, created_at=None):
    """One expectation from a `trades/index.jsonl` row (§0.5). `plan` carries `entry`, `stop_loss`, `targets`,
    `direction`, `date_opened`, `setup_type` -- the shape scripts/journal.py `sync_pilot` already writes."""
    entry = float(plan["entry"])
    stop = float(plan["stop_loss"])
    targets = [float(t) for t in (plan.get("targets") or [])]
    direction = plan.get("direction")
    kind = _kind_for(methodology)
    path = _path_for(entry, targets)
    inv = X.invalidation("stop", stop, owner=methodology)
    evidence = [plan["setup_type"]] if plan.get("setup_type") else None
    return X.create(kind, methodology, _statement(methodology, direction, entry, targets),
                     path=path, invalidation=inv, source_evidence=evidence,
                     series=series, event_time=plan.get("date_opened"), created_at=created_at)


def from_signal(sig, st, symbol, *, series=None, created_at=None):
    """One expectation PER DIMENSION the runner's rule family requires (§17: never merged). `sig` is the
    runner's signal (`entry`/`stop`/`target`/`side`/`time`), `st` its setup row (`method`/`tf`). COMBINED-BOOK's
    `requires` is `["wyckoff", "ict"]`, so a COMBINED-BOOK signal yields two independent records."""
    runner_method = st["method"]
    spec = M.RUNNER_METHODS.get(runner_method)
    if spec is None:
        raise ValueError(f"unknown runner method {runner_method!r}; declared in "
                         f"docs/architecture/methods.json `runner_methods`")
    entry = float(sig["entry"])
    stop = float(sig["stop"])
    targets = [float(sig["target"])]
    direction = sig.get("side")
    evidence = [symbol] + ([st["tf"]] if st.get("tf") else [])
    records = []
    for methodology in spec["requires"]:
        kind = _kind_for(methodology)
        path = _path_for(entry, targets)
        inv = X.invalidation("stop", stop, owner=methodology)
        records.append(X.create(kind, methodology, _statement(methodology, direction, entry, targets),
                                 path=path, invalidation=inv, source_evidence=list(evidence),
                                 series=series, event_time=sig.get("time"), created_at=created_at))
    return records
