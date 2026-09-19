"""THE session model (CLAUDE.md §21), read from one registry instead of six hand-kept copies.

    import sessions as S
    S.active("2026-03-10T13:00:00Z")        -> ('ny_am',)        every window this instant is inside
    S.primary("2026-03-10T13:00:00Z")       -> 'ny_am'           one label, by DECLARED precedence
    S.weight_class("metals", "london")      -> 'full'
    S.LABELS                                -> ('london','ny_am','ny_pm','asia','off')

§21 asks for sessions that are "timezone-aware, DST-aware, historically reproducible, configurable", and names
overlaps and custom sessions as first-class. Four of those six were already true and two were not:

  * **Configurable.** The windows lived in a markdown table (`session-model.md` §2), Python literals
    (`journal.session_of`), a JS array (`chart.js SESSIONS`), a JS weight map (`chart.js KZ_WEIGHT`), a schema
    enum (`trade-file.schema.json`), and a second markdown table (`session-model.md` §3). Six copies of one
    fact with no generator and no drift test -- exactly what this repo's single-source rule exists to stop, and
    "configurable" is not a property a markdown table has. Now: edit `docs/architecture/sessions.json`, run
    `scripts/sync-sessions.py --write`.
  * **Overlaps.** §21 lists them as a supported concept. `journal.session_of` was an if/elif chain, so if a
    window were ever configured to overlap another the first branch would silently win -- a resolution nobody
    declared. `active()` returns ALL matching windows; `primary()` collapses them by a precedence the registry
    states out loud. Today's four windows do not overlap (London 08-11 local is 13:30-16:00 London when NY AM
    runs), so this changes no current label -- which is the point of adding it before it is needed rather than
    after a window moves.

**Reproducibility.** The conversion has always been DST-correct (real IANA zones, per timestamp). What was
missing is that a session label is stamped on every journalled trade, so moving a window silently re-labels
history. `VERSION` makes the model a recorded input rather than an assumption (§11, §59).

**What this module does NOT do:** it awards no points. Which window an instant is in is a domain fact; what
that is worth is a scoring parameter, and it stays in `analysis-params.json timing.weight_by_class` beside the
number. This module returns a weight CLASS and stops there.
"""
import datetime
import json
import os
import zoneinfo

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "architecture", "sessions.json")


def _read():
    with open(PATH, encoding="utf-8") as fh:
        return json.load(fh)


_DATA = _read()

VERSION = _DATA["version"]
OFF = _DATA["off_label"]
WINDOWS = {k: v for k, v in _DATA["sessions"].items() if not k.startswith("_")}
WEIGHTS = {k: v for k, v in _DATA["weights"].items() if not k.startswith("_") or k == "_default"}
_DEFAULT_WEIGHTS = _DATA["weights"]["_default"]
GATES = _DATA["gates"]

# Ordered by the registry's own precedence, then named. `off` is last and is not a window.
ORDER = tuple(sorted(WINDOWS, key=lambda k: (WINDOWS[k]["precedence"], k)))
LABELS = ORDER + (OFF,)

_ZONES = {}

# ---- validation at import. A session model that loads but is wrong is worse than one that refuses: every
# fault below would silently mislabel trades rather than raise anywhere.
for _k, _w in WINDOWS.items():
    for _f in ("zone", "start", "end", "precedence", "what"):
        if _f not in _w:
            raise ValueError(f"{PATH}: session {_k!r} is missing {_f!r}. A window with no zone cannot be "
                             f"converted, and one with no precedence cannot be collapsed to a single label "
                             f"without an implicit rule somewhere (CLAUDE.md §21).")
    try:
        _ZONES[_w["zone"]] = zoneinfo.ZoneInfo(_w["zone"])
    except Exception as _exc:
        raise ValueError(f"{PATH}: session {_k!r} names zone {_w['zone']!r}, which is not a real IANA zone "
                         f"({_exc}). A fixed UTC offset here would be an hour wrong for eight months a year.")
    # tzdata also ships the legacy ABBREVIATION aliases -- 'EST', 'MST', 'CET', 'Japan' -- and `ZoneInfo('EST')`
    # loads happily while meaning a permanent -05:00 with no daylight saving. That is exactly the trap
    # session-model.md §1 was written about: the ICT decks label their windows "EST" year-round, and taking that
    # literally leaves the NY window an hour off the real open for roughly eight months. A genuine exchange zone
    # is always Region/City, so requiring the slash rejects the aliases without rejecting the many real
    # no-DST zones (Asia/Tokyo, Asia/Singapore, Asia/Dubai) a custom session might legitimately name.
    if "/" not in _w["zone"] and _w["zone"] != "UTC":
        raise ValueError(
            f"{PATH}: session {_k!r} names zone {_w['zone']!r}. tzdata loads it, but the abbreviation aliases "
            f"are FIXED offsets with no daylight saving -- 'EST' is a permanent -05:00, not New York's clock. "
            f"Use the Region/City zone (America/New_York) so the window follows DST, which is the whole point "
            f"of CLAUDE.md §21's 'DST-aware' and of docs/architecture/session-model.md §1.")
    for _f in ("start", "end"):
        if not isinstance(_w[_f], (int, float)) or not 0 <= _w[_f] <= 24:
            raise ValueError(f"{PATH}: session {_k!r} {_f} must be a local hour in [0, 24], got {_w[_f]!r}.")
    if _w["start"] == _w["end"]:
        raise ValueError(f"{PATH}: session {_k!r} opens and closes at the same hour, so it is never active. "
                         f"A zero-width window is almost always a typo, and it would silently award nothing.")
if len({_w["precedence"] for _w in WINDOWS.values()}) != len(WINDOWS):
    raise ValueError(f"{PATH}: two sessions share a precedence. Precedence exists to make an overlap resolve "
                     f"the same way every time; a tie would put the answer back in dict order.")
if OFF in WINDOWS:
    raise ValueError(f"{PATH}: {OFF!r} is the label for being in NO window and cannot also be a window.")
for _cls, _map in _DATA["weights"].items():
    if _cls.startswith("_") and _cls != "_default":
        continue
    _unknown = [s for s in _map if s not in WINDOWS]
    if _unknown:
        raise ValueError(f"{PATH}: weights.{_cls} names session(s) {_unknown} that no window declares.")
    _absent = [s for s in WINDOWS if s not in _map]
    if _absent:
        raise ValueError(f"{PATH}: weights.{_cls} says nothing about {_absent}. A session with no declared "
                         f"class for an asset class would fall back silently; say `none` and mean it.")


def _parse(value):
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _local_hour(when, zone):
    lt = when.astimezone(_ZONES[zone])
    return lt.hour + lt.minute / 60 + lt.second / 3600


def _inside(hour, start, end):
    """End-exclusive, and correct for a window that crosses local midnight (end <= start)."""
    return start <= hour < end if start < end else (hour >= start or hour < end)


def active(when):
    """Every session window this instant is inside, in precedence order. Empty tuple means `off`.

    Returns a tuple rather than one label because §21 names overlaps as a supported concept: a caller that
    wants one answer should say so by calling primary(), not receive one by accident.
    """
    t = _parse(when)
    if gated(t):
        return ()
    return tuple(k for k in ORDER
                 if _inside(_local_hour(t, WINDOWS[k]["zone"]), WINDOWS[k]["start"], WINDOWS[k]["end"]))


def primary(when):
    """The single session label for this instant -- the highest-precedence active window, else `off`.

    This is what the trade file records and what the journal groups by, because both need one value per trade.
    The collapse rule is the registry's declared precedence, not the order of a chain of ifs.
    """
    return (active(when) or (OFF,))[0]


def gated(when):
    """True when no session credit may be awarded whatever the clock says (registry `gates`)."""
    t = _parse(when)
    wk = GATES.get("weekend") or {}
    return bool(wk.get("enabled")) and t.weekday() in tuple(wk.get("days") or ())


def weight_class(asset_class, session):
    """The weight CLASS ('full' / 'reduced' / 'none') for this asset class in this session.

    An unknown asset class gets the registry's `_default` (all `none`) rather than a guess: handing an
    instrument nobody has considered the same credit as gold is how a scoring model quietly widens.
    """
    if session == OFF:
        return "none"
    if session not in WINDOWS:
        raise ValueError(f"unknown session {session!r}; the registry declares {list(LABELS)}")
    return (WEIGHTS.get(asset_class) or _DEFAULT_WEIGHTS)[session]


def js_sessions():
    """The window table in the shape scripts/chart.js consumes, injected through build-artifact's params.

    chart.js held its own `const SESSIONS` array and its own `KZ_WEIGHT` map. Shipping them from here is the
    same move i18n already made for the string catalog: the page gets the data, never a second copy of it.
    """
    return [{"key": k, "name": WINDOWS[k].get("display") or k.replace("_", " ").upper(),
             "tz": WINDOWS[k]["zone"], "a": WINDOWS[k]["start"], "b": WINDOWS[k]["end"]} for k in ORDER]


def js_weights():
    """Weight classes for chart.js, with the registry's `_default` shipped as `default`.

    chart.js used to fall back to `KZ_WEIGHT.crypto` for an unrecognised asset class, which quietly gave an
    unconsidered instrument crypto's reduced London and NY AM shading. The registry's default is `none`
    everywhere, and the page must agree with the scorer about that or the shading claims credit the score
    never awarded."""
    out = {c: dict(m) for c, m in _DATA["weights"].items() if not c.startswith("_")}
    out["default"] = dict(_DEFAULT_WEIGHTS)
    return out


def describe(when, asset_class=None):
    """One line naming the window, the local-to-UTC conversion used for THIS date, and the weight class.

    session-model.md §5 requires exactly this of any analysis that awards timing points, and requiring it of
    prose alone is how the DST conversion stops being stated. The wording says 'project assumption' because it
    is one -- the ICT sources give no killzone rule for crypto or commodity CFDs at all.
    """
    t = _parse(when)
    s = primary(t)
    if s == OFF:
        return f"Timing: off ({'weekend gate' if gated(t) else 'outside every window'})."
    w = WINDOWS[s]
    lo = t.astimezone(_ZONES[w["zone"]]).replace(
        hour=int(w["start"]), minute=int(round((w["start"] % 1) * 60)), second=0, microsecond=0)
    hi = lo + datetime.timedelta(hours=w["end"] - w["start"])
    span = (f"{w['start']:g}-{w['end']:g} {w['zone']} = "
            f"{lo.astimezone(datetime.timezone.utc):%H:%M}-{hi.astimezone(datetime.timezone.utc):%H:%M}Z")
    cls = f", weight {weight_class(asset_class, s)}" if asset_class else ""
    return (f"Timing: {s} ({span} on this date){cls}. Project assumption per "
            f"docs/architecture/session-model.md (model v{VERSION}).")
