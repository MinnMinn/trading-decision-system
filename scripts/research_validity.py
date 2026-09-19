"""CLAUDE.md §38 -- THE reader for docs/architecture/research-validity.json: what a defect does to a run.

§38 is two sentences. The first lists ten kinds of evidence that must flag or invalidate a research run. The
second is the one with teeth:

    "Never silently produce a trustworthy-looking performance result from invalid research."

Before this module the repo could DETECT most of the ten -- §20 computes data-quality faults, §37's prober
finds look-ahead, §11's configuration snapshot records required dependencies the engine never consults -- and
then did nothing with any of them. Every finding ended as a line on stderr or a key in a snapshot, and the
performance table underneath printed exactly as if the run had been clean. That is the failure §38 names, and
detection without a verdict is precisely how it happens.

So:

    import research_validity as RV

    a = RV.Assessment("stability-report crypto 15m")
    a.checked("look_ahead", "leakage.probe: 214 decisions unchanged under 3 mutations")
    a.from_quality_flags(bt.QUALITY_FLAGS)
    a.from_config_snapshot(cfg_snap)
    a.verdict()        -> 'FLAGGED'
    block = a.stamp()  -> goes into the run's JSON, next to the §10 and §11 snapshots

and on the consuming side:

    RV.require(RV.read(doc, where=path), where=path, allow=(RV.VALID, RV.FLAGGED))

Four properties, each of which is the thing that would otherwise rot:

1. **A disposition is declared once, in the registry, with its reason.** Choosing per call site is how
   everything ends up flagged.
2. **Escalation only.** `finding()` accepts a stronger disposition than the registry's and REFUSES a weaker
   one. The direction that loses information is closed.
3. **Not-checked is a state.** A run that looked at nothing gets `UNVERIFIED`, not `VALID`. §38's last
   sentence is about a result that LOOKS trustworthy; a blank assessment looks exactly like a clean one.
4. **Unstamped is refused, not trusted.** `read()` raises on a research artifact carrying no verdict, so a
   consumer cannot quietly treat silence as a pass.

This module decides nothing about markets. It only says what a run's own evidence makes the run worth.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "architecture", "research-validity.json")

FLAGS, INVALIDATES = "FLAGS", "INVALIDATES"
DISPOSITIONS = (FLAGS, INVALIDATES)

VALID, FLAGGED, INVALID, UNVERIFIED = "VALID", "FLAGGED", "INVALID", "UNVERIFIED"
VERDICTS = (VALID, FLAGGED, INVALID, UNVERIFIED)

# How bad each disposition is. Used only to pick the worst finding; the verdict function below is the
# authority on what the absence of findings means.
_RANK = {FLAGS: 1, INVALIDATES: 2}


class RegistryError(ValueError):
    """The §38 registry itself is wrong -- raised at import, never mid-run."""


class NotDeclared(KeyError):
    """A finding named a condition CLAUDE.md §38 does not list."""


class Downgrade(RuntimeError):
    """A caller tried to make a condition matter LESS than the registry says it does."""


class InvalidResearch(RuntimeError):
    """A consumer was handed a research result §38 does not allow it to use."""


class Unstamped(RuntimeError):
    """A research artifact carries no §38 verdict, so nothing is known about whether it is one."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    conds = data.get("conditions")
    if not isinstance(conds, list) or not conds:
        raise RegistryError(f"{path}: `conditions` must be a non-empty list")
    seen = set()
    for c in conds:
        for field in ("id", "spec_bullet", "disposition", "why"):
            if not str(c.get(field) or "").strip():
                raise RegistryError(f"{path}: condition {c.get('id')!r} has no {field!r}")
        if c["id"] in seen:
            raise RegistryError(f"{path}: duplicate condition id {c['id']!r}")
        seen.add(c["id"])
        if c["disposition"] not in DISPOSITIONS:
            raise RegistryError(f"{path}: condition {c['id']!r} declares disposition {c['disposition']!r}; "
                                f"§38 offers {list(DISPOSITIONS)} ('flagged or invalidated')")
        if c.get("detector") is None and not str(c.get("_detector_why") or "").strip():
            raise RegistryError(
                f"{path}: condition {c['id']!r} has no detector and does not say why. A §38 condition nothing "
                f"looks for must SAY so -- that is the difference between UNVERIFIED and a silent pass.")
    return data, {c["id"]: c for c in conds}, tuple(c["id"] for c in conds)


_DATA, CONDITIONS, ORDER = _load()


def condition(cid):
    c = CONDITIONS.get(cid)
    if c is None:
        raise NotDeclared(f"no §38 condition {cid!r}; the ten are {list(ORDER)}")
    return c


def disposition_of(cid):
    return condition(cid)["disposition"]


def spec_bullet(cid):
    return condition(cid)["spec_bullet"]


def invalidating():
    return tuple(c for c in ORDER if CONDITIONS[c]["disposition"] == INVALIDATES)


class Assessment:
    """One research run's §38 evidence, and the verdict it earns.

    `run` is a human label for the run (what was measured), carried into the stamp so a verdict found in a
    file months later can be attached to something.
    """

    def __init__(self, run=None):
        self.run = run
        self._findings = []
        self._cleared = {}          # cid -> what was checked and found clear
        self._na = {}               # cid -> why the condition cannot apply to this run

    # ---- recording
    def finding(self, cid, detail, *, source=None, disposition=None):
        """Record evidence that a §38 condition fired.

        `disposition` may only ESCALATE: a FLAGS condition may be raised to INVALIDATES by a caller with
        evidence the defect was worse than the general case (corruption across the whole series rather than
        one bar, say). Lowering is refused -- that direction is how an invalid run becomes a footnote.
        """
        c = condition(cid)
        if not str(detail or "").strip():
            raise ValueError(f"a §38 finding on {cid!r} needs a detail; an unexplained flag is not evidence")
        declared = c["disposition"]
        if disposition is None:
            disposition = declared
        elif disposition not in DISPOSITIONS:
            raise ValueError(f"{disposition!r} is not a §38 disposition; they are {list(DISPOSITIONS)}")
        elif _RANK[disposition] < _RANK[declared]:
            raise Downgrade(
                f"refusing to record {cid!r} as {disposition} when docs/architecture/research-validity.json "
                f"declares it {declared}: {c['why']} A caller may escalate a §38 condition, never soften one.")
        self._cleared.pop(cid, None)
        self._na.pop(cid, None)
        self._findings.append({"condition": cid, "spec_bullet": c["spec_bullet"],
                               "disposition": disposition, "escalated": disposition != declared,
                               "detail": detail, "source": source})
        return disposition

    def checked(self, cid, note):
        """This condition was looked for on this run and not found. Requires saying HOW it was looked for --
        `checked("look_ahead", "reviewed the code")` and `checked("look_ahead", "leakage.probe over 8,071
        trades, 3 mutation modes, 0 violations")` must not read the same in the record."""
        condition(cid)
        if not str(note or "").strip():
            raise ValueError(f"clearing {cid!r} requires saying what was run; an unevidenced clear is a claim")
        if any(f["condition"] == cid for f in self._findings):
            raise ValueError(f"{cid!r} already has a finding on this run; it cannot also be clear")
        self._cleared[cid] = note
        return self

    def not_applicable(self, cid, why):
        """This condition cannot apply to this run (no calendar was read, no OOS period was used).
        Distinguished from `checked` on purpose: 'we looked and it was clean' and 'there was nothing to look
        at' are different claims about a result."""
        condition(cid)
        if not str(why or "").strip():
            raise ValueError(f"declaring {cid!r} not applicable requires a reason")
        if any(f["condition"] == cid for f in self._findings):
            raise ValueError(f"{cid!r} already has a finding on this run; it cannot also be inapplicable")
        self._na[cid] = why
        return self

    # ---- adapters over evidence this repo already produces
    def from_quality_flags(self, flags, *, source=None):
        """§20 data-quality faults on the history a run loaded (backtest-methods.QUALITY_FLAGS).

        The routing is the point: a timestamp fault is §38's `invalid_timestamps` and INVALIDATES, while any
        other structural fault is `corrupted_provider_data` and FLAGS. Both arrive from `assess()` as the
        single state INVALID, so without this split the harsher condition would never fire and the registry's
        distinction would be decoration.
        """
        for f in flags or ():
            where = f.get("source") or source
            what = f"{f.get('symbol')} {f.get('tf')}: {f.get('reason')}"
            state = f.get("state")
            if state in ("PARTIAL", "MISSING"):
                self.finding("unavailable_historical_data", what, source=where)
            elif state == "INVALID":
                self.finding("invalid_timestamps" if _is_timestamp_fault(f.get("reason", "")) else
                             "corrupted_provider_data", what, source=where)
            else:
                raise ValueError(f"quality state {state!r} is not a fault; §20's faults are PARTIAL, MISSING "
                                 f"and INVALID, and FRESH/STALE/UNKNOWN must not reach §38 as evidence")
        if not flags:
            self.checked("unavailable_historical_data",
                         "scripts/quality.py assessed every loaded series: no PARTIAL or MISSING history")
            self.checked("corrupted_provider_data", "scripts/quality.py assessed every loaded series: no "
                                                    "structural faults")
            self.checked("invalid_timestamps", "scripts/quality.py assessed every loaded series: no "
                                               "duplicate, backwards or unparseable bar times")
        return self

    def from_config_snapshot(self, cfg_snapshot):
        """§11's configuration snapshot names the dependencies the Trading System declares REQUIRED that this
        engine never consults (`required_evidence.declared_but_not_applied_by_this_engine`, written by
        scripts/snapshot.py for §38's benefit). Reading it here is what turns that record into a verdict."""
        snap = cfg_snapshot or {}
        req = (snap.get("fields") or snap).get("required_evidence")
        if not isinstance(req, dict) or "declared_but_not_applied_by_this_engine" not in req:
            self.finding("incomplete_required_inputs",
                         "the configuration snapshot does not say which declared dependencies this engine "
                         "applied, so completeness of the required inputs is unknown rather than clear",
                         source="scripts/snapshot.py (§11/§35)")
            return self
        missing = req["declared_but_not_applied_by_this_engine"] or []
        if missing:
            self.finding("incomplete_required_inputs",
                         "declared REQUIRED_FOR_DECISION by the governing Trading System and never consulted "
                         "by this engine: " + ", ".join(missing),
                         source="docs/architecture/trading-systems.json (§35)")
        else:
            self.checked("incomplete_required_inputs",
                         "every dependency the governing Trading System declares REQUIRED_FOR_DECISION is "
                         "applied by this engine (§11 configuration snapshot)")
        return self

    def from_leakage(self, report, *, source="scripts/leakage.py"):
        """A §37 look-ahead probe report."""
        if report is None:
            return self
        if report.get("ok"):
            self.checked("look_ahead",
                         f"leakage.probe: {report.get('checked')} decisions at or before the cut unchanged "
                         f"under {', '.join(report.get('modes') or ())}")
            return self
        for v in report.get("violations") or ():
            self.finding("look_ahead",
                         f"{v.get('key')} {v.get('field')}: {v.get('before')!r} -> {v.get('after')!r} under "
                         f"mutation '{v.get('mode')}'", source=source)
        return self

    def from_execution_assumptions(self, assumptions, *, source=None):
        """What the engine models about execution, and what it does not.

        `assumptions` maps a named cost or venue constraint to True (modelled), False (not modelled) or a
        string describing how it is modelled. Everything False becomes one finding, because the run's numbers
        are then about a venue that charges less or accepts more than the one that trades.
        """
        unmodelled = sorted(k for k, v in (assumptions or {}).items() if v is False)
        if unmodelled:
            self.finding("unrealistic_execution_assumptions",
                         "not modelled by this engine: " + ", ".join(unmodelled), source=source)
        elif assumptions:
            self.checked("unrealistic_execution_assumptions",
                         "the engine declares every execution cost and venue constraint modelled: "
                         + ", ".join(sorted(assumptions)))
        return self

    # ---- reading
    def findings(self, cid=None):
        return [f for f in self._findings if cid is None or f["condition"] == cid]

    def unchecked(self):
        """Conditions with neither a finding, a clear, nor a not-applicable. §38's blind spots on this run."""
        seen = {f["condition"] for f in self._findings} | set(self._cleared) | set(self._na)
        return tuple(c for c in ORDER if c not in seen)

    def verdict(self):
        """INVALID if any INVALIDATES condition fired; FLAGGED if only FLAGS conditions did; otherwise
        UNVERIFIED when any condition was never looked at, and VALID only when all ten were accounted for.

        Findings outrank blind spots deliberately: a defect that was actually found is what a reader needs in
        the headline, and the blind spots travel in the stamp either way.
        """
        if any(f["disposition"] == INVALIDATES for f in self._findings):
            return INVALID
        if self._findings:
            return FLAGGED
        return UNVERIFIED if self.unchecked() else VALID

    def reasons(self):
        return [f"{f['condition']}: {f['detail']}" for f in self._findings]

    def stamp(self):
        """The block a research artifact carries. Everything a later reader needs to judge the numbers next
        to it, including what was never examined."""
        return {
            "verdict": self.verdict(),
            "run": self.run,
            "findings": list(self._findings),
            "checked": dict(self._cleared),
            "not_applicable": dict(self._na),
            "unchecked": list(self.unchecked()),
            "source": "docs/architecture/research-validity.json (CLAUDE.md §38)",
        }

    def describe(self):
        v = self.verdict()
        if v == VALID:
            return "§38 VALID: all ten conditions accounted for, none fired"
        if v == UNVERIFIED:
            return (f"§38 UNVERIFIED: nothing fired, but {len(self.unchecked())} condition(s) were never "
                    f"looked at ({', '.join(self.unchecked())})")
        head = f"§38 {v}: " + "; ".join(self.reasons()[:3])
        if len(self._findings) > 3:
            head += f" (+{len(self._findings) - 3} more)"
        return head


_TIMESTAMP_FAULT = re.compile(r"not a timestamp|repeats timestamp|goes backwards in time", re.I)


def _is_timestamp_fault(reason):
    return bool(_TIMESTAMP_FAULT.search(reason or ""))


# ---- consumer side


def read(obj, *, where, key="research_validity"):
    """The §38 block of a research artifact, or `Unstamped`.

    Refusing rather than defaulting is the whole point: an artifact with no verdict is one nobody assessed,
    and treating that as VALID is the sentence §38 ends on.
    """
    block = (obj or {}).get(key)
    if not isinstance(block, dict) or block.get("verdict") not in VERDICTS:
        raise Unstamped(
            f"{where}: carries no CLAUDE.md §38 research-validity verdict. A research result without one has "
            f"not been assessed, and an unassessed result must not be read as a valid one. Re-run the "
            f"producer (it stamps via scripts/research_validity.py) before consuming this.")
    return block


def require(block, *, where, allow=(VALID, FLAGGED)):
    """Raise unless this run's verdict is one the consumer accepts."""
    v = (block or {}).get("verdict")
    if v not in VERDICTS:
        raise Unstamped(f"{where}: no §38 verdict to check")
    if v not in allow:
        reasons = "; ".join(f"{f['condition']}: {f['detail']}" for f in block.get("findings") or ()) or \
                  f"never assessed: {', '.join(block.get('unchecked') or ())}"
        raise InvalidResearch(
            f"{where}: CLAUDE.md §38 verdict is {v}; this consumer accepts {list(allow)}. {reasons}")
    return v


#: Least to most alarming. A consumer that adds a state of its own (rank-setups.py's `UNSTAMPED`, for files
#: written before verdicts existed) extends this with `extra=` rather than dropping the unknown label, which is
#: how an unassessed input ends up reported as a merely unverified one.
SEVERITY = {VALID: 0, UNVERIFIED: 1, FLAGGED: 2, INVALID: 4}


def worst(verdicts, *, extra=None):
    """The verdict of a set of runs taken together. Raises on a label it does not know.

    Silently skipping an unrecognised verdict would make `worst()` report the best thing it happened to
    understand, which is the same failure as reporting an unassessed run as a clean one.
    """
    rank = dict(SEVERITY, **(extra or {}))
    seen = list(verdicts)
    unknown = sorted({v for v in seen if v not in rank})
    if unknown:
        raise ValueError(f"worst(): unknown verdict(s) {unknown}; §38's are {list(VERDICTS)}. Pass extra={{...}} "
                         f"to rank a consumer-specific state rather than letting it disappear from the result.")
    return max(seen, key=lambda v: rank[v]) if seen else UNVERIFIED


if __name__ == "__main__":
    print(f"CLAUDE.md §38 -- {len(ORDER)} conditions\n")
    for cid in ORDER:
        c = CONDITIONS[cid]
        print(f"{cid:<36} {c['disposition']:<12} {c['detector'] or 'NO DETECTOR'}")
    print(f"\ninvalidating: {', '.join(invalidating())}")
