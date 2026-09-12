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
import json, os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "architecture", "methods.json")


def _load():
    with open(PATH, encoding="utf-8") as fh:
        d = json.load(fh)
    seen = {}
    for p in d["presets"]:
        key = frozenset(p["dimensions"])
        if key in seen:
            raise ValueError(f"{PATH}: presets '{seen[key]}' and '{p['id']}' name the same dimension set "
                             f"{sorted(key)}; profile_of would stop being a function.")
        seen[key] = p["id"]
        unknown = [x for x in p["dimensions"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: preset '{p['id']}' names unknown dimension(s) {unknown}.")
    for name, m in d["runner_methods"].items():
        unknown = [x for x in m["requires"] if x not in d["dimensions"]]
        if unknown:
            raise ValueError(f"{PATH}: runner method '{name}' requires unknown dimension(s) {unknown}.")
    return d


_DATA = _load()
DIMENSIONS = _DATA["dimensions"]
RUNNER_METHODS = _DATA["runner_methods"]
PRESETS = _DATA["presets"]
ALL_DIMENSIONS = list(DIMENSIONS)


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


def runner_methods(flags):
    """Methods whose every required dimension is on. Lookup over requires[], not a hard-coded rule."""
    on = _on(flags)
    return {name for name, m in RUNNER_METHODS.items() if set(m["requires"]) <= on}


def runnable():
    return {name for name, m in RUNNER_METHODS.items() if m["runnable"]}


def scan_of(name):
    return RUNNER_METHODS[name]["scan"]
