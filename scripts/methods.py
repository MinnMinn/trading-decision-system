"""THE reader for docs/architecture/methods.json -- the single source of truth for the Confluence dimensions,
the runner method table and the named presets (spec docs/specs/2026-09-12-method-switch-design.md §3).
Import this; never hard-code a dimension, method or preset list anywhere else.

    import methods as M
    M.dimensions("cfd")        -> ['wyckoff', 'ict']        # dimensions that market can have at all
    M.profile_of(flags)        -> 'wyckoff+ict' | 'custom'  # the NAME of a set of the four flags
    M.runner_methods(flags)    -> {'WYCKOFF', ...}          # methods whose requires[] is satisfied
    M.presets_for("cfd")       -> [preset, ...]             # presets whose dimensions all exist there

Loading enforces the invariant that keeps profile_of a function: no two presets may name the same set of
dimensions. A violation raises at import time rather than silently making one preset unreachable.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Module-scope, once -- not inside dispatch_plan(). instruments.py does not import methods (checked to rule out
# a cycle before adding this), and every other sibling-script importer in this repo (build-artifact.py,
# sync-methods.py, sync-instruments.py) does the same insert-once-at-module-scope dance for the same reason.
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
# i18n.py reads only its own JSON and imports nothing from this repo, so this direction cannot cycle.
import i18n as _i18n
# providers.py imports instruments (which imports nothing from this repo) and not methods, so no cycle.
import providers as _P

PATH = os.path.join(ROOT, "docs", "architecture", "methods.json")


PANE_KINDS = {"volume", "range_pct", "unavailable"}


def _localized(value, where):
    """A user-facing registry string, which since the EN/VI switch is a {locale: text} object.

    A bare string is still accepted and read as the authoring locale (i18n.AUTHORED), so a half-migrated
    registry loads rather than exploding -- but scripts/tests/test_i18n.py fails the build on one, because a
    bare string means the page would print Vietnamese in an English UI.
    """
    if isinstance(value, str):
        return {_i18n.AUTHORED: value} if value.strip() else None
    if isinstance(value, dict):
        missing = [l for l in _i18n.LOCALES if not (value.get(l) or "").strip()]
        if missing:
            raise ValueError(f"{PATH}: {where} has no {', '.join(missing)} text. Every user-facing registry "
                             f"string carries one entry per locale in docs/architecture/i18n.json `locales`; a "
                             f"missing one would print another language into that UI, which is the exact defect "
                             f"the language switch exists to prevent.")
        return dict(value)
    return None


def text(dim, field, lang):
    """The dimension's user-facing `field` in `lang` (e.g. text('ict', 'reads', 'en') -> 'price structure')."""
    return DIMENSIONS[dim][field][lang]


def preset_text(preset, field, lang):
    return preset[field][lang]


def pane_label(dim, lang):
    return DIMENSIONS[dim]["pane"]["label"][lang]


def _validate(d):
    """The invariants _load() must hold. Split out so each can be tested directly with a small inline dict,
    rather than only via the real registry (where a collision may never happen to occur)."""
    modes = d.get("modes", {})
    for name, dim in d["dimensions"].items():
        pane = dim.get("pane")
        if not isinstance(pane, dict) or "kind" not in pane or "label" not in pane:
            raise ValueError(f"{PATH}: dimension '{name}' has no `pane` spec (kind + label) -- every dimension "
                              f"must declare what the chart's second pane shows for it, or a future dimension "
                              f"silently renders an empty pane again.")
        if pane["kind"] not in PANE_KINDS:
            raise ValueError(f"{PATH}: dimension '{name}' pane.kind {pane['kind']!r} is not one of {sorted(PANE_KINDS)}.")
        pane["label"] = _localized(pane["label"], f"dimensions.{name}.pane.label")
        dim["reads"] = _localized(dim.get("reads"), f"dimensions.{name}.reads")
        if not dim["reads"]:
            raise ValueError(f"{PATH}: dimension '{name}' has no `reads` gloss -- the short phrase, per locale, for "
                             f"WHAT this dimension reads ({{'en': 'price + volume', 'vi': 'giá + khối lượng'}}). The "
                             f"page lede names each engaged dimension with it; without one, a 5th dimension would "
                             f"either render an empty parenthesis or send someone back to hard-coding the pair in "
                             f"build-artifact.py, which is the defect that shipped an ICT-only page claiming a "
                             f"Wyckoff read.")
        # CLAUDE.md §6: a dimension's data needs are named in the CAPABILITY vocabulary, not in vendor terms.
        # They used to be `ohlcv` / `coinglass_footprint` / `coinglass_heatmap` -- two of those three put a
        # vendor's name into the domain, so "which dimensions need CoinGlass" was answered by prefix-matching
        # a string, in the page builder (scripts/build-artifact.py). Wiring a second aggregated-intelligence
        # provider would have left that prefix test quietly wrong.
        if "data_sources" in dim:
            unknown_caps = [c for c in dim["data_sources"] if c not in _P.CAPABILITIES]
            if unknown_caps:
                raise ValueError(f"{PATH}: dimension '{name}' needs data source(s) {unknown_caps} that are not "
                                 f"in the capability vocabulary (docs/architecture/providers.json "
                                 f"`capabilities`). Declare the capability there first.")
            # The markets a dimension can be analysed in are a CONSEQUENCE of who supplies its capabilities,
            # not an independent fact. Keeping the authored list but checking it against the registry is the
            # repo's usual single-source-plus-drift-test shape (cf. scripts/sync-instruments.py).
            implied = sorted(set.intersection(*[set(_P.markets_with_capability(c)) for c in dim["data_sources"]])
                             if dim["data_sources"] else set())
            if sorted(dim["markets"]) != implied:
                raise ValueError(
                    f"{PATH}: dimension '{name}' lists markets {sorted(dim['markets'])}, but the providers "
                    f"that supply {dim['data_sources']} cover {implied} "
                    f"(docs/architecture/providers.json). One of the two is wrong -- a dimension claiming a "
                    f"market no provider serves would dispatch an agent against data that cannot exist "
                    f"(CLAUDE.md §6: never assume a capability).")
        if not isinstance(dim.get("owns_invalidation"), bool):
            raise ValueError(f"{PATH}: dimension '{name}' has no boolean `owns_invalidation` -- every dimension "
                             f"must declare whether it may own a trade's stop, or narrative.schema.json's "
                             f"owner enum silently loses (or gains) a value when a dimension is added.")
        # scripts/build-artifact.py OVERLAY_LANES and chart.js `drawnFor` (plan §0.7) key on this instead of a
        # hand-kept ("wyckoff", "ict") pair -- a 5th dimension declares whether it has a shape-drawing chart
        # engine here, or the pair comes back the moment someone forgets to touch build-artifact.py.
        if "overlay_engine" not in dim:
            raise ValueError(f"{PATH}: dimension '{name}' has no `overlay_engine` -- declare which chart-lane "
                             f"engine draws this dimension's shapes (e.g. 'wyckoff'), or `null` if none exists "
                             f"yet (CLAUDE.md §57 -- footprint/heatmap have no live source to draw from).")
        oe = dim["overlay_engine"]
        if oe is not None and not isinstance(oe, str):
            raise ValueError(f"{PATH}: dimension '{name}' overlay_engine must be a lane name or null, got {oe!r}.")
    seen = {}
    for p in d["presets"]:
        key = frozenset(p["dimensions"])
        if key in seen:
            raise ValueError(f"{PATH}: presets '{seen[key]}' and '{p['id']}' name the same dimension set "
                             f"{sorted(key)}; profile_of would stop being a function "
                             f"(docs/specs/2026-09-12-method-switch-design.md §6 invariant 3).")
        seen[key] = p["id"]
        unknown = [x for x in p["dimensions"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: preset '{p['id']}' names unknown dimension(s) {unknown}.")
        mode = p.get("mode")
        if mode not in modes:
            raise ValueError(f"{PATH}: preset '{p['id']}' names unknown mode {mode!r}; known modes: "
                             f"{sorted(modes)} (SYSTEM-DESIGN.md §6.2).")
        # SOLO is the whole safety argument for the mode: it may only be reached by a preset that itself
        # names exactly one dimension, a deliberate pre-analysis choice -- never by a multi-dimension preset
        # (SYSTEM-DESIGN.md §6.2 "preset, not runtime" rule; docs/specs/2026-09-12-method-switch-design.md).
        if mode == "SOLO" and len(p["dimensions"]) != 1:
            raise ValueError(f"{PATH}: preset '{p['id']}' names {len(p['dimensions'])} dimensions but mode "
                             f"SOLO -- SOLO is reserved for single-dimension presets (SYSTEM-DESIGN.md §6.2).")
        if mode != "SOLO" and len(p["dimensions"]) == 1:
            raise ValueError(f"{PATH}: preset '{p['id']}' names exactly one dimension but mode {mode!r} -- "
                             f"a single-dimension preset must be mode SOLO (SYSTEM-DESIGN.md §6.2).")
    for name, m in d["runner_methods"].items():
        unknown = [x for x in m["requires"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: runner method '{name}' requires unknown dimension(s) {unknown}.")
    # Display text is checked LAST, deliberately. A registry with both a structural fault and a missing label
    # should report the structural one: "you named an unknown dimension" tells an author what to fix, "you
    # forgot a label" sends them to the wrong line. It also keeps the minimal fixtures in
    # scripts/tests/test_methods.py free to omit copy they are not testing.
    for p in d["presets"]:
        p["label"] = _localized(p.get("label"), f"presets[{p['id']}].label")
        if not p["label"]:
            raise ValueError(f"{PATH}: preset '{p['id']}' has no `label` -- the page footer names the configured "
                             f"preset with it, one entry per locale.")


def _load():
    with open(PATH, encoding="utf-8") as fh:
        d = json.load(fh)
    _validate(d)
    return d


_DATA = _load()
DIMENSIONS = _DATA["dimensions"]
RUNNER_METHODS = _DATA["runner_methods"]
PRESETS = _DATA["presets"]
MODES = _DATA["modes"]          # {"SOLO": {"minimum": 1, "threshold": 85}, "NORMAL": {...}, ...} -- SYSTEM-DESIGN.md §6.2
ALL_DIMENSIONS = list(DIMENSIONS)
DEFAULT_MODE = "NORMAL"         # unchanged default when a preset can't be named (custom / UNREADABLE config)


def dimensions(market):
    """The dimensions this market can have AT ALL -- the shape, not the on/off state."""
    return [d for d, v in DIMENSIONS.items() if market in v["markets"]]


# CLAUDE.md §15: the active trading configuration is NOT a global analysis filter.
#
# `analysis_scope` separates two questions the method preset currently answers with one flag:
#   "which dimensions may qualify a trade?"  -> the preset (required_for_decision)
#   "which dimensions do we still analyse?"  -> this
#
# `available`  -- analyse every dimension this market has a LIVE source for, whatever the preset says. This is
#                 §15's own default: "The system may continue analyzing all available methodologies when their
#                 data and capabilities are available."
# `preset`     -- analyse only the preset's dimensions. The behaviour before 2026-09-18, kept selectable
#                 because a user may genuinely want to spend nothing on reads they will not trade -- but it
#                 is now a DELIBERATE choice rather than an architectural consequence.
ANALYSIS_SCOPES = ("available", "preset")
DEFAULT_ANALYSIS_SCOPE = "available"


def live_sourced(dim, market):
    """Does every capability this dimension needs have a CONNECTED provider in this market? (CLAUDE.md §6)

    Distinct from `market in DIMENSIONS[dim]["markets"]`, which answers the STRUCTURAL question ("could this
    market ever have this dimension"). Footprint is structurally possible on crypto and not live-sourced
    anywhere, because CoinGlass has no API key. Conflating the two is how a fixture satisfies a live decision
    requirement, which SYSTEM-DESIGN.md §6.1 forbids by name.
    """
    return all(_P.providers_with(c, market, live_only=True) for c in DIMENSIONS[dim]["data_sources"])


def source_status(dim, market):
    """Per-capability report for a dimension in a market: which provider, what status, and WHY not, if not.

    CLAUDE.md §6 requires an unavailable capability to expose its state AND preserve the reason. "footprint
    unavailable" reads identically whether the vendor is down, unconfigured, or was never a source for this
    market -- three different answers to "should I wait?".
    """
    return [_P.capability_report(c, market) for c in DIMENSIONS[dim]["data_sources"]]


def _market_config(market, config_path=None):
    """One read of /automation's block for `market` -> (dimension flags, analysis scope, missing, corrupt).

    Extracted so `dispatch_plan` (which needs the whole picture for one instrument) and `analysed_dimensions`
    (which the AUTHORING path needs for a whole market, with no instrument in hand) cannot drift on how the
    config is read or on what an absent/!unreadable `analysis_scope` falls back to.

    An unreadable or absent `analysis_scope` falls back to the spec's own default rather than to the preset,
    because "continue analysing" is what §15 asks for and silently narrowing analysis is the failure it names.
    """
    path = config_path or CONFIG_PATH
    flags, scope, config_missing, config_corrupt = {}, None, False, None
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        block = (cfg.get("markets", {}) or {}).get(market, {}) or {}
        flags = block.get("dimensions", {}) or {}
        if not isinstance(flags, dict):
            raise ValueError(f"markets.{market}.dimensions is not an object")
        scope = block.get("analysis_scope")
    except FileNotFoundError:
        config_missing = True
    except (OSError, ValueError) as exc:
        config_corrupt = f"{path} is unreadable/corrupt ({exc}) -- falling back to dispatch-everything for " \
                          f"this read-only step; the config itself is untouched (CFG-02 governs writes, not this)."
    if scope not in ANALYSIS_SCOPES:
        scope = DEFAULT_ANALYSIS_SCOPE
    return flags, scope, config_missing, config_corrupt


def _analysis_verdict(d, market, flags, scope, unavailable):
    """§15 for ONE dimension: None if it is analysed, else the reason it is not.

    Live-sourcing is the gate, not the preset: analysing a dimension whose only provider is a fixture would be
    the §6 mock-satisfies-a-requirement failure wearing a different hat.
    """
    if market not in DIMENSIONS[d]["markets"]:
        return f"{market} has no source for {d}"
    if d in unavailable:
        return f"{d} data source unavailable for this run"
    if not live_sourced(d, market):
        reasons = [r["reason"] for r in source_status(d, market) if r["reason"]]
        return reasons[0] if reasons else f"{d} has no connected provider for {market}"
    if scope == "preset" and not flags.get(d, True):
        return (f"analysis_scope is 'preset' and dimensions.{d} is off -- a deliberate narrowing; "
                f"§15's default ('available') would analyse it")
    return None


def analysed_dimensions(market, config_path=None, unavailable=None):
    """CLAUDE.md §15 for a whole MARKET: which dimensions are still ANALYSED, and why each other one is not.

    The trading-eligibility question ("which dimensions may qualify a trade") is deliberately NOT answered
    here -- that is the preset, and it is `dispatch_plan`'s `engaged`. This function is what the authoring and
    display paths ask, because §15's rule is that the active trading selection "is NOT a global analysis
    filter": a methodology the preset does not trade is still read when its data is live.

    Returns (analysed, analysis_skipped, scope). Market-level rather than instrument-level because the
    authoring path (a chart style covering several symbols) has no single instrument to ask about, and the
    answer does not vary by instrument within a market anyway -- it is a function of the market's providers
    and the market's config block.
    """
    flags, scope, missing, corrupt = _market_config(market, config_path)
    if missing or corrupt:
        flags = {d: True for d in dimensions(market)}
    analysed, skipped = [], {}
    for d in ALL_DIMENSIONS:
        why = _analysis_verdict(d, market, flags, scope, set(unavailable or ()))
        (skipped.__setitem__(d, why) if why else analysed.append(d))
    return analysed, skipped, scope


def invalidation_owners():
    """Dimensions that may OWN a trade's invalidation level. A stop is a price level: the two structural reads
    define one, footprint/heatmap describe activity AT a level. Order is registry order, so generated enums and
    error messages are stable. Read this — do not hand-keep the pair in a checker or a schema."""
    return tuple(d for d, v in DIMENSIONS.items() if v.get("owns_invalidation"))


def markets():
    out = []
    for v in DIMENSIONS.values():
        for m in v["markets"]:
            if m not in out:
                out.append(m)
    return out


def _on(flags):
    return frozenset(d for d in ALL_DIMENSIONS if flags.get(d))


def profile_of(flags):
    """The preset id naming this set of flags, or 'custom'. Pure function of the flags."""
    on = _on(flags)
    for p in PRESETS:
        if frozenset(p["dimensions"]) == on:
            return p["id"]
    return "custom"


def preset(pid):
    for p in PRESETS:
        if p["id"] == pid:
            return p
    return None


def presets_for(market):
    """Presets every one of whose dimensions exists in this market. cfd has no CoinGlass source, so any
    preset naming footprint/heatmap is structurally impossible there (SYSTEM-DESIGN.md §12 item 3)."""
    have = set(dimensions(market))
    return [p for p in PRESETS if set(p["dimensions"]) <= have]


def flags_for(pid):
    """The four booleans a preset means. Raises on an unknown id -- callers must validate first."""
    p = preset(pid)
    if p is None:
        raise KeyError(pid)
    return {d: d in p["dimensions"] for d in ALL_DIMENSIONS}


def mode_of(preset_name):
    """The methodology mode a preset id resolves to, per its own `mode` field in the registry -- SOLO for the
    two single-dimension presets, NORMAL for every multi-dimension preset today (SYSTEM-DESIGN.md §6.2).
    `preset_name` may be 'custom' or 'UNREADABLE' (dispatch_plan's non-preset states); both fall back to
    DEFAULT_MODE, the same behaviour as before SOLO existed. This is the ONLY function that may decide a run's
    mode is SOLO -- it is a pure function of the preset id, never of how many dimensions turned out to be
    engaged, which is exactly the preset-not-runtime rule the mode-lock exists to enforce."""
    p = preset(preset_name)
    return p["mode"] if p is not None else DEFAULT_MODE


def runner_methods(flags):
    """Methods whose every required dimension is on. Lookup over requires[], not a hard-coded rule."""
    on = _on(flags)
    return {name for name, m in RUNNER_METHODS.items() if set(m["requires"]) <= on}


def runnable():
    return {name for name, m in RUNNER_METHODS.items() if m["runnable"]}


def scan_of(name):
    return RUNNER_METHODS[name]["scan"]


CONFIG_PATH = os.path.join(ROOT, "docs", "architecture", "automation-config.json")


def dispatch_plan(instrument, config_path=None, unavailable=None):
    """Which read-only agents /analyze must dispatch for this instrument, and why each skipped one is skipped.
    The gating logic lives here so .claude/commands/analyze.md does not have to be edited when a dimension is
    added (spec §4.2).

    `unavailable` (optional) names dimensions whose LIVE data source is known unavailable for this specific
    run (e.g. CoinGlass down this morning) -- distinct from a dimension's /automation config flag being off.
    This is deliberately a separate input from `config_path`'s flags: the config flags are the user's
    deliberate preset selection and are what `mode` is derived from (SOLO only when the preset itself names
    exactly one dimension); `unavailable` can only lower `engaged_count` for this run, exactly like a
    config-off dimension does, but it must NEVER change which preset/mode is in force -- otherwise a
    multi-dimension preset that loses a dimension to a live outage would silently downgrade to SOLO and could
    pass on a single dimension, which is precisely the after-the-fact mode downgrade §6.2's mode-lock rule
    forbids. See SYSTEM-DESIGN.md §6.2 "SOLO mode" for the full rule.

    Config states, distinguished so a corrupt file cannot masquerade as a real preset:
      - MISSING file -> unconfigured, exactly as before the switch existed: dispatch everything this market
        can have. Silent -- this is the expected state for anyone who has never opened /automation.
      - CORRUPT file (exists but does not parse, or is not the expected shape) -> also falls back to
        dispatch-everything (this is a read-only advisory step, not a write path -- CFG-02's refuse-on-corrupt
        rule is about automation.py's mutating subcommands, where a silent fallback would entrench a bad write;
        here the worst case is over-dispatching a few extra read-only agents, not an unsafe trade). But it is
        NOT silent: `config_corrupt` carries the reason, `preset` is reported as "UNREADABLE" rather than a
        computed name (a made-up preset name here would be exactly the "claims a preset that is not real"
        problem this function exists to avoid), and the CLI prints the reason prominently.
    """
    market = I.market_of(instrument)
    if market is None:
        raise ValueError(f"{instrument} is not on the allowlist (docs/architecture/instruments.json)")
    have = set(dimensions(market))
    unavailable = set(unavailable or ())
    flags, scope, config_missing, config_corrupt = _market_config(market, config_path)
    if config_missing or config_corrupt:
        flags = {d: True for d in have}

    dispatch, skipped, engaged, analysed, analysis_skipped = [], {}, [], [], {}
    # Preset NAME uses only this market's structurally possible dimensions (defaulting the rest to off) --
    # otherwise an unrelated market's missing keys (e.g. cfd has no footprint/heatmap keys at all) would read
    # as "on" and misname the preset (e.g. XAUUSD would wrongly show "full" instead of "wyckoff+ict").
    # Deliberately built from CONFIG flags only, never from `unavailable` -- this is what makes `mode` a
    # function of the preset the user selected, not of what turned out to be available at analysis time.
    preset_flags = {d: (flags.get(d, True) if d in have else False) for d in ALL_DIMENSIONS}
    preset_name = "UNREADABLE" if config_corrupt else profile_of(preset_flags)
    mode = mode_of(preset_name)

    for d in ALL_DIMENSIONS:
        agent = DIMENSIONS[d]["agent"]
        structurally_possible = market in DIMENSIONS[d]["markets"]

        # --- Trading eligibility (unchanged): which dimensions may count toward the mode minimum.
        if not structurally_possible:
            skipped[d] = (f"{market} has no source for {d} -- CoinGlass is crypto-derivatives only "
                          f"(SYSTEM-DESIGN.md §12 item 3)")
        elif not flags.get(d, True):
            skipped[d] = f"dimensions.{d} is off in /automation (method preset {preset_name})"
        elif d in unavailable:
            skipped[d] = (f"{d} data source unavailable for this run -- lowers engaged_count only; the locked "
                          f"mode stays {mode} (preset {preset_name}) regardless, per the mode-lock rule "
                          f"(SYSTEM-DESIGN.md §6.2) -- a degraded multi-dimension preset never becomes SOLO")
        else:
            engaged.append(d)

        # --- Analysis scope (CLAUDE.md §15): a dimension the preset does not trade may still be READ, and
        # under the `available` scope it is. Shared with `analysed_dimensions`, which the authoring and
        # display paths call with a market and no instrument -- one implementation, so a page and a decision
        # record can never disagree about what was analysed.
        why = _analysis_verdict(d, market, flags, scope, unavailable)
        (analysis_skipped.__setitem__(d, why) if why else analysed.append(d))

        # Dispatch is the UNION of "may qualify a trade" and "is still analysed", never just one of them.
        # Making it follow `analysed` alone would stop dispatching an agent for a dimension the preset DOES
        # trade whenever that dimension's only provider is a fixture -- which would silently break the
        # deliberate mock rehearsal runs docs/architecture/data-sources.md keeps the fixtures for. Additive is
        # the safe direction: §15 asks for MORE analysis, not less.
        if (d in engaged or d in analysed) and agent not in dispatch:
            dispatch.append(agent)

    mode_minimum = MODES[mode]["minimum"]
    return {"instrument": instrument, "market": market, "dispatch": dispatch, "skipped": skipped,
            "engaged": engaged, "engaged_count": len(engaged),
            # CLAUDE.md §15: analysed >= engaged. A dimension may be read without being tradeable; the
            # reverse would be a dimension counting toward a verdict without having been read.
            "analysed": analysed, "analysis_skipped": analysis_skipped, "analysis_scope": scope,
            "analysed_not_traded": [d for d in analysed if d not in engaged],
            "mode": mode, "mode_minimum": mode_minimum, "mode_threshold": MODES[mode]["threshold"],
            "meets_mode_minimum": len(engaged) >= mode_minimum,
            "preset": preset_name, "config_missing": config_missing, "config_corrupt": config_corrupt}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Method registry reader.")
    ap.add_argument("--dispatch-plan", metavar="INSTRUMENT")
    args = ap.parse_args()
    if args.dispatch_plan:
        try:
            p = dispatch_plan(args.dispatch_plan)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(2)
        if p["config_corrupt"]:
            print(f"** CONFIG UNREADABLE: {p['config_corrupt']}", file=sys.stderr)
        print(f"instrument: {p['instrument']} ({p['market']})   method preset: {p['preset']}   "
              f"mode: {p['mode']} (minimum {p['mode_minimum']}, threshold {p['mode_threshold']})")
        print(f"DISPATCH:   {', '.join(p['dispatch']) or '(none)'}")
        print(f"analysis scope: {p['analysis_scope']}   analysed: {', '.join(p['analysed']) or '(none)'}"
              + (f"   (read but NOT tradeable: {', '.join(p['analysed_not_traded'])})"
                 if p["analysed_not_traded"] else ""))
        for d, why in p["skipped"].items():
            print(f"NOT TRADEABLE {d}: {why}")
        for d, why in p["analysis_skipped"].items():
            print(f"NOT ANALYSED  {d}: {why}")
        print(f"engaged_count = {p['engaged_count']}; {p['mode']} minimum {p['mode_minimum']} "
              f"{'met' if p['meets_mode_minimum'] else 'NOT met -- verdict is NO TRADE on count alone'}")
