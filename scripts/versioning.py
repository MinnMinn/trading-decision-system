"""CLAUDE.md §46 + §47 -- THE reader for docs/architecture/versioning.json: what makes a result reproducible,
and what makes a system a different system.

Two sections, one question asked twice. §46 asks it of a RESULT; §47 asks it of the thing that produced one.
The Trading System version is an item in both lists, which is why they share a registry: version must not be
able to mean two things.

    import versioning as VER

    VER.grade(record)                  -> {"grade": "PARTIAL", "captured": [...], "missing": ["provider_state"]}
    VER.compare(a, b)                  -> refuses to compare without both grades attached
    VER.is_significant("risk")         -> True
    VER.next_candidate("v1")           -> 'v1.4'   (reads the store; a number spent on a rejected candidate stays spent)

Three properties:

1. **§46's last sentence is about COMPARISON**, which is where the harm happens. A fully reproducible result
   and a partial one placed in the same ranking table are treated as equivalent by the reader whatever the
   footnote says. `compare()` will not return a comparison without both grades in it, and
   `assert_comparable()` raises when they differ.
2. **Every listed change kind is version-significant, and none can be declared otherwise.** §47 calls its
   thirteen "examples", which is a floor, not a ceiling: an unlisted change may also be significant, so the
   API accepts an explicit override *upward* and offers none downward.
3. **A rejected candidate's number stays spent.** §47: "Rejected candidates must remain traceable."
   `next_candidate()` reads the §42 experiment store rather than a counter, so v1.3 is never reissued to a
   different candidate once something has worn it.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PATH = os.path.join(ROOT, "docs", "architecture", "versioning.json")

REPRODUCIBLE, PARTIAL, NOT_REPRODUCIBLE = "REPRODUCIBLE", "PARTIAL", "NOT_REPRODUCIBLE"


class RegistryError(ValueError):
    """The §46/§47 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something named an item or change kind the spec does not list."""


class NotEquivalent(RuntimeError):
    """Two results of different reproducibility grades were about to be compared as equals."""


class BadVersion(ValueError):
    """A version string that is not §47's canonical grammar."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rep, ver = data.get("reproducibility") or {}, data.get("versioning") or {}
    if not isinstance(rep.get("items"), list) or not rep["items"]:
        raise RegistryError(f"{path}: `reproducibility.items` must be a non-empty list")
    for it in rep["items"]:
        for f in ("id", "spec_name", "definition", "captured_by"):
            if not str(it.get(f) or "").strip():
                raise RegistryError(f"{path}: reproducibility item {it.get('id')!r} has no {f!r}")
    if set(rep.get("grades") or ()) != {REPRODUCIBLE, PARTIAL, NOT_REPRODUCIBLE}:
        raise RegistryError(f"{path}: `grades` must be exactly {REPRODUCIBLE}, {PARTIAL}, {NOT_REPRODUCIBLE}")
    kinds = ver.get("change_kinds")
    if not isinstance(kinds, list) or not kinds:
        raise RegistryError(f"{path}: `versioning.change_kinds` must be a non-empty list")
    g = ver.get("grammar") or {}
    for k in ("released", "candidate"):
        if not g.get(k):
            raise RegistryError(f"{path}: `versioning.grammar.{k}` is required -- §47's canonical form is the "
                                f"only form, and a pattern nobody declared is a form nobody validates")
    return data


_DATA = _load()
ITEMS = {i["id"]: i for i in _DATA["reproducibility"]["items"]}
ITEM_ORDER = tuple(i["id"] for i in _DATA["reproducibility"]["items"])
CHANGE_KINDS = {k["id"]: k for k in _DATA["versioning"]["change_kinds"]}
KIND_ORDER = tuple(k["id"] for k in _DATA["versioning"]["change_kinds"])
RELEASED_RE = re.compile(_DATA["versioning"]["grammar"]["released"])
CANDIDATE_RE = re.compile(_DATA["versioning"]["grammar"]["candidate"])


def item(iid):
    it = ITEMS.get(iid)
    if it is None:
        raise NotDeclared(f"no §46 item {iid!r}; the nine are {list(ITEM_ORDER)}")
    return it


def spec_name(xid):
    return (ITEMS.get(xid) or CHANGE_KINDS.get(xid) or {}).get("spec_name") or xid


# ---- §46: reproducibility


def provider_state():
    """§46's one item nothing else captures: which providers answered, in which role, and what each declared.

    A result computed while a provider was degraded is a different result, and no dataset or configuration
    snapshot would show it -- they record what was asked for, not who answered.
    """
    try:
        import providers as P
        return {"providers": {pid: {"roles": sorted(rec.get("roles") or []),
                                    "status": rec.get("status"),
                                    "venue": rec.get("venue"),
                                    "market_type": rec.get("market_type"),
                                    "capabilities": sorted(rec.get("capabilities") or [])}
                              for pid, rec in P.PROVIDERS.items()},
                "_source": "docs/architecture/providers.json (§6)"}
    except Exception as exc:                      # a capture failure is recorded, never silently omitted
        return {"unavailable": f"{type(exc).__name__}: {exc}"}


def _present(obj, iid):
    """Is this §46 item genuinely captured in `obj`?

    'Present' means a real value. A key holding `None`, an empty container, or an `unavailable()` marker is
    NOT captured -- those are the three ways a capture list gets ticked off without capturing anything.
    """
    v = obj.get(iid) if isinstance(obj, dict) else None
    if v is None:
        return False
    if isinstance(v, dict) and ("unavailable" in v or "snapshot_error" in v):
        return False
    if isinstance(v, (dict, list, str, tuple)) and len(v) == 0:
        return False
    if iid == "random_seed":
        # `null` is allowed only with an explicit statement that nothing stochastic ran; since §39 and §45
        # added bootstraps and Monte Carlo, an unexplained null is a gap rather than an exemption.
        return v is not None
    return True


def grade(obj):
    """§46's grade for one research artifact, with the missing items named.

    Named, not counted: "7 of 9 captured" tells a reader nothing about whether they can re-run it, and the two
    that are missing are the entire answer.
    """
    captured = [i for i in ITEM_ORDER if _present(obj, i)]
    missing = [i for i in ITEM_ORDER if i not in captured]
    g = REPRODUCIBLE if not missing else (NOT_REPRODUCIBLE if not captured else PARTIAL)
    return {"grade": g, "captured": captured, "missing": missing,
            "missing_names": [spec_name(m) for m in missing],
            "_source": "docs/architecture/versioning.json (CLAUDE.md §46)"}


def assert_comparable(a, b, *, where="this comparison"):
    """Raise unless two results carry the SAME reproducibility grade.

    §46: 'A result without reproducibility metadata must not be treated as equivalent to a fully reproducible
    experiment.' The harm is in the comparison, not in the record: a reader scanning a ranking table treats
    every row as equivalent whatever a footnote says.
    """
    ga, gb = grade(a)["grade"], grade(b)["grade"]
    if ga != gb:
        raise NotEquivalent(
            f"{where}: one result is {ga} and the other is {gb}. CLAUDE.md §46 forbids treating them as "
            f"equivalent. Either capture what is missing ({', '.join(grade(a if ga != REPRODUCIBLE else b)['missing_names'])}) "
            f"or present them apart, labelled.")
    return ga


def compare(a, b, *, metric, where="comparison"):
    """A comparison that carries both grades, or no comparison at all.

    Deliberately returns the grades INSIDE the result rather than beside it: a caller that wants to render
    only the numbers has to delete them on purpose.
    """
    ga, gb = grade(a), grade(b)
    va, vb = a.get(metric), b.get(metric)
    return {"metric": metric, "a": va, "b": vb,
            "a_reproducibility": ga["grade"], "b_reproducibility": gb["grade"],
            "comparable": ga["grade"] == gb["grade"],
            "_warning": None if ga["grade"] == gb["grade"] else
                        (f"NOT EQUIVALENT (§46): {ga['grade']} vs {gb['grade']}; missing from the weaker "
                         f"result: {', '.join((ga if ga['grade'] != REPRODUCIBLE else gb)['missing_names'])}"),
            "_source": "docs/architecture/versioning.json (CLAUDE.md §46)"}


# ---- §47: versioning


def is_released(v):
    return bool(RELEASED_RE.match(str(v or "")))


def is_candidate(v):
    return bool(CANDIDATE_RE.match(str(v or "")))


def parse(v):
    """('v1', None) for a release, ('v1', 3) for candidate v1.3. Raises on anything else.

    There is no third form on purpose: §47 forbids a separate incompatible version system, and a grammar that
    accepts 'v2-experimental' is how one starts.
    """
    s = str(v or "")
    if is_released(s):
        return s, None
    if is_candidate(s):
        parent, n = s.split(".")
        return parent, int(n)
    raise BadVersion(
        f"{v!r} is not CLAUDE.md §47's canonical versioning. A released system is v1, v2, v3 ...; a candidate "
        f"is v<parent>.<n> (§47: 'Trading System v1 -> Candidate v1.x -> Approved Trading System v2'). "
        f"§47 also forbids a separate incompatible version system, so there is no third form.")


def parent_of(v):
    return parse(v)[0]


def is_significant(kind=None, *, also_significant=False):
    """Is a change version-significant?

    Every one of §47's thirteen kinds is. `also_significant=True` lets a caller declare an UNLISTED change
    significant -- §47's list is examples, which is a floor. There is deliberately no way to declare a listed
    kind insignificant: that is the direction in which a version silently stops tracking the system.
    """
    if also_significant:
        return True
    if kind is None:
        return False
    if kind in CHANGE_KINDS:
        return True
    raise NotDeclared(
        f"{kind!r} is not one of §47's thirteen change kinds ({list(KIND_ORDER)}). If this change IS "
        f"significant, say so with also_significant=True -- §47's list is a floor, not a ceiling.")


def next_candidate(parent, *, records=None):
    """The next unused candidate number under `parent`, read from the §42 experiment store.

    §47: 'Rejected candidates must remain traceable.' A counter would hand v1.3 to a new candidate once the
    old v1.3 was rejected and forgotten. Reading the store means a number that has been worn stays worn --
    including by candidates that were rejected, which is precisely the traceability §47 asks for.
    """
    if not is_released(parent):
        raise BadVersion(f"a candidate's parent must be a released version (v1, v2 ...); got {parent!r}")
    if records is None:
        import experiment as X
        records = X.all_records()
    used = set()
    for r in records:
        for v in (r.get("candidate_version"), r.get("parent_trading_system_version")):
            try:
                p, n = parse(v)
            except BadVersion:
                continue
            if n is not None and p == parent:
                used.add(n)
    n = 1
    while n in used:
        n += 1
    return f"{parent}.{n}"


def approved_successor(candidate):
    """The released version a candidate becomes if approved: v1.4 -> v2 (§47's own example)."""
    parent, n = parse(candidate)
    if n is None:
        raise BadVersion(f"{candidate!r} is already a released version")
    return f"v{int(parent[1:]) + 1}"


def describe(obj):
    g = grade(obj)
    line = f"§46 {g['grade']}"
    if g["missing"]:
        line += f" -- missing: {', '.join(g['missing_names'])}"
    return line


if __name__ == "__main__":
    print(f"CLAUDE.md §46 -- {len(ITEM_ORDER)} reproducibility items")
    for iid in ITEM_ORDER:
        print(f"  {spec_name(iid):<28} {ITEMS[iid]['captured_by']}")
    print(f"\nCLAUDE.md §47 -- {len(KIND_ORDER)} version-significant change kinds")
    for kid in KIND_ORDER:
        print(f"  {spec_name(kid)}")
    import experiment as X
    recs = X.all_records()
    print(f"\nexperiment store: {len(recs)} record(s); next candidate under v1 = {next_candidate('v1', records=recs)}")
