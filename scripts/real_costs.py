"""A0 real costs (CLAUDE.md §34; docs/plans/2026-09-28-methodology-improvement-plan.md §2 "A0 Costs").

Per-symbol, per-UTC-hour spread + per-night-held swap, read from the broker's OWN MT5 symbol-specification
export -- never guessed. Selected by a named, versioned PROFILE; the flat `risk_model.py` mt5 fee stays the
default everywhere nothing asks for a profile by name, so every existing caller's output is unchanged (plan
§1.6 "live safety": A0's cost inputs land behind a versioned key that defaults to v1 behaviour).

    import real_costs as RC
    RC.spec("ftmo_demo_2026_09", "XAUUSD")                 -> the raw symbolspec dict
    RC.spread_price("ftmo_demo_2026_09", "XAUUSD", 14)     -> (price, "hour" | "overall_fallback")
    RC.swap_price("ftmo_demo_2026_09", "XAUUSD", "long", entry_time, exit_time) -> (signed_price, nights, note)
    RC.cost_r(entry, stop, entry_time, exit_time, "XAUUSD", "long", "ftmo_demo_2026_09")
        -> {"spread_R":..., "swap_R":..., "commission_R":..., "total_R":..., ...}
    RC.crosses_rollover(bar_close_iso, next_bar_close_iso, provider) -> bool  (flat_before_rollover, §2 A0)
    RC.profile_snapshot(name, canonical_symbols)            -> {"profile":..., "source_files_sha256": {...}}

WHERE THE NUMBERS COME FROM
----------------------------
`data/history/costs/ftmo/symbolspec.<MT5 name>.json` (FTMO-Demo, exported by integrations/mt5/ExportSymbolSpec.mq5
2026-09-28): per-symbol `point`, `swap_long`/`swap_short` (POINTS per lot per day, swap_mode 1 =
SYMBOL_SWAP_MODE_POINTS), `swap_rollover3days` (the MQL5 day-of-week, SUNDAY=0..SATURDAY=6, that charges triple
swap), `commission` (`status: "no_deals"` on every symbol recorded so far -- data/history/costs/ftmo/symbol-map.json's
own note), and `recorded_spread_m15.by_utc_hour[h]` (median/p90 spread in points, from 100k M15 bars per symbol).
`data/history/costs/symbolspec.<SYM>.json` is the same export shape for MetaQuotes-Demo, already named with the
canonical symbol (no map needed). FTMO's specs are named with the MT5 platform symbol (`US500.cash`, `GER40.cash`,
...) -- `data/history/costs/ftmo/symbol-map.json` is the (MT5 name -> canonical) map this module reverses.

COMMISSION IS NEVER GUESSED
----------------------------
Every FTMO-Demo spec recorded so far declares `commission.status == "no_deals"` (the account has not traded).
`commission_r()` always returns `(0.0, status)` -- never a number this module invented -- and even a future
`"from_deals"` spec only carries a PER-LOT figure, which this engine's R-based (percent-of-equity) costing has
no lot size to apply it to. Left as ONE function so a real, sourced commission figure can be dropped in
later (task instruction, plan §2 A0) without touching every caller.

SPREAD CONVENTION
------------------
A round trip pays the spread ONCE (buy at ask, sell at bid), so each leg is charged HALF the spread recorded
for its own bar's hour -- structurally the same "per side" shape `risk_model.cost_r` already uses for the flat
mt5 fee (entry_fee + exit_fee, each priced separately). Entry pays the entry bar's own UTC-hour median (or p90
under `spread_stat="p90"`, the disclosed stress option); exit pays the exit bar's own hour. An hour with no
recorded bars (n=0 -- e.g. the broker's daily break) falls back to the symbol's overall median/p90, a coarser
but still MEASURED figure, flagged via the returned `note` rather than silently substituted.

ABSOLUTE vs RELATIVE SPREAD (C2, red-team 2026-10-02)
------------------------------------------------------
The recorded spreads are ABSOLUTE price units (points * point) measured on 2022-07..2026-09 prices. Charged unchanged
against a 2007-2024 trade (XAUUSD ~$1,100-1,700 then, ~$4,000 now) that overstates spread_R 2-4x in early folds and
drifts across folds. The profile `ftmo_demo_2026_09_relspread` (same files, same hours, same fallback) therefore
scales the spread with the entry price: `spread_price(trade) = spread_points * point * entry / price_ref(symbol)` for
both legs, median and p90 alike, where `price_ref(symbol)` is the MEDIAN CLOSE of the symbol's M15 bars over the
spreads' recording window (spec `recorded_spread_m15.first_bar_server` .. `last_bar_server`, converted to UTC with the
profile's own server clock, both bar-open labels inclusive) from the committed `data/history/ftmo` M15 series. The window
is the spec's, but the stored XPTUSD / XPDUSD series hold 99,999 bars in it against the spec's 100,000 (the last spec bar,
02:45 UTC, is missing from the history; the other seven symbols match exactly; the effect on the median is nil). The closes
run to 2026-09 / 10, after the development cutoff: `price_ref` is a constant per-symbol cost-calibration scale (not an
outcome read), consistent with the spreads' own recording window. At
entry == price_ref the two profiles agree. Swap is unaffected (every fund trade is flat before the rollover; swap is not
rescaled here). `ftmo_demo_2026_09` keeps the ABSOLUTE behaviour byte-identically (a comparison baseline; no fund-search code uses it).

SWAP CONVENTION
-----------------
One swap charge per server-LOCAL calendar day the position was held across a rollover (`nights_held`), tripled
on the day whose MQL5 weekday matches the spec's own `swap_rollover3days` (the standard weekend-bundling
convention: the extra two days are folded into one broker night, usually Wednesday). The server clock is
whichever provider the selected profile declares (`mt5_time.server_zone`) -- FTMO-Demo runs on
`server_timezone_convention: us_dst_dates_fixed_offset` (docs/audits/2026-09-29-ftmo-server-timezone.md),
so the DST edge this module inherits is exactly the one `mt5_time.py` already gets right; this module reuses
its zone objects rather than re-deriving DST rules (CLAUDE.md §58).

`crosses_rollover(bar_close_iso, next_bar_close_iso, provider)` is the SAME server-local-date comparison,
reused by `scripts/backtest-methods.py walk()` for the "no overnight holding" fund-cell rule
(OPTS["flat_before_rollover"]): a position still open at the last bar that closes before the server's own
midnight is flattened there, never at a bar that has not closed yet (CLAUDE.md §8 point-in-time: the decision
uses only the clock, never a later price).
"""
import datetime
import functools
import gzip
import hashlib
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mt5_time as _MT   # noqa: E402 -- THE server-zone resolver (docs/architecture/providers.json)
import history_store as _HS   # noqa: E402 -- THE history reader (single-file / split-gz shapes)

COSTS_ROOT = os.path.join(ROOT, "data", "history", "costs")
UNKNOWN = "UNKNOWN"

#: profile name -> {server, provider (docs/architecture/providers.json id, for mt5_time.server_zone), spec_dir,
#: symbol_map (MT5 name -> canonical, or None when the spec files are already named with the canonical symbol)}.
#: Versioned by month in the name on purpose -- a re-export next quarter is a NEW profile, not a silent update
#: of this one, so an old snapshot's `profile` name still resolves to the exact files it was measured against.
PROFILES = {
    "ftmo_demo_2026_09": {
        "server": "FTMO-Demo",
        "provider": "mt5_bridge_ftmo",
        "spec_dir": os.path.join(COSTS_ROOT, "ftmo"),
        "symbol_map": os.path.join(COSTS_ROOT, "ftmo", "symbol-map.json"),
    },
    # C2: the SAME FTMO files and server clock, spread scaled by entry / price_ref (module docstring). A NEW profile name,
    # so a record's `profile` still names the exact pricing rule it was measured under.
    "ftmo_demo_2026_09_relspread": {
        "server": "FTMO-Demo",
        "provider": "mt5_bridge_ftmo",
        "spec_dir": os.path.join(COSTS_ROOT, "ftmo"),
        "symbol_map": os.path.join(COSTS_ROOT, "ftmo", "symbol-map.json"),
        "spread_scaling": "relative_price_ref",
        "price_ref_history_dir": os.path.join(ROOT, "data", "history", "ftmo"),
        "price_ref_timeframe": "15m",
    },
    "metaquotes_demo_2026_09": {
        "server": "MetaQuotes-Demo",
        "provider": "mt5_bridge",
        "spec_dir": COSTS_ROOT,
        "symbol_map": None,
    },
}


class CostRefused(Exception):
    """A cost calculation that must not produce a number, carrying why (same discipline as risk_model.RiskRefused)."""


def profile_names():
    return sorted(PROFILES)


def _profile(name):
    p = PROFILES.get(name)
    if p is None:
        raise CostRefused(f"no cost profile {name!r} declared in scripts/real_costs.py PROFILES "
                          f"(have {profile_names()}).")
    return p


@functools.lru_cache(maxsize=8)
def _reverse_symbol_map(symbol_map_path):
    """(canonical -> MT5 platform name) tuple-of-pairs (hashable, for lru_cache), or () when the profile's
    spec files are already named with the canonical symbol."""
    if symbol_map_path is None:
        return ()
    with open(symbol_map_path, encoding="utf-8") as fh:
        m = json.load(fh)["map"]
    rev = {}
    for mt5_name, canon in m.items():
        rev.setdefault(canon, mt5_name)
    return tuple(sorted(rev.items()))


def _mt5_name(profile_name, canonical_symbol):
    profile = _profile(profile_name)
    rev = dict(_reverse_symbol_map(profile["symbol_map"]))
    return rev.get(canonical_symbol, canonical_symbol)


@functools.lru_cache(maxsize=64)
def _spec_cached(spec_path_):
    with open(spec_path_, encoding="utf-8") as fh:
        return json.load(fh)


def spec_path(profile_name, canonical_symbol):
    profile = _profile(profile_name)
    return os.path.join(profile["spec_dir"], f"symbolspec.{_mt5_name(profile_name, canonical_symbol)}.json")


def spec(profile_name, canonical_symbol):
    """The raw symbolspec dict for `canonical_symbol` under `profile_name`. Refuses (never defaults) when
    this profile has no export for the symbol."""
    path = spec_path(profile_name, canonical_symbol)
    if not os.path.exists(path):
        declared = sorted(dict(_reverse_symbol_map(_profile(profile_name)["symbol_map"])) or ())
        raise CostRefused(f"no cost spec for {canonical_symbol!r} under profile {profile_name!r} ({path}). "
                          f"Declared canonical symbols for this profile: {declared or 'none declared'}. "
                          f"A symbol this profile has no MT5 export for is refused, not priced at a "
                          f"guessed or borrowed cost.")
    return _spec_cached(path)


def tick_size(profile_name, canonical_symbol):
    """The instrument's price tick (MT5 SYMBOL_TRADE_TICK_SIZE, the spec's `tick_size`), as a positive float. Used by
    the planned-risk admission rule (`backtest-methods.planned_risk_refusal`: a stop closer to the entry than one
    tick is not a placeable order). Refuses -- never defaults -- when the spec has no positive `tick_size`."""
    d = spec(profile_name, canonical_symbol)
    tick = d.get("tick_size")
    if not isinstance(tick, (int, float)) or isinstance(tick, bool) or not tick > 0:
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: the spec has no positive `tick_size` "
                          f"(got {tick!r}); the planned-risk rule will not guess a tick.")
    return float(tick)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def profile_snapshot(profile_name, canonical_symbols=()):
    """§10/§11: the profile name plus its source files' sha256, for a run's configuration snapshot -- so a
    later reader can tell exactly which export a reported cost came from, not merely which profile name."""
    profile = _profile(profile_name)
    files = {}
    if profile["symbol_map"]:
        files[os.path.relpath(profile["symbol_map"], ROOT).replace(os.sep, "/")] = _sha256(profile["symbol_map"])
    for sym in canonical_symbols:
        p = spec_path(profile_name, sym)
        if os.path.exists(p):
            files[os.path.relpath(p, ROOT).replace(os.sep, "/")] = _sha256(p)
    out = {"profile": profile_name, "server": profile["server"], "provider": profile["provider"],
           "source_files_sha256": files}
    if profile.get("spread_scaling", ABSOLUTE) == RELATIVE:
        # C2: the relative profile is only reproducible with the price_ref values AND where they came from.
        info = {sym: price_ref_info(profile_name, sym) for sym in sorted(canonical_symbols)}
        out["spread_scaling"] = RELATIVE
        out["price_ref"] = {sym: i["price_ref"] for sym, i in info.items()}
        out["price_ref_provenance"] = info
        out["price_ref_provenance_sha256"] = hashlib.sha256(
            json.dumps(info, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return out


def _parse_z(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


@functools.lru_cache(maxsize=8)
def server_zone(provider):
    """(zone_name, tzinfo) for `provider`, via `mt5_time.server_zone` -- cached so a per-trade cost loop does
    not re-parse providers.json on every call. `mt5_time.server_zone` itself refuses rather than defaulting
    (module docstring), and that refusal propagates through this cache unmodified.

    `provider=None` refuses HERE, as `CostRefused` (code review 2026-09-29, fix round 1): the caller this
    guards is `backtest-methods.py walk()`'s `OPTS["flat_before_rollover"]` -- if that flag is set but
    `OPTS["rollover_provider"]` was left `None` (the two are meant to be set together, `main()` refuses that
    combination at the CLI, but a test or a future caller could still leave them mismatched), letting `None`
    fall through to `mt5_time.server_zone`/`providers.provider` would raise whatever generic exception THOSE
    happen to produce for a `None` id -- an unguided failure a caller has to reverse-engineer, not a named,
    explained refusal."""
    if provider is None:
        raise CostRefused("no rollover provider given (OPTS[\"rollover_provider\"] is None) -- "
                          "flat_before_rollover/crosses_rollover/nights_held all need a provider id "
                          "(e.g. real_costs.PROFILES[<profile>][\"provider\"]) to know whose server clock "
                          "the daily rollover is measured against; refusing rather than guessing one.")
    return _MT.server_zone(provider)


def crosses_rollover(t_close_iso, t_next_close_iso, provider):
    """True when the server-LOCAL calendar date changes between two bar-close instants -- i.e. a server
    midnight (the daily rollover) falls strictly after `t_close_iso` and at/before `t_next_close_iso`, so the
    bar closing at `t_close_iso` is the LAST bar closing before that rollover. DST-safe: compares wall-clock
    dates after `.astimezone(zone)`, the same conversion `mt5_time.py` already gets right for both a real
    IANA zone and FTMO-Demo's `us_dst_dates_fixed_offset` convention (CLAUDE.md §58: one place, not a second
    hand-rolled DST rule)."""
    _, zone = server_zone(provider)
    a = _parse_z(t_close_iso).astimezone(zone)
    b = _parse_z(t_next_close_iso).astimezone(zone)
    return a.date() != b.date()


def nights_held(entry_time_iso, exit_time_iso, provider):
    """Server-local calendar days D such that the rollover FROM D TO D+1 happened while the position was
    open (entry_time <= that midnight < exit_time) -- one swap charge per day returned, in ascending order.
    DST-safe, same zone conversion as `crosses_rollover`."""
    _, zone = server_zone(provider)
    a = _parse_z(entry_time_iso).astimezone(zone)
    b = _parse_z(exit_time_iso).astimezone(zone)
    out = []
    day = a.date()
    while day < b.date():
        out.append(day)
        day = day + datetime.timedelta(days=1)
    return out


def _mql5_dow(date):
    """MQL5 day-of-week (SUNDAY=0..SATURDAY=6) for a `datetime.date` -- Python's own `.weekday()` is
    Monday=0..Sunday=6, so this is the one place the two conventions are reconciled. `symbolspec`'s own
    `swap_rollover3days` is exported in the MQL5 convention (ExportSymbolSpec.mq5)."""
    return (date.weekday() + 1) % 7


#: The hour frame of `recorded_spread_m15.by_utc_hour`. ExportSymbolSpec.mq5 buckets every recorded M15 bar by
#: `TimeToStruct(server_time - offset)`, offset = the server-GMT offset AT EXPORT (`_server_utc_offset_sec_now`), so table
#: bucket h holds SERVER hour (h + offset) mod 24 in every DST regime -- it is NOT the bar's UTC hour (in US standard time
#: the two differ by one hour). "server_table" (erratum 2026-10-04, docs/audits/2026-10-04-cost-hour-erratum.md) prices a
#: leg at its server hour minus that offset; "utc_legacy" reproduces every record priced before the erratum (the leg's own
#: UTC hour). Records carry the frame they were priced in (`cost_r` -> `hour_frame`).
HOUR_FRAMES = ("server_table", "utc_legacy")
HOUR_FRAME = "server_table"


@functools.lru_cache(maxsize=256)
def export_offset_hours(profile_name, canonical_symbol):
    """The spec's server-GMT offset at export, in whole hours. The export stamps it from the terminal clock, so a value
    within 60 s of a whole hour (10799 s) is that hour; anything else refuses (never guessed)."""
    off = spec(profile_name, canonical_symbol).get("_server_utc_offset_sec_now")
    if not isinstance(off, int) or isinstance(off, bool):
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: the spec has no integer "
                          f"_server_utc_offset_sec_now ({off!r}), so its spread table's hour frame is unknown")
    h = round(off / 3600)
    if abs(off - 3600 * h) > 60:
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: _server_utc_offset_sec_now {off} is not "
                          f"within 60 s of a whole hour; refusing to guess the spread table's hour frame")
    return h


def table_hour(profile_name, canonical_symbol, when):
    """The spread-table bucket (0..23) a leg at instant `when` (ISO "...Z" or an aware datetime) is priced at:
    (server hour - export offset) mod 24 under HOUR_FRAME "server_table"; the leg's UTC hour under "utc_legacy"."""
    t = _parse_z(when) if isinstance(when, str) else when
    if t.tzinfo is None:
        raise CostRefused(f"table_hour needs an aware instant, got {when!r}")
    if HOUR_FRAME == "utc_legacy":
        return t.astimezone(datetime.timezone.utc).hour
    if HOUR_FRAME != "server_table":
        raise CostRefused(f"HOUR_FRAME {HOUR_FRAME!r} is not one of {HOUR_FRAMES}")
    _, zone = server_zone(_profile(profile_name)["provider"])
    return (t.astimezone(zone).hour - export_offset_hours(profile_name, canonical_symbol)) % 24


def spread_price(profile_name, canonical_symbol, bucket, stat="median"):
    """(price, note) -- the spread in table bucket `bucket` (0..23; get it from an instant with `table_hour`), from the
    symbol's `recorded_spread_m15.by_utc_hour`, in PRICE units (points * point). `stat` is "median" (default) or "p90"
    (the disclosed stress option). Falls back to the symbol's overall `{stat}_points` -- still a measured
    figure, just a coarser one -- when the hour has no recorded bars (n=0, e.g. the broker's daily break);
    `note` says which happened so a caller/report can disclose the degraded granularity rather than treat
    every hour as equally well-measured."""
    d = spec(profile_name, canonical_symbol)
    point = d["point"]
    rec = d.get("recorded_spread_m15") or {}
    by_hour = {row["h"]: row for row in (rec.get("by_utc_hour") or ())}
    row = by_hour.get(bucket)
    if row is not None and row.get("n", 0) > 0 and row.get(stat, -1) not in (None, -1):
        return row[stat] * point, "hour"
    overall = rec.get(f"{stat}_points")
    if overall is None or overall < 0:
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: no recorded spread ({stat}) for "
                          f"table bucket {bucket} and no overall {stat}_points fallback either -- "
                          f"recorded_spread_m15 is missing or empty in {spec_path(profile_name, canonical_symbol)}.")
    return overall * point, "overall_fallback"


ABSOLUTE, RELATIVE = "absolute", "relative_price_ref"


def spread_scaling(profile_name):
    """"absolute" (every profile that declares nothing: the original behaviour) or "relative_price_ref" (C2)."""
    return _profile(profile_name).get("spread_scaling", ABSOLUTE)


def _server_stamp_to_utc_iso(stamp, provider):
    """A spec's `first_bar_server`/`last_bar_server` ("2022.07.06 08:00", server wall clock, no zone) -> UTC "...Z"."""
    zone_name, zone = server_zone(provider)
    iso = stamp.strip().replace(".", "-", 2).replace(" ", "T")
    utc, _resolved = _MT.to_utc_ordered(iso, zone, zone_name, f"recorded_spread_m15 window {stamp!r}", None)
    return _MT.iso_z(utc)


def price_ref_window(profile_name, canonical_symbol):
    """(first_utc, last_utc) ISO "...Z" bar-open labels of the spreads' recording window, from the spec."""
    rec = spec(profile_name, canonical_symbol).get("recorded_spread_m15") or {}
    a, b = rec.get("first_bar_server"), rec.get("last_bar_server")
    if not a or not b:
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: recorded_spread_m15 has no "
                          f"first_bar_server/last_bar_server window, so price_ref cannot be defined.")
    provider = _profile(profile_name)["provider"]
    return _server_stamp_to_utc_iso(a, provider), _server_stamp_to_utc_iso(b, provider)


def _window_candles(hist_dir, sym, tf, first_utc, last_utc):
    """The candles of `sym`/`tf` under `hist_dir` whose open label is in [first_utc, last_utc]. A split series reads
    ONLY the year parts the window touches (a 500k-bar M15 series is never parsed whole)."""
    path, shape = _HS.resolve(sym, tf, root=hist_dir)
    if shape is None:
        raise CostRefused(f"no {tf} history for {sym!r} under {hist_dir}: price_ref needs the series of the "
                          f"spreads' recording window.")
    if shape == "file":
        cs = _HS.read_at(path, shape)["candles"]
    else:
        with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
            years = sorted(json.load(fh).get("years") or ())
        y0, y1 = int(first_utc[:4]), int(last_utc[:4])
        cs = []
        for y in years:
            if y0 <= int(y) <= y1:
                with gzip.open(os.path.join(path, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
                    cs.extend(json.load(fh)["candles"])
    return [c for c in cs if first_utc <= c["time"] <= last_utc]


@functools.lru_cache(maxsize=64)
def _price_ref_cached(hist_dir, sym, tf, first_utc, last_utc):
    cs = _window_candles(hist_dir, sym, tf, first_utc, last_utc)
    if not cs:
        raise CostRefused(f"{sym!r}: no {tf} bars in the recording window {first_utc}..{last_utc} under {hist_dir}.")
    closes = [float(c["close"]) for c in cs]
    h = hashlib.sha256()
    for c in cs:
        h.update(f"{c['time']}|{float(c['close'])!r}\n".encode())
    ref = float(statistics.median(closes))
    if not ref > 0:
        raise CostRefused(f"{sym!r}: median close over the recording window is {ref} (not a positive price).")
    return {"price_ref": ref, "n_bars": len(cs), "window_utc": [first_utc, last_utc],
            "first_bar": cs[0]["time"], "last_bar": cs[-1]["time"], "timeframe": tf,
            "closes_sha256": h.hexdigest()}


def price_ref_info(profile_name, canonical_symbol):
    """Provenance of `price_ref`: {price_ref, n_bars, window_utc, first_bar, last_bar, timeframe, closes_sha256}.
    Refuses on a profile that scales nothing (an absolute profile has no price_ref)."""
    prof = _profile(profile_name)
    if prof.get("spread_scaling", ABSOLUTE) != RELATIVE:
        raise CostRefused(f"profile {profile_name!r} prices spreads in absolute price units; it has no price_ref.")
    first_utc, last_utc = price_ref_window(profile_name, canonical_symbol)
    return dict(_price_ref_cached(prof["price_ref_history_dir"], canonical_symbol, prof["price_ref_timeframe"],
                                  first_utc, last_utc))


def price_ref(profile_name, canonical_symbol):
    """The median CLOSE of the symbol's M15 bars over exactly the spreads' recording window (cached, deterministic)."""
    return price_ref_info(profile_name, canonical_symbol)["price_ref"]


def spread_scale(profile_name, canonical_symbol, entry):
    """Multiplier applied to the recorded absolute spread: `entry / price_ref` under the relative profile, else None
    (the absolute profile multiplies by nothing, so its numbers are untouched)."""
    if spread_scaling(profile_name) != RELATIVE:
        return None
    return float(entry) / price_ref(profile_name, canonical_symbol)


def swap_price(profile_name, canonical_symbol, side, entry_time_iso, exit_time_iso):
    """(signed_price, nights, note) -- the total swap PRICE MOVEMENT applied to the position across every
    server-local night held (negative = a debit that costs the trade, positive = a credit), tripled on the
    spec's own `swap_rollover3days` day. Only `swap_mode == 1` (SYMBOL_SWAP_MODE_POINTS) is implemented --
    every export recorded so far (data/history/costs/**) is this mode; a future spec in a different mode
    refuses rather than being priced by a formula this module does not implement."""
    d = spec(profile_name, canonical_symbol)
    if d.get("swap_mode") != 1:
        raise CostRefused(f"{canonical_symbol!r} under {profile_name!r}: swap_mode {d.get('swap_mode')!r} "
                          f"is not SYMBOL_SWAP_MODE_POINTS (1); this model implements POINTS swap only.")
    if side not in ("long", "short"):
        raise CostRefused(f"side {side!r} is not 'long' or 'short'.")
    point = d["point"]
    swap_points = d["swap_long"] if side == "long" else d["swap_short"]
    triple_day = d.get("swap_rollover3days")
    provider = _profile(profile_name)["provider"]
    nights = nights_held(entry_time_iso, exit_time_iso, provider)
    total_points = 0.0
    for day in nights:
        mult = 3 if triple_day is not None and _mql5_dow(day) == triple_day else 1
        total_points += swap_points * mult
    return total_points * point, len(nights), "swap_mode_points"


def commission_r(profile_name, canonical_symbol):
    """(0.0, state) -- see the module docstring "COMMISSION IS NEVER GUESSED". `state` is the spec's own
    `commission.status` (e.g. "no_deals"), or UNKNOWN if the spec carries none."""
    d = spec(profile_name, canonical_symbol)
    status = (d.get("commission") or {}).get("status")
    return 0.0, (status or UNKNOWN)


def cost_r(entry, stop, entry_time_iso, exit_time_iso, canonical_symbol, side, profile_name, spread_stat="median"):
    """The real round-turn cost of one trade, in R -- spread (half the entry-hour spread + half the
    exit-hour spread) + swap (per night held) + commission (always 0/UNKNOWN, see `commission_r`).

    Returns a detail dict; `total_R` is what a caller subtracts from gross R, exactly where
    `risk_model.cost_r`'s returned figure is used today (`backtest-methods.py simulate()`)."""
    entry, stop = float(entry), float(stop)
    if entry <= 0:
        raise CostRefused(f"entry {entry} is not a positive price.")
    dist = abs(entry - stop) / entry
    if dist <= 0:
        raise CostRefused("stop distance is zero: entry and stop are the same price.")
    entry_hour = table_hour(profile_name, canonical_symbol, entry_time_iso)
    exit_hour = table_hour(profile_name, canonical_symbol, exit_time_iso)
    spread_entry, entry_note = spread_price(profile_name, canonical_symbol, entry_hour, spread_stat)
    spread_exit, exit_note = spread_price(profile_name, canonical_symbol, exit_hour, spread_stat)
    spread_cost_price = spread_entry / 2 + spread_exit / 2
    scale = spread_scale(profile_name, canonical_symbol, entry)       # None on an absolute profile: untouched
    if scale is not None:
        spread_cost_price = spread_cost_price * scale
    swap_signed, nights, swap_note = swap_price(profile_name, canonical_symbol, side, entry_time_iso, exit_time_iso)
    commission_R, commission_state = commission_r(profile_name, canonical_symbol)
    spread_R = (spread_cost_price / entry) / dist
    swap_R = -(swap_signed / entry) / dist
    out = {"spread_R": spread_R, "swap_R": swap_R, "commission_R": commission_R,
           "total_R": spread_R + swap_R + commission_R,
           "nights_held": nights, "spread_stat": spread_stat, "hour_frame": HOUR_FRAME,
           "spread_entry_note": entry_note, "spread_exit_note": exit_note,
           "swap_note": swap_note, "commission_state": commission_state,
           "profile": profile_name, "symbol": canonical_symbol}
    if scale is not None:
        out["spread_scale"] = scale
    return out


def mean_spread_r(trades, profile_name, spread_stat="median"):
    """{"n": priced trades, "mean_spread_R": float | None} -- the mean SPREAD cost in R over `trades` (dicts with
    symbol, side, entry, stop, entry_time, exit_time), for the per-fold cost report. A COST figure, not a result: it reads
    no outcome. A trade with no valid stop distance is not priced (the planned-risk rule refuses it elsewhere)."""
    vals = []
    for t in trades:
        if not (isinstance(t.get("entry"), (int, float)) and isinstance(t.get("stop"), (int, float))
                and t["entry"] > 0 and t["entry"] != t["stop"]):
            continue
        vals.append(cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"],
                           profile_name, spread_stat=spread_stat)["spread_R"])
    return {"n": len(vals), "mean_spread_R": (sum(vals) / len(vals)) if vals else None}
