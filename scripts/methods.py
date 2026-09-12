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

PATH = os.path.join(ROOT, "docs", "architecture", "methods.json")


def _validate(d):
    """The invariants _load() must hold. Split out so each can be tested directly with a small inline dict,
    rather than only via the real registry (where a collision may never happen to occur)."""
    modes = d.get("modes", {})
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
    path = config_path or CONFIG_PATH
    config_missing = False
    config_corrupt = None
    flags = {}
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        flags = (cfg.get("markets", {}).get(market, {}) or {}).get("dimensions", {}) or {}
        if not isinstance(flags, dict):
            raise ValueError(f"markets.{market}.dimensions is not an object")
    except FileNotFoundError:
        config_missing = True
    except (OSError, ValueError) as exc:
        config_corrupt = f"{path} is unreadable/corrupt ({exc}) -- falling back to dispatch-everything for " \
                          f"this read-only step; the config itself is untouched (CFG-02 governs writes, not this)."

    if config_missing or config_corrupt:
        flags = {d: True for d in have}

    dispatch, skipped, engaged = [], {}, []
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
        if market not in DIMENSIONS[d]["markets"]:
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
            if agent not in dispatch:
                dispatch.append(agent)

    mode_minimum = MODES[mode]["minimum"]
    return {"instrument": instrument, "market": market, "dispatch": dispatch, "skipped": skipped,
            "engaged": engaged, "engaged_count": len(engaged),
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
        for d, why in p["skipped"].items():
            print(f"SKIP {d}: {why}")
        print(f"engaged_count = {p['engaged_count']}; {p['mode']} minimum {p['mode_minimum']} "
              f"{'met' if p['meets_mode_minimum'] else 'NOT met -- verdict is NO TRADE on count alone'}")
