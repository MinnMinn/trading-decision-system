"""CLAUDE.md §36 -- THE reader for docs/architecture/decision-order.json, the canonical decision ordering.

§36 names seventeen steps and one critical invariant: the live path must wait for every REQUIRED dependency
and must not wait for anything else. This module makes the ordering executable. A decision builds a `Trace`,
records each step as it happens, and the Trace refuses three things outright:

1. **Out of order.** Recording step 14 and then step 10 raises. Steps may be SKIPPED; they may not be
   reordered. "The Decision Engine must preserve canonical decision ordering" is §36's first sentence.
2. **Blocking where blocking is forbidden.** Step 17 (execution instruction generation) is the only step with
   `may_block: false`: by the time it runs the decision is made. A refusal discovered there is a defect in
   steps 1-16, not a decision.
3. **Blocking on something that may not gate.** A blocking record that names a dependency is put through
   `trading_system.assert_may_gate` (§35), so an OPTIONAL_FOR_ANALYSIS / VISUALIZATION_ONLY / RESEARCH_ONLY
   input cannot stop an entry by being consulted at the wrong step.

    import decision_order as DO

    tr = DO.Trace("scalping", instrument="BTCUSDT", setup=row)
    tr.ok("market_instrument")
    tr.block("event_final", "blackout FOMC", dep="event_risk.calendar")
    tr.decision()        -> 'BLOCK_ENTRY'
    tr.verify()          -> raises OrderViolation if the sequence broke the rules

The outcome vocabulary is §20/§36's own: WAIT, NO_TRADE, BLOCK_ENTRY, UNKNOWN, HUMAN_CONFIRMATION, plus OK
and SKIPPED, which are not decisions.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import trading_system as TS

PATH = os.path.join(ROOT, "docs", "architecture", "decision-order.json")

OK, SKIPPED = "OK", "SKIPPED"
# §20's five outcomes for a failing required input, in the order §20 lists them. Most restrictive first is a
# different question (quality.py owns that); this tuple is the vocabulary, not a ranking.
BLOCKING = ("WAIT", "NO_TRADE", "BLOCK_ENTRY", "UNKNOWN", "HUMAN_CONFIRMATION")
OUTCOMES = (OK, SKIPPED) + BLOCKING

PATHS = ("live", "analyze", "backtest")


class RegistryError(ValueError):
    """The ordering registry itself is wrong -- raised at import, never at decision time."""


class OrderViolation(RuntimeError):
    """A decision executed the canonical steps in an order, or with a block, that §36 forbids."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return _validate(data, path)


def _validate(data, path):
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RegistryError(f"{path}: `steps` must be a non-empty list")
    seen = set()
    for i, s in enumerate(steps, start=1):
        if s.get("n") != i:
            raise RegistryError(f"{path}: step {s.get('id')!r} is at position {i} but declares n={s.get('n')}; "
                                f"CLAUDE.md §36's numbering IS the order and may not be renumbered locally")
        for field in ("id", "name", "why"):
            if not str(s.get(field) or "").strip():
                raise RegistryError(f"{path}: step {i} has no {field!r}")
        if s["id"] in seen:
            raise RegistryError(f"{path}: duplicate step id {s['id']!r}")
        seen.add(s["id"])
        if not isinstance(s.get("may_block"), bool):
            raise RegistryError(f"{path}: step {s['id']!r} must declare may_block true or false")
        for dep in s.get("dependencies") or ():
            if dep not in TS.DEPENDENCIES:
                raise RegistryError(
                    f"{path}: step {s['id']!r} names dependency {dep!r}, which is not classified in "
                    f"docs/architecture/trading-systems.json. A decision step may only consult a dependency "
                    f"§35 has given a role -- otherwise the step could gate on something nobody classified.")
        for p in PATHS:
            if p not in s:
                raise RegistryError(f"{path}: step {s['id']!r} does not say where it lives on the {p!r} path; "
                                    f"declare a citation or null with a _{p}_why")
            if s[p] is None and not str(s.get(f"_{p}_why") or "").strip():
                raise RegistryError(
                    f"{path}: step {s['id']!r} is unimplemented on the {p!r} path and does not say why. A "
                    f"canonical step that no path implements must SAY so -- that is how the missing event-risk "
                    f"precheck stayed invisible until 2026-09-18.")
    return data


_DATA = _load()
STEPS = tuple(_DATA["steps"])
ORDER = tuple(s["id"] for s in STEPS)
BY_ID = {s["id"]: s for s in STEPS}


def step(step_id):
    s = BY_ID.get(step_id)
    if s is None:
        raise KeyError(f"no canonical decision step {step_id!r}; §36's steps are {list(ORDER)}")
    return s


def position(step_id):
    """1-based position in CLAUDE.md §36's own numbering."""
    return step(step_id)["n"]


def implemented(path):
    """Step ids that have an implementation on this path ('live', 'analyze' or 'backtest')."""
    if path not in PATHS:
        raise KeyError(f"unknown path {path!r}; the decision paths are {list(PATHS)}")
    return tuple(s["id"] for s in STEPS if s[path])


def unimplemented(path):
    """Step ids declared absent on this path, with the declared reason. Absence is data, not silence."""
    return {s["id"]: s[f"_{path}_why"] for s in STEPS if not s[path]}


def dependencies_of(step_id):
    return tuple(step(step_id).get("dependencies") or ())


class Trace:
    """One decision's walk through the canonical order.

    `style` is the §35 Trading System id; `setup` and `instrument` are the context §35 needs to resolve a
    conditional role. A Trace with no style still records and orders, but cannot check gate legality, so it
    refuses a blocking record that names a dependency rather than letting one through unchecked.
    """

    def __init__(self, style=None, *, setup=None, instrument=None, engaged=None):
        self.style = style
        self.ctx = {"setup": setup, "instrument": instrument, "engaged": engaged}
        self.rows = []
        self._last_n = 0

    # ---- recording
    def record(self, step_id, outcome=OK, why=None, dep=None):
        s = step(step_id)
        if outcome not in OUTCOMES:
            raise ValueError(f"{outcome!r} is not a §36/§20 outcome; they are {list(OUTCOMES)}")
        if s["n"] <= self._last_n:
            prev = self.rows[-1]["step"] if self.rows else "(none)"
            raise OrderViolation(
                f"canonical ordering violated: step {s['n']} {step_id!r} recorded after step "
                f"{self._last_n} {prev!r}. CLAUDE.md §36: 'The Decision Engine must preserve canonical "
                f"decision ordering.' Steps may be skipped; they may not be reordered.")
        if outcome in BLOCKING:
            if not s["may_block"]:
                raise OrderViolation(
                    f"step {s['n']} {step_id!r} returned {outcome} but declares may_block=false. By this step "
                    f"the decision is already made -- a refusal here is a defect in steps 1-{s['n'] - 1}, not "
                    f"a decision (CLAUDE.md §36).")
            if dep is not None:
                if self.style is None:
                    raise OrderViolation(
                        f"cannot block on {dep!r} at {step_id!r}: this Trace names no Trading System, so §35's "
                        f"classification cannot be consulted. An unchecked gate is the thing §62 forbids.")
                TS.assert_may_gate(self.style, dep, **self.ctx)
        self._last_n = s["n"]
        self.rows.append({"n": s["n"], "step": step_id, "outcome": outcome, "why": why, "dep": dep})
        return outcome

    def ok(self, step_id, why=None):
        return self.record(step_id, OK, why)

    def skip(self, step_id, why):
        """A step this system does not implement. Requires a reason -- a silent skip is indistinguishable
        from a step that was forgotten, which is the failure mode §36 exists to prevent."""
        if not str(why or "").strip():
            raise ValueError(f"skipping {step_id!r} requires a reason")
        return self.record(step_id, SKIPPED, why)

    def block(self, step_id, why, outcome="BLOCK_ENTRY", dep=None):
        return self.record(step_id, outcome, why, dep)

    # ---- reading
    def blocked(self):
        return [r for r in self.rows if r["outcome"] in BLOCKING]

    def decision(self):
        """The first blocking outcome in canonical order, or None when nothing blocked."""
        b = self.blocked()
        return b[0]["outcome"] if b else None

    def reasons(self):
        return [r["why"] for r in self.blocked() if r["why"]]

    def reached(self):
        return tuple(r["step"] for r in self.rows)

    def verify(self):
        """Raise unless this trace is a legal §36 walk. Ordering and gate legality are already enforced at
        record() time; what verify adds is the completeness question: an order was placed (step 17 reached)
        only if nothing before it blocked."""
        if "execution_instruction" in self.reached() and self.blocked():
            first = self.blocked()[0]
            raise OrderViolation(
                f"an execution instruction was generated after step {first['n']} {first['step']!r} returned "
                f"{first['outcome']} ({first['why']}). CLAUDE.md §62: a blocked decision does not proceed.")
        return True

    def as_log(self):
        """Compact, auditable form for a log line (§19 explainability, §36 ordering)."""
        return " > ".join(f"{r['n']}:{r['step']}" + ("" if r["outcome"] == OK else f"={r['outcome']}")
                          for r in self.rows)

    def snapshot(self):
        return {"trading_system": self.style, "steps": list(self.rows), "decision": self.decision(),
                "source": "docs/architecture/decision-order.json"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Canonical decision ordering (CLAUDE.md §36).")
    ap.add_argument("--path", choices=PATHS, help="show where each step lives on this path")
    args = ap.parse_args()
    for s in STEPS:
        line = f"{s['n']:>2}. {s['id']:<26} {'gate' if s['may_block'] else 'act ':<5}"
        if args.path:
            line += "  " + (s[args.path] or f"NOT IMPLEMENTED -- {s['_' + args.path + '_why']}")
        else:
            line += "  " + s["name"]
        print(line)
    if args.path:
        missing = unimplemented(args.path)
        print(f"\n{len(implemented(args.path))}/{len(STEPS)} implemented on {args.path}; "
              f"declared absent: {', '.join(missing) or '(none)'}")
