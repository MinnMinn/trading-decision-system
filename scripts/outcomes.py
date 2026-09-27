"""CLAUDE.md §41 -- THE reader for docs/architecture/outcomes.json: what happened, what it may mean, and who
is allowed to change production because of it.

§41 asks for eight outcome states. **Five of them could not be expressed anywhere in this repo.** A trade file
carries WIN / LOSS / BREAKEVEN; the runner logged every block reason into `pilot-selection-log.jsonl` and *nothing ever
read it back*, so "the filter saved us" and "the filter cost us a winner" were the same silence.

    import outcomes as O

    rows = O.ingest()                       # the pilot log + the trade journal -> §41 outcome records
    O.distribution(rows)                    # every state, including the ones with zero
    O.resolve(rows, candles_by_symbol)      # a blocked entry that WOULD have worked becomes MISSED_OPPORTUNITY
    clusters = O.cluster(rows, min_size=3)  # §41 stage 3: a repeated failure, not a single bad day

    p = O.Proposal("widen the stop on 15m ICT", hypothesis="...", author="learning-agent")
    p.stage("backtest", evidence="docs/backtests/...")
    p.decide("APPROVED", actor="claude")    -> raises: §41 reserves this for a human

Three properties this module exists to hold:

1. **NO_TRADE and BLOCKED_ENTRY are not failures.** §41 says so directly, and `is_failure` is therefore
   THREE-VALUED: `True`, `False`, or `None` for "this needs a counterfactual nobody has computed". The
   default for an evaluation state is `None`. Any code that treats a blocked entry as a failure by default is
   measuring its own filter as a defect.
2. **UNKNOWN is a real cause and the default.** §41: "Do not force every outcome into a causal category." A
   distribution where every outcome has a confident cause is a distribution nobody checked.
3. **A proposal cannot become production silently.** There is no writer here for the Trading System registry
   or the pilot selection; `Proposal.decide()` refuses any actor but `human`; and a proposal that has not
   passed every implemented pipeline stage cannot be APPROVED at all. §41's word is *silently*, and the
   mechanism is that a change must be a visible, recorded, human-decided artifact.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PATH = os.path.join(ROOT, "docs", "architecture", "outcomes.json")

REALISED, EVALUATION, FAULT = "realised", "evaluation", "fault"
UNKNOWN = "UNKNOWN"

#: Where the live path writes what happened. Read-only here.
PILOT_LOGS = (os.path.join(ROOT, "data", "live", "pilot-futures", "pilot-selection-log.jsonl"),
              os.path.join(ROOT, "data", "live", "pilot-futures", "pilot-selection-mt5-log.jsonl"),
              os.path.join(ROOT, "data", "live", "pilot-futures", "log.jsonl"))
JOURNAL = os.path.join(ROOT, "trades", "index.jsonl")

DECISIONS = ("APPROVED", "REJECTED", "DEFERRED")


class RegistryError(ValueError):
    """The §41 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something used an outcome state, cause or stage CLAUDE.md §41 does not name."""


class HumanDecisionRequired(RuntimeError):
    """Something that is not a human tried to decide a proposal."""


class PipelineIncomplete(RuntimeError):
    """A proposal tried to skip a stage of §41's pipeline."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    states = data.get("states")
    if not isinstance(states, list) or not states:
        raise RegistryError(f"{path}: `states` must be a non-empty list")
    seen = set()
    for st in states:
        for field in ("id", "spec_name", "family", "definition"):
            if not str(st.get(field) or "").strip():
                raise RegistryError(f"{path}: state {st.get('id')!r} has no {field!r}")
        if st["id"] in seen:
            raise RegistryError(f"{path}: duplicate state id {st['id']!r}")
        seen.add(st["id"])
        if st["family"] not in (REALISED, EVALUATION, FAULT):
            raise RegistryError(f"{path}: state {st['id']!r} has family {st['family']!r}; §41's families are "
                                f"{REALISED!r}, {EVALUATION!r}, {FAULT!r}")
        if "is_failure" not in st:
            raise RegistryError(f"{path}: state {st['id']!r} must declare is_failure true, false or null. "
                                f"null is 'needs a counterfactual', and it is the only honest answer for an "
                                f"evaluation state (§41).")
        if st["family"] == EVALUATION and st["is_failure"] is not None:
            raise RegistryError(
                f"{path}: state {st['id']!r} is an evaluation state and declares is_failure="
                f"{st['is_failure']!r}. CLAUDE.md §41: 'NO TRADE and BLOCKED ENTRY must NOT automatically be "
                f"classified as failures. They are evaluation states.' Automatic is exactly what a non-null "
                f"default here would be.")
        if st["is_failure"] is None and not str(st.get("_is_failure_why") or "").strip():
            raise RegistryError(f"{path}: state {st['id']!r} declares is_failure null and does not say why")
    stages = data.get("pipeline") or []
    for i, s in enumerate(stages, start=1):
        if s.get("n") != i:
            raise RegistryError(f"{path}: pipeline stage {s.get('id')!r} is at position {i} but declares "
                                f"n={s.get('n')}; §41's pipeline IS the order")
        if s.get("implemented_by") is None and not str(s.get("_why") or "").strip():
            raise RegistryError(f"{path}: pipeline stage {s['id']!r} has no implementation and does not say "
                                f"why -- an unimplemented stage that nobody declared is a stage a proposal "
                                f"will quietly skip")
    return data, {s["id"]: s for s in states}, tuple(s["id"] for s in states), tuple(stages)


_DATA, STATES, ORDER, PIPELINE = _load()
CAUSES = tuple(c["id"] for c in _DATA.get("causes") or ())
REVEALS = tuple(r["id"] for r in _DATA.get("reveals") or ())
STAGE_ORDER = tuple(s["id"] for s in PIPELINE)
IMPLEMENTED_STAGES = tuple(s["id"] for s in PIPELINE if s.get("implemented_by"))
#: Stages §41 requires that this repo cannot perform at all. `hypothesis_generation` is deliberately NOT
#: here: it has no code because a hypothesis is prose, and a Proposal cannot be constructed without one -- the
#: record IS the implementation. §44 (OOS exposure) and §45 (robustness) are genuinely absent, and a proposal
#: must not be adoptable through that gap.
ABSENT_STAGES = {s["id"]: s.get("_why") for s in PIPELINE
                 if not s.get("implemented_by") and s["id"] != "hypothesis_generation"}
AI_MAY = tuple(a["spec_name"] for a in _DATA.get("ai_may") or ())


def state(sid):
    st = STATES.get(sid)
    if st is None:
        raise NotDeclared(f"no §41 outcome state {sid!r}; the eight are {list(ORDER)}")
    return st


def spec_name(sid):
    return state(sid)["spec_name"]


def family(sid):
    return state(sid)["family"]


def is_failure(sid):
    """True / False / None. `None` means 'not knowable from the record alone' and is NOT a soft no."""
    return state(sid)["is_failure"]


def evaluation_states():
    return tuple(s for s in ORDER if STATES[s]["family"] == EVALUATION)


def cause(cid):
    if cid != UNKNOWN and cid not in CAUSES:
        raise NotDeclared(f"no §41 cause {cid!r}; the four are {list(CAUSES)} plus {UNKNOWN!r}, which is "
                          f"valid and is the default")
    return cid


def record(state_id, *, at=None, symbol=None, setup=None, detail=None, cause_id=UNKNOWN, blocked_on=None,
           r=None, reveals=None, source=None):
    """One §41 outcome record.

    `cause_id` defaults to UNKNOWN on purpose: §41 says unknown is a valid causal state and that outcomes must
    not be forced into a category. `reveals` is only meaningful for an evaluation state and is refused
    elsewhere -- 'this WIN reveals beneficial filtering' is not a sentence §41 makes available.
    """
    st = state(state_id)
    cause(cause_id)
    if reveals is not None:
        if st["family"] != EVALUATION:
            raise NotDeclared(f"`reveals` applies to an evaluation state; {state_id!r} is {st['family']}")
        for r_ in reveals:
            if r_ not in REVEALS:
                raise NotDeclared(f"no §41 reveal {r_!r}; the five are {list(REVEALS)}")
    return {"state": state_id, "family": st["family"], "is_failure": st["is_failure"], "at": at,
            "symbol": symbol, "setup": setup, "detail": detail, "cause": cause_id,
            "blocked_on": blocked_on, "r": r, "reveals": list(reveals or ()), "source": source}


# ---- ingest: the live path already writes all eight; nothing read them back


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def _from_log_row(row, source):
    """One pilot-log line -> an outcome record, or None when the line is not an outcome.

    This is the function whose absence was the §41 gap: every one of these lines existed and none was ever
    turned into a record anything could count.
    """
    kind = row.get("kind")
    at, sym = row.get("t"), row.get("symbol")
    if row.get("drill"):
        return None                           # plan §0.11: a drill is a rehearsal of the path, not an outcome
    if kind == "signal":
        reasons = row.get("reasons") or []
        if row.get("ok") and not reasons:
            return None                       # an accepted signal becomes a TRADE; the journal carries it
        dep = next((r.split(":")[0].strip() for r in reasons if ":" in str(r)), None)
        blocking = bool(reasons)
        return record("BLOCKED_ENTRY" if blocking else "NO_TRADE", at=at, symbol=sym,
                      setup=row.get("strategy"), detail="; ".join(str(r) for r in reasons) or None,
                      blocked_on=dep, source=source)
    if kind in ("rejected", "gtx_rejected"):
        return record("EXECUTION_FAILURE", at=at, symbol=sym, setup=row.get("strategy"),
                      detail=row.get("note") or row.get("why"), cause_id="execution_failure", source=source)
    if kind == "skip":
        # A venue floor refusal is an execution failure; anything else the runner calls a skip is a NO TRADE.
        why = str(row.get("why") or "")
        venue_floor = any(w in why for w in ("volume_min", "MIN_NOTIONAL", "notional below"))
        return record("EXECUTION_FAILURE" if venue_floor else "NO_TRADE", at=at, symbol=sym,
                      setup=row.get("strategy"), detail=why,
                      cause_id="execution_failure" if venue_floor else UNKNOWN, source=source)
    if kind == "error":
        why = str(row.get("msg") or row.get("why") or "")
        data = any(w in why.lower() for w in ("quality", "stale", "fetch", "no mt5 export", "calendar"))
        return record("DATA_FAILURE" if data else "EXECUTION_FAILURE", at=at, symbol=sym,
                      detail=why, cause_id="data_failure" if data else UNKNOWN, source=source)
    if kind in ("halt", "preset_filtered", "unscannable_tf"):
        return record("NO_TRADE", at=at, symbol=sym, setup=row.get("setup") or row.get("strategy"),
                      detail=row.get("why"), source=source)
    return None


def _from_trade(row, source):
    r = row.get("r_multiple")
    if row.get("status") != "CLOSED" or not isinstance(r, (int, float)) or row.get("drill"):
        return None                           # plan §0.11: drills are never WIN/LOSS evidence
    band = 0.05
    sid = "BREAKEVEN" if abs(r) <= band else ("WIN" if r > 0 else "LOSS")
    return record(sid, at=row.get("date_closed"), symbol=row.get("instrument"),
                  setup=row.get("setup_type"), r=float(r),
                  cause_id=(row.get("root_cause") if row.get("root_cause") in CAUSES else UNKNOWN),
                  source=source)


def ingest(logs=PILOT_LOGS, journal=JOURNAL):
    """Every §41 outcome the repo can currently produce, from the live log and the trade journal."""
    out = []
    for p in logs:
        rel = os.path.relpath(p, ROOT)
        for row in _read_jsonl(p):
            rec = _from_log_row(row, rel)
            if rec:
                out.append(rec)
    for row in _read_jsonl(journal):
        rec = _from_trade(row, os.path.relpath(journal, ROOT))
        if rec:
            out.append(rec)
    out.sort(key=lambda r: r["at"] or "")
    return out


def distribution(rows):
    """Every declared state with its count -- including the ones that are zero.

    Zero is information: 'no execution failure was recorded' and 'execution failure cannot be recorded' look
    identical in a dict that omits empty keys, and the second was this repo's actual state until today.
    """
    counts = {s: 0 for s in ORDER}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"n": len(rows), "counts": counts,
            "failures": sum(1 for r in rows if r["is_failure"] is True),
            "needs_counterfactual": sum(1 for r in rows if r["is_failure"] is None),
            "by_cause": {c: sum(1 for r in rows if r["cause"] == c) for c in (UNKNOWN,) + CAUSES},
            "_note": "is_failure null means the record alone cannot say; §41 forbids counting NO TRADE and "
                     "BLOCKED ENTRY as failures by default"}


# ---- resolution: the counterfactual an evaluation state needs


def resolve(rows, candles_by_symbol, *, horizon=96):
    """Turn a NO_TRADE / BLOCKED_ENTRY into MISSED_OPPORTUNITY where the plan WOULD have worked.

    Requires the plan (entry/stop/target) and the bars after it, and says so when it cannot. The horizon is
    explicit and travels in the record: "would have won" is meaningless without "by when", and a long enough
    horizon makes almost anything a missed opportunity.

    This is a counterfactual on ONE path of prices that did happen. It is evidence, not proof, and §41's
    `reveals` vocabulary is where that distinction lives.
    """
    out = []
    for r in rows:
        if r["family"] != EVALUATION or not (r.get("plan") and r["symbol"]):
            out.append(r)
            continue
        plan, c = r["plan"], candles_by_symbol.get(r["symbol"]) or []
        idx = next((i for i, x in enumerate(c) if x["time"] >= (r["at"] or "")), None)
        if idx is None:
            out.append(dict(r, resolution="unresolvable: no bars after this decision"))
            continue
        long = plan["target"] > plan["entry"]
        won = None
        for x in c[idx:idx + horizon]:
            hit_stop = x["low"] <= plan["stop"] if long else x["high"] >= plan["stop"]
            hit_tgt = x["high"] >= plan["target"] if long else x["low"] <= plan["target"]
            if hit_stop:                       # same-bar both = stop, matching the backtest's convention
                won = False
                break
            if hit_tgt:
                won = True
                break
        if won is True:
            out.append(dict(record("MISSED_OPPORTUNITY", at=r["at"], symbol=r["symbol"], setup=r["setup"],
                                   detail=r["detail"], blocked_on=r.get("blocked_on"), source=r["source"],
                                   reveals=["missed_opportunities"]),
                            resolves=r["state"], horizon_bars=horizon, plan=plan))
        elif won is False:
            out.append(dict(r, reveals=["beneficial_filtering"], horizon_bars=horizon,
                            resolution="would have stopped out"))
        else:
            out.append(dict(r, horizon_bars=horizon,
                            resolution="neither target nor stop reached inside the horizon"))
    return out


def cluster(rows, *, by=("setup", "blocked_on", "cause"), min_size=3):
    """§41 stages 2-3: a repeated failure CLUSTER, not a single bad day.

    `min_size` is what separates the two, and it is the caller's to choose and the report's to state. Groups
    below it are returned too, under `singletons`, so a reader can see how much was left out rather than
    inferring it -- the same reason §39 insists on sample size.
    """
    groups = {}
    for r in rows:
        if r["is_failure"] is False:
            continue                    # a win is not a failure pattern
        key = tuple(str(r.get(k)) for k in by)
        groups.setdefault(key, []).append(r)
    big = [{"key": dict(zip(by, k)), "n": len(v), "states": sorted({x["state"] for x in v}),
            "examples": [x.get("detail") for x in v[:3] if x.get("detail")]}
           for k, v in groups.items() if len(v) >= min_size]
    big.sort(key=lambda g: -g["n"])
    return {"min_size": min_size, "grouped_by": list(by), "clusters": big,
            "singletons": sum(1 for v in groups.values() if len(v) < min_size),
            "_note": "a cluster is evidence of a REPEATED failure; one occurrence is an anecdote (§41 stage 3)"}


# ---- the proposal, and the human who decides it


class Proposal:
    """§41 stages 5-11: a candidate change, its evidence, and the human decision at the end.

    The reason this is a class rather than a document convention: §41's prohibition is on a SILENT rewrite,
    and silence is prevented by making the artifact mandatory, ordered and unapprovable until the pipeline has
    been walked. There is no method here that writes to docs/architecture/trading-systems.json or
    docs/architecture/pilot-selection.json, and there is not meant to be one.
    """

    def __init__(self, title, *, hypothesis, author, cluster=None, baseline=None):
        if not str(title or "").strip() or not str(hypothesis or "").strip():
            raise ValueError("a §41 proposal needs a title and a hypothesis")
        if not str(author or "").strip():
            raise ValueError("a §41 proposal must name its author -- §41 distinguishes what AI MAY do from "
                             "what only a human may")
        self.title, self.hypothesis, self.author = title, hypothesis, author
        self.cluster, self.baseline = cluster, baseline
        self.stages = {}
        self.decision = None
        self.decided_by = None

    def stage(self, sid, *, evidence):
        """Record that a pipeline stage was completed, with the artifact that proves it."""
        if sid not in STAGE_ORDER:
            raise NotDeclared(f"no §41 pipeline stage {sid!r}; they are {list(STAGE_ORDER)}")
        if not str(evidence or "").strip():
            raise ValueError(f"stage {sid!r} needs evidence -- a path, a report, a run id. A stage marked "
                             f"complete with nothing behind it is the pipeline being skipped politely.")
        self.stages[sid] = evidence
        return self

    def missing(self):
        """Implemented stages this proposal has not passed. Unimplemented stages (§44, §45) are NOT silently
        excused -- they are returned separately by `blocked_by`."""
        return tuple(s for s in IMPLEMENTED_STAGES
                     if s not in self.stages and s not in ("hypothesis_generation", "human_decision"))

    def blocked_by(self):
        """Stages §41 requires that this proposal cannot pass. A proposal cannot be APPROVED through one.

        Two sources, deliberately:

          * `ABSENT_STAGES` -- a stage with no implementation at all, declared in the registry.
          * the §44 ledger -- a stage that IS implemented but has no data to run on. Since 2026-09-18
            `scripts/validation.py` implements OOS validation and robustness, so the registry no longer calls
            them absent; what still blocks an approval is that NO period in this repo is untouched, and that
            fact belongs to the ledger and changes when a period is carved out. Hardcoding it here would leave
            a stale refusal standing on the day the data finally exists.
        """
        out = dict(ABSENT_STAGES)
        try:
            import research_ledger as RL
            if not RL.periods()["validation_available"]:
                out["oos_validation"] = (
                    "implemented (scripts/validation.py oos()) but unrunnable: CLAUDE.md §44 says no period "
                    "in this repo is out-of-sample and untouched, so there is nothing to validate ON. See "
                    "docs/architecture/research-ledger.json.")
        except Exception:
            out["oos_validation"] = ("the §44 OOS ledger could not be read, so it is unknown whether any "
                                     "period can validate anything -- unknown blocks approval (§45's posture)")
        return out

    def compare(self, *, baseline, candidate):
        """§41 stage 9. Stores both sides; it does not judge them -- judging is stage 11 and it is a human's."""
        self.baseline = {"baseline": baseline, "candidate": candidate}
        return self.stage("compare_against_baseline", evidence="in-record comparison")

    def report(self):
        """§41 stage 10: the improvement report, including what is missing. A report that lists only the
        stages that passed is how an incomplete pipeline reads as a complete one."""
        return {"title": self.title, "hypothesis": self.hypothesis, "author": self.author,
                "cluster": self.cluster, "comparison": self.baseline,
                "stages_passed": dict(self.stages), "stages_missing": list(self.missing()),
                "stages_not_possible_here": self.blocked_by(),
                "decision": self.decision, "decided_by": self.decided_by,
                "_source": "docs/architecture/outcomes.json (CLAUDE.md §41)"}

    def decide(self, decision, *, actor, note=None):
        """§41 stage 11. Reserved for a human, and refused before the pipeline has been walked.

        Two refusals, for two different failure modes: a model approving its own proposal, and anyone
        approving one whose evidence does not exist yet.
        """
        if decision not in DECISIONS:
            raise ValueError(f"{decision!r} is not a §41 decision; they are {list(DECISIONS)}")
        if str(actor).strip().lower() != "human":
            raise HumanDecisionRequired(
                f"{actor!r} may not decide a §41 proposal. CLAUDE.md §41 lists what AI MAY do -- "
                f"{', '.join(AI_MAY)} -- and 'AI must NEVER silently rewrite the production Trading System.' "
                f"The decision stage is the human's, and it is the only thing standing between a hypothesis "
                f"and the account.")
        if decision == "APPROVED":
            miss = self.missing()
            if miss:
                raise PipelineIncomplete(
                    f"cannot approve {self.title!r}: §41's pipeline has not been walked -- missing "
                    f"{', '.join(miss)}. Approving here would adopt a candidate on the strength of the "
                    f"hypothesis that produced it.")
            blocked = self.blocked_by()
            if blocked:
                raise PipelineIncomplete(
                    f"cannot approve {self.title!r}: §41 requires {', '.join(blocked)}, which this repo "
                    f"cannot yet perform ({'; '.join(blocked.values())}). The gap blocks adoption rather "
                    f"than being skipped.")
        self.decision, self.decided_by = decision, actor
        return self.report()


def describe(rows):
    d = distribution(rows)
    parts = [f"n={d['n']}"]
    for sid in ORDER:
        parts.append(f"{spec_name(sid)} {d['counts'][sid]}")
    return " · ".join(parts) + f" · failures {d['failures']} · needs-counterfactual {d['needs_counterfactual']}"


if __name__ == "__main__":
    rows = ingest()
    print(f"CLAUDE.md §41 -- {len(ORDER)} outcome states, {len(PIPELINE)} pipeline stages\n")
    print(describe(rows))
    cl = cluster(rows)
    print(f"\nclusters (min {cl['min_size']}): {len(cl['clusters'])}, singletons {cl['singletons']}")
    for c in cl["clusters"][:8]:
        print(f"  n={c['n']:<4} {c['key']}")
    if ABSENT_STAGES:
        print(f"\npipeline stages this repo cannot yet perform: {', '.join(ABSENT_STAGES)}")
