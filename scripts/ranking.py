"""CLAUDE.md §48 + §49 -- THE reader for docs/architecture/ranking.json: how systems are ordered, and how two
configurations of one system are compared.

§48's rule and §49's rule are the same rule pointed at different things:

    §48: "Do not create a universal 'best system' score."
    §49: "Do not assume the filter improves performance."

Both forbid a conclusion from being baked into the machinery that is supposed to reach it. §48's version is a
weighted blend whose weights ARE the objective while looking like arithmetic; §49's is an A/B that can only
come out one way because the arms were not actually identical.

    import ranking as R

    R.rank(rows, objective="survival")     # lexicographic, and it says which key decided each row
    R.ab(arm_a, arm_b)                     # refuses if the arms differ on anything §49 says to hold identical

Three properties:

1. **Every objective is lexicographic over named keys in a declared order.** There is no weighting parameter
   in this module and there is not meant to be one. `rank()` returns the deciding key per row, so "why is this
   first" is answerable.
2. **Exposure is not optional and is not satisfied by dropping a row.** A row that cannot supply one of §48's
   seven exposures is ranked and MARKED. Dropping it hides a system; ranking it silently hides that the
   comparison is uneven.
3. **An A/B refuses rather than caveats.** The six things §49 says to hold identical are the experiment. An
   A/B whose arms differ elsewhere measures that other thing, and a caveat on a two-column table is not read.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import performance as P

PATH = os.path.join(ROOT, "docs", "architecture", "ranking.json")

MAX, MIN = "max", "min"


class RegistryError(ValueError):
    """The §48/§49 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something named an objective or comparison dimension the spec does not list."""


class ArmsDiffer(RuntimeError):
    """An A/B was asked to compare arms that differ in something §49 says to hold identical."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rk, ab_ = data.get("ranking") or {}, data.get("news_ab") or {}
    objs = rk.get("objectives")
    if not isinstance(objs, list) or not objs:
        raise RegistryError(f"{path}: `ranking.objectives` must be a non-empty list")
    for o in objs:
        for f in ("id", "spec_name", "definition"):
            if not str(o.get(f) or "").strip():
                raise RegistryError(f"{path}: objective {o.get('id')!r} has no {f!r}")
        if len(o.get("keys") or ()) != len(o.get("direction") or ()):
            raise RegistryError(f"{path}: objective {o['id']!r} has {len(o.get('keys') or ())} keys and "
                                f"{len(o.get('direction') or ())} directions; every key needs one")
        for d in o.get("direction") or ():
            if d not in (MAX, MIN):
                raise RegistryError(f"{path}: objective {o['id']!r} has direction {d!r}; use {MAX!r}/{MIN!r}")
        if any(k in str(o) for k in ("weight", "score =")):
            raise RegistryError(
                f"{path}: objective {o['id']!r} looks like a weighted blend. CLAUDE.md §48: 'Do not create a "
                f"universal best system score.' A blend hides which criterion decided and its weights become "
                f"the real objective while looking like arithmetic.")
    for key in ("always_expose",):
        if not isinstance(rk.get(key), list) or not rk[key]:
            raise RegistryError(f"{path}: `ranking.{key}` must be a non-empty list")
    for key in ("compare", "identical", "arms"):
        if not isinstance(ab_.get(key), list) or not ab_[key]:
            raise RegistryError(f"{path}: `news_ab.{key}` must be a non-empty list")
    return data


_DATA = _load()
OBJECTIVES = {o["id"]: o for o in _DATA["ranking"]["objectives"]}
OBJECTIVE_ORDER = tuple(o["id"] for o in _DATA["ranking"]["objectives"])
EXPOSURES = tuple(e["id"] for e in _DATA["ranking"]["always_expose"])
EXPOSURE_NAMES = {e["id"]: e["spec_name"] for e in _DATA["ranking"]["always_expose"]}
AB_COMPARE = tuple(c["id"] for c in _DATA["news_ab"]["compare"])
AB_IDENTICAL = tuple(i["id"] for i in _DATA["news_ab"]["identical"])


def objective(oid):
    o = OBJECTIVES.get(oid)
    if o is None:
        raise NotDeclared(f"no §48 objective {oid!r}; the seven are {list(OBJECTIVE_ORDER)}")
    return o


def spec_name(xid):
    return (OBJECTIVES.get(xid) or {}).get("spec_name") or EXPOSURE_NAMES.get(xid) or xid


def _num(row, key):
    """A comparable number for one metric, or None.

    Unwraps §39's shapes -- a bare float, `{"value": ...}`, `{"fraction": ...}` -- and refuses an
    `unavailable()` marker, which must never sort as a number.
    """
    v = row.get(key)
    if key == "not_ruined":
        return 1.0 if not row.get("ruin") else 0.0
    if P.is_unavailable(v):
        return None
    if isinstance(v, dict):
        for k in ("value", "fraction", "mean"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
        return None
    return float(v) if isinstance(v, (int, float)) else None


def exposure_gaps(row):
    """Which of §48's seven exposures this row cannot supply."""
    return [e for e in EXPOSURES if not row.get(e)]


def rank(rows, *, objective_id="expectancy", custom_keys=None, custom_direction=None):
    """Order rows lexicographically under a declared objective.

    Returns every row -- ranked and annotated, never filtered. A row missing an exposure is MARKED rather than
    dropped: dropping it hides a system, and ranking it silently hides that the comparison is uneven.

    The result names the deciding key per row, so "why is this first" has an answer that is not "the score".
    """
    o = objective(objective_id)
    keys = list(custom_keys or o["keys"])
    dirs = list(custom_direction or o["direction"])
    if objective_id == "custom" and not keys:
        raise NotDeclared("a custom objective must declare its keys and directions -- §48 requires objectives "
                          "to be configurable, and an undeclared one is not configurable, it is hidden")
    if len(keys) != len(dirs):
        raise ValueError(f"{len(keys)} keys and {len(dirs)} directions")

    def sort_key(r):
        out = []
        for k, d in zip(keys, dirs):
            v = _num(r, k)
            # A row that cannot supply a key sorts LAST on it, whichever direction the key runs -- an
            # unmeasurable system must never win a comparison by being unmeasured.
            out.append((v is not None, (v if d == MAX else -v) if v is not None else 0.0))
        return tuple(out)

    ordered = sorted(rows, key=sort_key, reverse=True)
    out = []
    for i, r in enumerate(ordered):
        decided = None
        if i + 1 < len(ordered):
            for k, d in zip(keys, dirs):
                a, b = _num(r, k), _num(ordered[i + 1], k)
                if a != b:
                    decided = k
                    break
        gaps = exposure_gaps(r)
        out.append({"rank": i + 1, "row": r, "decided_by": decided,
                    "missing_exposures": gaps,
                    "missing_exposure_names": [EXPOSURE_NAMES[g] for g in gaps],
                    "unmeasurable_keys": [k for k in keys if _num(r, k) is None]})
    return {"objective": objective_id, "objective_name": o["spec_name"],
            "keys": keys, "direction": dirs, "ranked": out,
            "_no_universal_score": "lexicographic over the named keys above, in that order; there is no "
                                   "weighting and no blended score (CLAUDE.md §48)",
            "_source": "docs/architecture/ranking.json (CLAUDE.md §48)"}


def exposure_report(rows):
    """§48: 'Always expose: ...'. Which rows can, which cannot, and what is missing from each."""
    return {e: {"supplied": sum(1 for r in rows if r.get(e)), "of": len(rows),
                "missing_from": [r.get("id", i) for i, r in enumerate(rows) if not r.get(e)]}
            for e in EXPOSURES}


# ---- §49


def _arm_context(arm):
    return {k: arm.get(k) for k in AB_IDENTICAL}


def assert_identical(a, b):
    """Raise unless the two arms agree on everything §49 says to hold identical.

    Refusing rather than caveating: the six items ARE the experiment, an A/B whose arms differ elsewhere
    measures that other thing, and a caveat on a two-column table is not read.
    """
    ca, cb = _arm_context(a), _arm_context(b)
    differ = [k for k in AB_IDENTICAL if ca.get(k) != cb.get(k)]
    if differ:
        raise ArmsDiffer(
            f"the A/B arms differ on {', '.join(differ)}. CLAUDE.md §49 requires identical "
            f"{', '.join(_DATA['news_ab']['identical'][i]['spec_name'] for i, k in enumerate(AB_IDENTICAL) if k in differ)}"
            f" -- an A/B whose arms differ elsewhere measures that other thing, not the news filter.")
    missing = [k for k in AB_IDENTICAL if ca.get(k) is None]
    return {"identical": ca, "undeclared": missing}


def ab(arm_a, arm_b):
    """§49's controlled comparison. Reports every dimension and judges none of them.

    §49 says the filter must not be ASSUMED to improve performance, which means the comparison has to be able
    to conclude that it does not -- so opportunity loss and missed opportunities are reported beside
    expectancy and drawdown, and each difference carries its direction without a verdict attached.
    """
    ctx = assert_identical(arm_a, arm_b)
    rows = {}
    for dim in AB_COMPARE:
        va, vb = _num(arm_a, dim), _num(arm_b, dim)
        rows[dim] = {"A_filter_on": arm_a.get(dim), "B_filter_off": arm_b.get(dim),
                     "delta": (va - vb) if (va is not None and vb is not None) else None,
                     "comparable": va is not None and vb is not None}
    incomparable = [d for d, r in rows.items() if not r["comparable"]]
    return {"arms": {"A": _DATA["news_ab"]["arms"][0]["spec_name"],
                     "B": _DATA["news_ab"]["arms"][1]["spec_name"]},
            "held_identical": ctx["identical"], "undeclared_context": ctx["undeclared"],
            "dimensions": rows, "incomparable_dimensions": incomparable,
            "_verdict": None,
            "_note": "CLAUDE.md §49: 'Do not assume the filter improves performance.' This comparison states "
                     "each difference and its direction; it does not conclude. Opportunity loss and missed "
                     "opportunities are the filter's COST and are reported beside its benefit.",
            "_source": "docs/architecture/ranking.json (CLAUDE.md §49)"}


def describe(res):
    lines = [f"§48 ranked by {res['objective_name']} ({' > '.join(res['keys'])})"]
    for r in res["ranked"]:
        row = r["row"]
        extra = ""
        if r["missing_exposures"]:
            extra = f"  [missing: {', '.join(r['missing_exposure_names'])}]"
        lines.append(f"  {r['rank']}. {row.get('id', '?')}"
                     f"  decided by {r['decided_by'] or '(last)'}{extra}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(f"CLAUDE.md §48 -- {len(OBJECTIVE_ORDER)} configurable objectives")
    for oid in OBJECTIVE_ORDER:
        o = OBJECTIVES[oid]
        print(f"  {o['spec_name']:<24} {' > '.join(o['keys']) or '(caller-supplied)'}")
    print(f"\nalways expose: {', '.join(EXPOSURE_NAMES[e] for e in EXPOSURES)}")
    print(f"\nCLAUDE.md §49 -- compare {len(AB_COMPARE)} dimensions, hold {len(AB_IDENTICAL)} identical")
    print(f"  compare:   {', '.join(AB_COMPARE)}")
    print(f"  identical: {', '.join(AB_IDENTICAL)}")
