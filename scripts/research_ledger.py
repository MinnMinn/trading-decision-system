"""CLAUDE.md §43 + §44 -- THE reader for docs/architecture/research-ledger.json: what was tried, and what
trying it did to the validation data.

Two sections over one structure. §43 counts the experiments; §44 asks what those counts did to the data. Both
were impossible before §42 gave the repo an experiment store, and both are still partly answered by facts that
predate it -- which this module reports as *unrecorded*, never as zero.

    import research_ledger as RL

    RL.budget()                  # §43's seven counters, computed from the §42 store
    RL.periods()                 # §44's four states over the declared periods
    RL.state_of("crypto-history-2023-2026")     -> 'development'
    RL.expose(period, trigger="candidate_selection", experiment_id=...)  # one-way
    RL.assert_untouched(period)  # raises unless the period can still validate anything

Three properties:

1. **Computed, not remembered.** Every §43 counter is derived from the experiment store. A counter kept by
   hand is a counter that disagrees with the store, and §43's whole demand is "do not hide the number".
2. **Unrecorded is not zero.** Two real searches predate the store -- seven ICT target-model variants over one
   dataset, and 120 candidate rows narrowed to 6 with nothing recorded about the 114. `budget()` reports them
   in `unrecorded` and refuses to fold them into the counts, because an unrecorded search that has been added
   to a total is indistinguishable from a recorded one.
3. **Exposure is one-way.** `untouched -> exposed` is allowed; the reverse raises. §44: "Do not label it as
   pristine validation anymore." A state machine that can go back is a label that can be restored by whoever
   needs it to be.

The honest current state, which this module states rather than implies: **no period is untouched.** Every span
of history the repo holds was read by the runs that produced the live selection. A genuine OOS period must be
carved out and left alone before it can validate anything, and doing that is a decision about what the pilot
trades (§59), not a documentation change.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import experiment as X

PATH = os.path.join(ROOT, "docs", "architecture", "research-ledger.json")

DEVELOPMENT, UNTOUCHED, EXPOSED, HOLDOUT = "development", "oos_untouched", "oos_exposed", "final_holdout"


class RegistryError(ValueError):
    """The §43/§44 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something named a period, counter or trigger the spec does not list."""


class ExposureIsOneWay(RuntimeError):
    """Something tried to un-expose a period CLAUDE.md §44 says is exposed."""


class NotValidationData(RuntimeError):
    """Something tried to validate on data that has already influenced a choice."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    b, o = data.get("budget") or {}, data.get("oos") or {}
    for key, section in (("counters", b), ("states", o), ("exposure_triggers", o)):
        if not isinstance(section.get(key), list) or not section[key]:
            raise RegistryError(f"{path}: `{key}` must be a non-empty list")
    states = {s["id"] for s in o["states"]}
    if states != {DEVELOPMENT, UNTOUCHED, EXPOSED, HOLDOUT}:
        raise RegistryError(f"{path}: §44 names exactly four data states; found {sorted(states)}")
    for p in o.get("periods") or ():
        for k in ("id", "range", "state", "why"):
            if not p.get(k):
                raise RegistryError(f"{path}: period {p.get('id')!r} has no {k!r}")
        if p["state"] not in states:
            raise RegistryError(f"{path}: period {p['id']!r} is in state {p['state']!r}, which §44 does not "
                                f"name")
        if p["state"] == UNTOUCHED and "read" in str(p.get("why", "")).lower():
            raise RegistryError(
                f"{path}: period {p['id']!r} is labelled {UNTOUCHED} and its own reason says it was read. "
                f"§44: 'Do not continue treating exposed OOS data as untouched validation data.'")
    return data


_DATA = _load()
COUNTERS = tuple(c["id"] for c in _DATA["budget"]["counters"])
COUNTER_NAMES = {c["id"]: c["spec_name"] for c in _DATA["budget"]["counters"]}
BIASES = tuple(a["id"] for a in _DATA["budget"]["account_for"])
STATES = tuple(s["id"] for s in _DATA["oos"]["states"])
TRIGGERS = tuple(t["id"] for t in _DATA["oos"]["exposure_triggers"])
PERIODS = {p["id"]: p for p in _DATA["oos"].get("periods") or ()}
UNRECORDED = tuple(_DATA["budget"].get("_known_unrecorded") or ())


def counter_name(cid):
    if cid not in COUNTER_NAMES:
        raise NotDeclared(f"no §43 counter {cid!r}; the seven are {list(COUNTERS)}")
    return COUNTER_NAMES[cid]


def period(pid):
    p = PERIODS.get(pid)
    if p is None:
        raise NotDeclared(f"no declared period {pid!r}; they are {list(PERIODS)}")
    return p


def state_of(pid):
    return period(pid)["state"]


# ---- §43: the budget, computed from the §42 store


def _swept(rec):
    """Does this experiment's parameter diff describe a SWEEP rather than a single choice?

    A sweep of twenty values is twenty tests wearing one hypothesis, and §43 lists parameter searches
    separately from candidates precisely so the two cannot be conflated.
    """
    params = rec.get("parameters")
    if X.is_unavailable(params) or not isinstance(params, dict):
        return False
    for v in params.values():
        if isinstance(v, (list, tuple)) and len(v) > 1:
            return True
        if isinstance(v, dict) and any(k in v for k in ("range", "sweep", "values")):
            return True
    return False


def budget(records=None):
    """§43's seven counters over the experiment store, plus what is known to be unrecorded.

    Every number here is DERIVED. §43 says "do not hide the number of experiments performed", and a number
    maintained by hand beside the store is a number that will eventually disagree with it.
    """
    recs = list(records if records is not None else X.all_records())
    decisions = [r for r in recs if isinstance(r.get("decision"), dict)]
    hypotheses = {str(r.get("hypothesis")) for r in recs}
    candidates = {str(r.get("candidate_version")) for r in recs}
    ds_reuse, oos_reuse = {}, {}
    for r in recs:
        snap = r.get("dataset_snapshot")
        sid = snap.get("snapshot_id") if isinstance(snap, dict) else None
        if sid:
            ds_reuse[sid] = ds_reuse.get(sid, 0) + 1
        tp = r.get("test_periods")
        if isinstance(tp, dict):
            for key, val in tp.items():
                if "oos" in key.lower() or "holdout" in key.lower():
                    oos_reuse[str(val)] = oos_reuse.get(str(val), 0) + 1
    counts = {
        "hypothesis_count": len(hypotheses),
        "candidate_count": len(candidates),
        "parameter_searches": sum(1 for r in recs if _swept(r)),
        "dataset_reuse": ds_reuse,
        "oos_reuse": oos_reuse,
        "exposed_oos_periods": [pid for pid, p in PERIODS.items() if p["state"] == EXPOSED],
        "rejected_candidates": sum(1 for r in decisions if r["decision"].get("decision") == "REJECTED"),
    }
    missing = [c for c in COUNTERS if c not in counts]
    if missing:                      # a declared counter nobody computes is a number silently reported as 0
        raise RegistryError(f"§43 counters with no computation: {missing}")
    return {"experiments_recorded": len(recs), "counts": counts,
            "unrecorded": [dict(u) for u in UNRECORDED],
            "account_for": {b: _DATA["budget"]["account_for"][i]["means"] for i, b in enumerate(BIASES)},
            "_note": "`unrecorded` is NOT added to `counts`: a search that predates the experiment store and "
                     "has been folded into a total is indistinguishable from one that was recorded. "
                     "CLAUDE.md §43: 'Do not hide the number of experiments performed.'",
            "_source": "docs/architecture/research-ledger.json (CLAUDE.md §43)"}


# ---- §44: exposure, and the one-way door


def periods():
    """Every declared period with its §44 state, grouped so the answer to 'what can still validate?' is one
    lookup rather than a scan."""
    out = {s: [] for s in STATES}
    for pid, p in PERIODS.items():
        out[p["state"]].append({"id": pid, "range": p["range"], "why": p["why"]})
    return {"by_state": out,
            "validation_available": bool(out[UNTOUCHED] or out[HOLDOUT]),
            "_note": _DATA["oos"].get("_no_untouched_period_exists"),
            "_source": "docs/architecture/research-ledger.json (CLAUDE.md §44)"}


def expose(pid, *, trigger, experiment_id=None, note=None):
    """Move a period to `oos_exposed`. One-way, by construction.

    Returns the new state. Raises if the period is already `development` (it was never validation data) --
    that is not an error the caller should swallow, it means the caller believed something false about which
    data it was using.
    """
    p = period(pid)
    if trigger not in TRIGGERS:
        raise NotDeclared(f"no §44 exposure trigger {trigger!r}; the five are {list(TRIGGERS)}")
    if p["state"] == DEVELOPMENT:
        raise NotValidationData(
            f"{pid!r} is {DEVELOPMENT} data: it was never out-of-sample, so it cannot BECOME exposed. If a "
            f"caller expected to be validating here, the expectation is what is wrong.")
    if p["state"] == EXPOSED:
        return EXPOSED                       # idempotent: exposing twice is not an error, un-exposing is
    p["state"] = EXPOSED
    p.setdefault("exposures", []).append({"trigger": trigger, "experiment_id": experiment_id, "note": note})
    return EXPOSED


def unexpose(pid, *_a, **_kw):
    """Always raises. CLAUDE.md §44: 'Do not label it as pristine validation anymore.'

    Present so that the refusal is something a caller can find and read, rather than an absence they work
    around by editing the registry -- which is the move this function exists to make awkward.
    """
    raise ExposureIsOneWay(
        f"{pid!r} cannot be returned to {UNTOUCHED}. CLAUDE.md §44: once OOS data has materially influenced "
        f"candidate selection, parameter selection, hypothesis refinement, methodology changes or setup "
        f"selection, that period is exposed and must not be labelled pristine validation again. Carve out a "
        f"NEW period instead -- the only thing that restores validation capacity is data nobody has read.")


def assert_untouched(pid):
    """Raise unless this period can still validate something. The guard a validation run should call first."""
    st = state_of(pid)
    if st in (UNTOUCHED, HOLDOUT):
        return st
    raise NotValidationData(
        f"{pid!r} is {st}: {period(pid)['why']} A result measured here is a description of data the candidate "
        f"was chosen on, not a validation of it (CLAUDE.md §44).")


def describe():
    b, p = budget(), periods()
    lines = [f"§43 budget: {b['experiments_recorded']} experiment(s) recorded"]
    for cid in COUNTERS:
        v = b["counts"][cid]
        lines.append(f"  {counter_name(cid):<24} {v if not isinstance(v, dict) else dict(v)}")
    if b["unrecorded"]:
        lines.append(f"  UNRECORDED (not counted above): {len(b['unrecorded'])}")
        for u in b["unrecorded"]:
            lines.append(f"    - [{u['bias']}] {u['what']}")
    lines.append("")
    lines.append("§44 OOS exposure:")
    for st in STATES:
        got = p["by_state"][st]
        lines.append(f"  {st:<16} {len(got)}" + (f"  ({', '.join(x['id'] for x in got)})" if got else ""))
    if not p["validation_available"]:
        lines.append("  -> NO period can currently validate anything; see the registry's own note.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
