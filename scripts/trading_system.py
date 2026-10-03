"""CLAUDE.md §35 -- THE reader for docs/architecture/trading-systems.json.

A Trading System is the executable specification of trading behaviour: market + instrument + market type +
session + methodology + setup + entry + exit + risk + account profile + custom constraints + event risk +
required data. Most of those already have their own registry in this repo, so this module RESOLVES them
(`describe`) rather than holding a second copy. What lives here and nowhere else is the part §35 calls
mandatory and §62 calls non-negotiable: the four-way dependency classification.

    import trading_system as TS

    TS.role_of("scalping", "event_risk.calendar")        -> 'REQUIRED_FOR_DECISION'
    TS.role_of("cfd-swing", "methodology.footprint")     -> 'OPTIONAL_FOR_ANALYSIS'   (no source on cfd)
    TS.required("scalping", setup=row)                   -> the ids that may gate THIS setup's entry
    TS.assert_may_gate("scalping", "display.chart", ...) -> raises NotGating

Three rules are enforced in code, not in prose:

1. **Required-ness cannot be inherited.** A dependency's `baseline_role` -- the role it has in a system that
   does not name it -- may never be REQUIRED_FOR_DECISION. Loading refuses a registry where it is. So a
   dependency gates only a system that wrote its id down.
2. **Unknown context resolves REQUIRED, never optional.** A conditional role (`only_when`) whose predicate
   cannot be evaluated for lack of a setup row / engaged-dimension set resolves REQUIRED_FOR_DECISION. "I was
   not told" must never read as "not required" -- that is the exact silent downgrade §36 forbids.
3. **Only REQUIRED_FOR_DECISION may gate.** `assert_may_gate` raises on the other three roles, which is §62's
   invariant with an inverse that is also enforced: an optional analysis can never quietly become a gate.

There is deliberately no runtime setter. `reclassify()` exists only to raise and say where the change belongs.
"""
import hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import methods as M
import account_profile as AP
import sessions as S
import quality as Q
import trader_constraints as TC

PATH = os.path.join(ROOT, "docs", "architecture", "trading-systems.json")
PILOT_PATH = os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")

REQUIRED = "REQUIRED_FOR_DECISION"
OPTIONAL = "OPTIONAL_FOR_ANALYSIS"
VISUALIZATION = "VISUALIZATION_ONLY"
RESEARCH = "RESEARCH_ONLY"
# Order is CLAUDE.md §35's own. The registry must repeat it exactly; loading checks that, so a reordering or
# a renaming here would have to be a deliberate edit in two places rather than a drift in one.
ROLES = (REQUIRED, OPTIONAL, VISUALIZATION, RESEARCH)
NON_GATING = (OPTIONAL, VISUALIZATION, RESEARCH)

_VERSION_RE = re.compile(r"^v[1-9][0-9]*$")


BOOK_STATUSES = ("DRAFT", "APPROVED", "RETIRED")
BOOK_THROTTLES = ("none", "dd3")
BOOK_SIZING = ("initial_balance",)
BOOK_EXECUTION_KEYS = ("max_bar_age_minutes", "close_before_rollover_minutes", "tp_stop_multiple")
#: Plausible values of a component's numeric params, checked when the registry loads (so a bad version is refused at import /
#: switch time, never at an executor tick). stop_k = the H7 / G9 protective stop in sigma_5m x sqrt(bars to the rollover).
BOOK_PARAM_RANGES = {"stop_k": (0.5, 4.0)}
# The fields of a book version that DECIDE trades. Everything else on the version (status, approval, the digest
# itself, `_why` notes) is metadata and may change without a new version.
BOOK_CONTENT_KEYS = ("dependency_profile", "components", "risk", "execution")


class RegistryError(ValueError):
    """The registry itself is wrong -- raised at import, never at decision time."""


class NotDeclared(KeyError):
    """Asked for the role of a dependency no system has classified. §35 calls the classification mandatory,
    so an unclassified dependency is a spec violation and not a silently optional one."""


class NotGating(RuntimeError):
    """A caller tried to block an entry on a dependency whose declared role forbids it (§35, §62)."""


# --------------------------------------------------------------------------- predicates
# Each answers True / False / None. None means "this cannot be decided from what the caller supplied", and
# every caller of a predicate treats None as REQUIRED. Implemented here rather than in the registry because a
# predicate is behaviour; the registry names which one applies and the reader owns what it means.

def _p_setup_htf(dep, system, ctx):
    setup = ctx.get("setup")
    return None if setup is None else bool(setup.get("htf"))


def _p_setup_method_requires(dep, system, ctx):
    setup = ctx.get("setup")
    if setup is None:
        return None
    method = setup.get("method")
    spec = M.RUNNER_METHODS.get(method)
    if spec is None:
        # An unknown method is not a reason to relax: it is a reason to require. Returning None rather than
        # False keeps the fail-closed path in one place.
        return None
    return dep["dimension"] in spec["requires"]


def _p_preset_engages(dep, system, ctx):
    dim = dep["dimension"]
    # Structural impossibility is knowable from the system alone and needs no config: cfd has no
    # CoinGlass source, so footprint/heatmap can never be engaged there (methods.json dimensions.*.markets).
    # Answering False here is what stops a dimension that cannot exist on a market from gating it forever.
    if system["market"] not in M.DIMENSIONS[dim]["markets"]:
        return False
    engaged = ctx.get("engaged")
    if engaged is None and ctx.get("instrument"):
        engaged = M.dispatch_plan(ctx["instrument"])["engaged"]
    return None if engaged is None else dim in set(engaged)


PREDICATES = {
    "setup.htf": (_p_setup_htf, False),
    "setup.method_requires": (_p_setup_method_requires, True),   # needs `dimension`
    "preset.engages": (_p_preset_engages, True),
}


# --------------------------------------------------------------------------- load + validate
def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return _validate(data, path)


def _validate(data, path):
    if tuple(data.get("roles") or ()) != ROLES:
        raise RegistryError(f"{path}: `roles` must be CLAUDE.md §35's four names in its order {list(ROLES)}; "
                            f"got {data.get('roles')}")
    if data.get("gating_role") != REQUIRED:
        raise RegistryError(f"{path}: `gating_role` must be {REQUIRED!r} -- §35 says only that classification "
                            f"determines whether a dependency may gate a live decision")

    deps = data.get("dependencies")
    if not isinstance(deps, dict) or not deps:
        raise RegistryError(f"{path}: `dependencies` must be a non-empty object")
    for dep_id, dep in deps.items():
        for field in ("kind", "produced_by", "baseline_role", "why"):
            if not str(dep.get(field) or "").strip():
                raise RegistryError(f"{path}: dependency {dep_id!r} has no {field!r}")
        if dep["baseline_role"] not in ROLES:
            raise RegistryError(f"{path}: dependency {dep_id!r} baseline_role {dep['baseline_role']!r} is not "
                                f"one of {list(ROLES)}")
        if dep["baseline_role"] == REQUIRED:
            raise RegistryError(
                f"{path}: dependency {dep_id!r} declares baseline_role {REQUIRED} -- forbidden. The baseline "
                f"is the role in a system that did NOT name this dependency, so allowing it here would let a "
                f"dependency gate a system by inheritance, which is how a required input appears in a system "
                f"nobody reviewed (CLAUDE.md §35, §62).")
        if "only_when" in dep:
            pred = dep["only_when"]
            if pred not in PREDICATES:
                raise RegistryError(f"{path}: dependency {dep_id!r} names unknown predicate {pred!r}; "
                                    f"implemented predicates are {sorted(PREDICATES)}")
            if dep.get("else_role") not in ROLES:
                raise RegistryError(f"{path}: dependency {dep_id!r} is conditional and must declare an "
                                    f"`else_role` from {list(ROLES)}")
            if dep["else_role"] == REQUIRED:
                raise RegistryError(f"{path}: dependency {dep_id!r} else_role may not be {REQUIRED} -- a "
                                    f"condition that changes nothing is a condition that hides something")
            if PREDICATES[pred][1]:
                dim = dep.get("dimension")
                if dim not in M.DIMENSIONS:
                    raise RegistryError(f"{path}: dependency {dep_id!r} uses predicate {pred!r}, which needs a "
                                        f"`dimension` from methods.json; got {dim!r}")
        elif "else_role" in dep:
            raise RegistryError(f"{path}: dependency {dep_id!r} declares `else_role` with no `only_when`")

    profiles = data.get("dependency_profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise RegistryError(f"{path}: `dependency_profiles` must be a non-empty object")
    for pid, prof in profiles.items():
        req = prof.get("required_for_decision")
        if not isinstance(req, list) or not req:
            raise RegistryError(f"{path}: profile {pid!r} has no `required_for_decision` list")
        if len(set(req)) != len(req):
            raise RegistryError(f"{path}: profile {pid!r} lists a dependency twice")
        unknown = [d for d in req if d not in deps]
        if unknown:
            raise RegistryError(f"{path}: profile {pid!r} requires undeclared dependencies {unknown}")
        if not str(prof.get("why") or "").strip():
            raise RegistryError(f"{path}: profile {pid!r} has no `why`")

    systems = data.get("systems")
    if not isinstance(systems, dict) or not systems:
        raise RegistryError(f"{path}: `systems` must be a non-empty object")
    # The style set is automation.py's, derived from (market x horizon). Importing it lazily keeps this module
    # importable from automation.py's own test harness without a cycle.
    import automation as A
    expected = set(A.STYLE.values())
    if set(systems) != expected:
        missing, extra = sorted(expected - set(systems)), sorted(set(systems) - expected)
        raise RegistryError(
            f"{path}: `systems` must have exactly one entry per style in scripts/automation.py STYLE "
            f"(market x horizon). missing={missing} unexpected={extra}. A style with no Trading System would "
            f"be a page and a scan with nothing declaring what may gate it; a Trading System with no style "
            f"would govern nothing.")
    for sid, sysd in systems.items():
        if not _VERSION_RE.match(str(sysd.get("version") or "")):
            raise RegistryError(f"{path}: system {sid!r} version {sysd.get('version')!r} is not vN (§47)")
        if sysd.get("dependency_profile") not in profiles:
            raise RegistryError(f"{path}: system {sid!r} names unknown dependency_profile "
                                f"{sysd.get('dependency_profile')!r}")
        ap = sysd.get("account_profile") or {}
        if not ap.get("venue") or not ap.get("environment"):
            raise RegistryError(f"{path}: system {sid!r} must declare account_profile.venue and .environment")
        # Resolve it now, at load, so a system pointing at an account that does not exist fails here rather
        # than on the first tick that tries to size a trade under it.
        AP.for_venue(ap["venue"], ap["environment"])
        market, tf = A.STYLE_MARKET_TF[sid]
        sysd["market"], sysd["timeframe"], sysd["id"] = market, tf, sid
        sysd["horizon"] = A.TF_HORIZON[tf]
    _validate_books(data.get("books") or {}, profiles, path)
    return data


def book_digest(version):
    """sha256 of a book version's decision content (BOOK_CONTENT_KEYS), canonical JSON. An APPROVED or RETIRED
    version must carry this as `content_sha256`: editing an approved version in place changes the digest and
    the registry refuses to load (CLAUDE.md §47 -- a meaningful change is a new version, never an edit)."""
    blob = json.dumps({k: version.get(k) for k in BOOK_CONTENT_KEYS}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_books(books, profiles, path):
    import trading_env
    for bid, book in books.items():
        if book.get("market") not in I.MARKETS:
            raise RegistryError(f"{path}: book {bid!r} market {book.get('market')!r} is not one of {list(I.MARKETS)}")
        versions = book.get("versions")
        if not isinstance(versions, dict) or not versions:
            raise RegistryError(f"{path}: book {bid!r} has no versions")
        for ver, v in versions.items():
            where = f"{path}: book {bid!r} {ver}"
            if not _VERSION_RE.match(ver):
                raise RegistryError(f"{where}: version is not vN (§47)")
            if v.get("status") not in BOOK_STATUSES:
                raise RegistryError(f"{where}: status {v.get('status')!r} is not one of {list(BOOK_STATUSES)}")
            if v.get("dependency_profile") not in profiles:
                raise RegistryError(f"{where}: unknown dependency_profile {v.get('dependency_profile')!r}")
            comps = v.get("components")
            if not isinstance(comps, list) or not comps:
                raise RegistryError(f"{where}: no components")
            seen = set()
            for c in comps:
                if not c.get("setup") or not c.get("instrument") or not isinstance(c.get("params"), dict):
                    raise RegistryError(f"{where}: a component needs setup, instrument and params: {c}")
                for pk, (lo, hi) in BOOK_PARAM_RANGES.items():
                    pv = c["params"].get(pk)
                    if pk in c["params"] and (isinstance(pv, bool) or not isinstance(pv, (int, float)) or not lo <= pv <= hi):
                        raise RegistryError(f"{where}: component {c['setup']}/{c['instrument']} {pk} {pv!r} is outside [{lo}, {hi}]")
                key = (c["setup"], c["instrument"])
                if key in seen:
                    raise RegistryError(f"{where}: component {key} is listed twice")
                seen.add(key)
            risk = v.get("risk") or {}
            pct = risk.get("risk_pct")
            if not isinstance(pct, (int, float)) or not 0 < pct <= float(trading_env.MAX_RISK_PCT):
                raise RegistryError(f"{where}: risk_pct {pct!r} must be in (0, max_risk_pct "
                                    f"{trading_env.MAX_RISK_PCT}] (docs/architecture/risk-config.json)")
            if risk.get("throttle") not in BOOK_THROTTLES:
                raise RegistryError(f"{where}: throttle {risk.get('throttle')!r} is not one of {list(BOOK_THROTTLES)}")
            if risk.get("sizing_basis") not in BOOK_SIZING:
                raise RegistryError(f"{where}: sizing_basis {risk.get('sizing_basis')!r} is not one of {list(BOOK_SIZING)}")
            ex = v.get("execution") or {}
            missing = [k for k in BOOK_EXECUTION_KEYS if not isinstance(ex.get(k), (int, float))]
            if missing:
                raise RegistryError(f"{where}: execution lacks {missing}")
            if v["status"] != "DRAFT" and v.get("content_sha256") != book_digest(v):
                raise RegistryError(
                    f"{where}: content_sha256 does not match the version's content ({book_digest(v)}). An "
                    f"{v['status']} version is immutable (CLAUDE.md §47): add a new version instead of editing it.")
            v["id"], v["book"], v["version"], v["market"] = f"{bid}@{ver}", bid, ver, book["market"]


_DATA = _load()
DEPENDENCIES = _DATA["dependencies"]
PROFILES = _DATA["dependency_profiles"]
SYSTEMS = _DATA["systems"]
BOOKS = _DATA.get("books") or {}


def book(book_id, version):
    """One version of a book Trading System (validated at import), or KeyError naming what exists."""
    if book_id not in BOOKS:
        raise KeyError(f"no book Trading System {book_id!r}; declared books are {sorted(BOOKS)}")
    versions = BOOKS[book_id]["versions"]
    if version not in versions:
        raise KeyError(f"book {book_id!r} has no version {version!r}; declared: {sorted(versions)}")
    return versions[version]


def market_of(system_id, version):
    """The market a Trading System version trades -- a style system's from automation.STYLE, a book's from
    its own declaration. KeyError for an unknown system or version."""
    if system_id in SYSTEMS:
        if SYSTEMS[system_id]["version"] != version:
            raise KeyError(f"system {system_id!r} is at {SYSTEMS[system_id]['version']}, not {version!r}")
        return SYSTEMS[system_id]["market"]
    return book(system_id, version)["market"]


# --------------------------------------------------------------------------- lookup
def styles():
    """Every Trading System id, in registry order."""
    return tuple(SYSTEMS)


def get(style):
    sysd = SYSTEMS.get(style)
    if sysd is None:
        raise KeyError(f"no Trading System {style!r}; declared systems are {list(SYSTEMS)}")
    return sysd


def for_market_tf(market, timeframe):
    """The Trading System governing this (market, timeframe), or KeyError. The pair IS the style.

    The timeframe is matched case-insensitively ON PURPOSE. This repo carries two timeframe spellings that
    are not going to be unified here: the scanner/automation side writes `1h`/`4h` (automation.STYLE,
    SCAN_WINDOW) and the backtest/pilot side writes `1H`/`4H` (backtest-methods.py `P`, and therefore the
    `tf` field of every row in pilot-selection.json). A Trading System that could not be found because a caller
    came from the other half of the repo would mean the pilot's own setups had no system governing them --
    which is exactly what happened the first time this function was wired in. Folding the case here resolves
    the lookup without pretending the two vocabularies are one; prefer `for_setup()` where a row is in hand,
    since a row declares its `horizon` and that word has only one spelling.
    """
    import automation as A
    want = str(timeframe).lower()
    for (m, tf), style in A.STYLE.items():
        if m == market and tf.lower() == want:
            return get(style)
    raise KeyError(f"no Trading System for market={market!r} timeframe={timeframe!r}")


def for_setup(row):
    """The Trading System governing a pilot-selection.json setup row, by its declared (market, horizon)."""
    import automation as A
    market, horizon = row.get("market"), row.get("horizon")
    if market in A.STYLE_PREFIX and horizon in A.HORIZON_TF:
        return get(A.STYLE_PREFIX[market] + horizon)
    return for_market_tf(market, row.get("tf"))


def dependency(dep_id):
    dep = DEPENDENCIES.get(dep_id)
    if dep is None:
        raise NotDeclared(
            f"{dep_id!r} is not a classified dependency. CLAUDE.md §35 makes the classification mandatory, so "
            f"an unclassified input may not be consulted by a decision: declare it in "
            f"docs/architecture/trading-systems.json `dependencies` first. Declared: {sorted(DEPENDENCIES)}")
    return dep


def declared_required(style):
    """The ids this system's profile names -- BEFORE any condition is applied. This is the reviewable list."""
    return tuple(PROFILES[get(style)["dependency_profile"]]["required_for_decision"])


# --------------------------------------------------------------------------- the classification
def role_of(style, dep_id, *, setup=None, engaged=None, instrument=None):
    """This system's declared role for this dependency, refined by whatever context the caller supplied.

    `setup`      a row from docs/architecture/pilot-selection.json (its `htf` / `method` fields are conditions)
    `engaged`    the dimensions the active preset engages (methods.dispatch_plan(...)["engaged"])
    `instrument` a symbol, from which `engaged` is resolved when not given directly

    Missing context never relaxes a role: a condition that cannot be evaluated resolves REQUIRED_FOR_DECISION.
    """
    sysd = get(style)
    dep = dependency(dep_id)
    if dep_id not in declared_required(style):
        return dep["baseline_role"]
    if "only_when" not in dep:
        return REQUIRED
    predicate = PREDICATES[dep["only_when"]][0]
    answer = predicate(dep, sysd, {"setup": setup, "engaged": engaged, "instrument": instrument})
    if answer is None:
        return REQUIRED     # fail closed -- see the module docstring, rule 2
    return REQUIRED if answer else dep["else_role"]


def required(style, *, setup=None, engaged=None, instrument=None):
    """The dependencies that may gate THIS decision, in registry order."""
    return tuple(d for d in DEPENDENCIES
                 if role_of(style, d, setup=setup, engaged=engaged, instrument=instrument) == REQUIRED)


def classification(style, **ctx):
    """dependency id -> role, for every declared dependency. The whole §35 table for one system."""
    return {d: role_of(style, d, **ctx) for d in DEPENDENCIES}


def may_gate(style, dep_id, **ctx):
    return role_of(style, dep_id, **ctx) == REQUIRED


def assert_may_gate(style, dep_id, **ctx):
    """Raise unless this dependency is allowed to block an entry in this system.

    Call this at the site that BLOCKS, not at the site that reads. CLAUDE.md §62: only REQUIRED_FOR_DECISION
    inputs can gate entry; OPTIONAL_FOR_ANALYSIS, VISUALIZATION_ONLY and RESEARCH_ONLY must not block
    execution. A gate on one of those is a defect the moment it is written, and this turns it into an
    exception instead of a quietly missed trade.
    """
    role = role_of(style, dep_id, **ctx)
    if role != REQUIRED:
        raise NotGating(
            f"{style}: refusing to block an entry on {dep_id!r} -- its role here is {role}, and CLAUDE.md §62 "
            f"says only {REQUIRED} inputs may gate entry. If this dependency really must gate this system, "
            f"that is a registry change (docs/architecture/trading-systems.json) plus a §47 version bump, not "
            f"a branch in the decision path.")
    return role


def gate(style, states, *, setup=None, engaged=None, instrument=None, allow=Q.USABLE, action=None):
    """§20 quality gating over exactly this system's REQUIRED_FOR_DECISION set.

    `states` maps dependency id -> §20 quality state. Returns (decision, reasons) from quality.gate; a
    required dependency absent from `states` is MISSING there, which is the fail-closed answer.
    """
    req = required(style, setup=setup, engaged=engaged, instrument=instrument)
    return Q.gate(states, required=req, allow=allow, action=action)


def reclassify(*_a, **_kw):
    """Always raises. There is no runtime reclassification, by design."""
    raise NotGating(
        "a dependency's role may not be changed at runtime. CLAUDE.md §36: 'Never silently downgrade "
        "REQUIRED_FOR_DECISION -> OPTIONAL_FOR_ANALYSIS to improve latency.' Change "
        "docs/architecture/trading-systems.json, bump the system's §47 version, and let the configuration "
        "snapshot record which version produced which result.")


# --------------------------------------------------------------------------- composition (§35's checklist)
def setups(style):
    """The pilot setup rows this system owns: same market, same horizon. Read from pilot-selection.json, not
    copied into the registry -- a setup row is the entry condition, the Trading System is what surrounds it
    (SYSTEM-DESIGN.md §17.1)."""
    sysd = get(style)
    with open(PILOT_PATH, encoding="utf-8") as fh:
        rows = json.load(fh)["setups"]
    return [r for r in rows if r.get("market") == sysd["market"] and r.get("horizon") == sysd["horizon"]]


def execution_venues(style):
    """The venues this system actually routes to today -- derived from its setup rows, so a system with no
    row reports () rather than claiming an execution path it does not have."""
    return tuple(sorted({r["execution"] for r in setups(style) if r.get("execution")}))


def account_profile(style):
    ap = get(style)["account_profile"]
    return AP.for_venue(ap["venue"], ap["environment"])


_CUSTOM_CONSTRAINTS_SOURCE = ("docs/architecture/automation-config.json (dimension / timeframe / instrument "
                              "flags) and docs/architecture/analysis-params.json (thresholds)")


def _custom_constraints(trader):
    """§0.9's per-trader, per-methodology constraints resolved into `describe()`'s `custom_constraints`.

    `trader=None` (the default): unchanged from before §0.9 -- the platform-wide source, empty `items` (no
    trader was named, so there is nothing to resolve). A named trader resolves the full per-methodology list
    from `docs/architecture/trader-constraints.json`; an id that registry does not declare raises
    `trader_constraints.NotDeclared` rather than silently returning no constraints (no silent fallback)."""
    if trader is None:
        return {"source": _CUSTOM_CONSTRAINTS_SOURCE, "items": []}
    per = TC.for_trader(trader)
    items = [dict(item, methodology=methodology) for methodology, its in per.items() for item in its]
    return {"source": "docs/architecture/trader-constraints.json (CLAUDE.md §0.9)", "trader": trader,
           "items": items}


def describe(style, *, trader=None, **ctx):
    """CLAUDE.md §35's composition, resolved from the registries that own each part.

    Every field names its source. Nothing here is a second copy: change instruments.json and this changes.

    `trader` -- a §0.9 trader id (docs/architecture/trader-constraints.json), resolved into
    `custom_constraints["items"]`. Kept OUT of `**ctx`: `ctx` is forwarded to `classification()` /
    `role_of()`, whose `only_when` predicates accept exactly `setup` / `engaged` / `instrument` -- a `trader`
    passed through there would be an unrelated kwarg raising TypeError, and even if it did not, a trader's
    per-methodology constraints are not a §35 dependency-classification input.
    """
    sysd = get(style)
    market = sysd["market"]
    prof = account_profile(style)
    rows = setups(style)
    return {
        "id": style,
        "version": sysd["version"],
        "market": market,
        "market_types": list(I.market_types(market)),
        "timeframe": sysd["timeframe"],
        "horizon": sysd["horizon"],
        "instruments": {"analysis": list(I.live_analysis(market)), "execution": list(I.execution(market)),
                        "source": "docs/architecture/instruments.json"},
        "session": {"registry": "docs/architecture/sessions.json", "version": S.VERSION,
                    "windows": list(S.ORDER),
                    "note": "the per-instrument weight class is a property of the instrument's asset class, "
                            "not of this system -- sessions.weight_class(asset_class, session)"},
        "methodology": {"possible_on_market": list(M.dimensions(market)),
                        "presets_available": [p["id"] for p in M.presets_for(market)],
                        "note": "which preset (and therefore which mode and which engaged dimensions) is in "
                                "force is per-instrument and per-run: methods.dispatch_plan(instrument)"},
        # Excludes a row whose method is not (or no longer) in the registry, mirroring strategy-runner.py
        # load_setups()'s own `if s.get("method") in METHODS` filter -- rather than crashing describe() for
        # the WHOLE system over one stale row. This is a real state as of 2026-09-19: WYCKOFF, COMBINED and
        # PARTIAL were removed from docs/architecture/methods.json runner_methods
        # (docs/audits/2026-09-19-knowledge-fidelity.md finding 6), and docs/architecture/pilot-selection.json still
        # names them in 4 of its 6 rows -- deliberately left unregenerated by that removal (see its own commit);
        # scripts/rank-setups.py must re-select before those rows are valid again.
        "setups": [{"id": r["id"], "method": r["method"], "htf": r.get("htf"),
                    "entry": M.RUNNER_METHODS[r["method"]]["entry"], "exit": {"mgmt": r.get("mgmt")},
                    "execution": r.get("execution"), "rule_version": r.get("rule_version")}
                   for r in rows if r["method"] in M.RUNNER_METHODS],
        "execution_venues": list(execution_venues(style)),
        "account_profile": AP.snapshot(prof),
        "risk": {"max_risk_pct_source": "docs/architecture/risk-config.json max_risk_pct via "
                                        "trading_env.MAX_RISK_PCT",
                 "effective_max_risk_pct": AP.effective_risk_pct(prof),
                 "costs_source": "docs/architecture/risk-config.json costs via scripts/risk_model.py"},
        "custom_constraints": _custom_constraints(trader),
        "event_risk": {"source": "docs/architecture/event-calendar.json via scripts/event_risk.py",
                       "tightened_by_account": "scripts/account_profile.py tighten_calendar()"},
        "dependencies": classification(style, **ctx),
        "declared_required": list(declared_required(style)),
    }


def snapshot(style, **ctx):
    """The §11 configuration-snapshot view: what this system required, and under which version."""
    return {"trading_system": style, "trading_system_version": get(style)["version"],
            "dependency_profile": get(style)["dependency_profile"],
            "declared_required": list(declared_required(style)),
            "resolved_required": list(required(style, **ctx)),
            "classification": classification(style, **ctx),
            "source": "docs/architecture/trading-systems.json"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Trading System registry reader (CLAUDE.md §35).")
    ap.add_argument("style", nargs="?", help="a style id; omit to list all")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.style:
        for sid in styles():
            s = get(sid)
            print(f"{sid:<14} {s['market']:<7} {s['timeframe']:<4} {s['version']:<4} "
                  f"profile={s['dependency_profile']:<9} venues={','.join(execution_venues(sid)) or '(none)'}")
        sys.exit(0)
    if args.json:
        print(json.dumps(describe(args.style), indent=1, ensure_ascii=False, default=str)); sys.exit(0)
    d = describe(args.style)
    print(f"{d['id']} {d['version']} -- {d['market']} {d['timeframe']} ({d['horizon']}), "
          f"market types {', '.join(d['market_types'])}")
    print(f"  instruments   analysis={len(d['instruments']['analysis'])} "
          f"execution={len(d['instruments']['execution'])}")
    print(f"  setups        {', '.join(s['id'] for s in d['setups']) or '(none today)'}")
    print(f"  venues        {', '.join(d['execution_venues']) or '(none today)'}")
    print(f"  account       {d['account_profile']['profile_id']} "
          f"({d['account_profile']['venue']}/{d['account_profile']['environment']})")
    for role in ROLES:
        names = [k for k, v in d["dependencies"].items() if v == role]
        print(f"  {role:<22} {', '.join(names) or '(none)'}")
