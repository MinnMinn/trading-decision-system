"""THE normalized data layer (CLAUDE.md §7): one shape for market data, with its provenance attached.

    import normalized as N
    s = N.load("BTCUSDT", "15m")
    s["provenance"]["canonical_symbol"]   -> 'BTC/USDT'
    s["provenance"]["market_type"]        -> 'SPOT'      (what the DATA is, not what we trade)
    s["provenance"]["quality"]            -> 'AVAILABLE' | 'STALE' | 'MOCK' | 'UNAVAILABLE'
    N.available_time(s["candles"][3], "15m")             -> when candle 3 became knowable

**Provenance is DERIVED, not copied into every file.** §7 lists fifteen fields a data record must carry. The
obvious implementation -- writing all fifteen into every OHLCV file -- was rejected for two reasons. The
writers are a bash script and an MQL5 expert advisor that only recompiles inside MetaTrader, so half the
fields could not be added without the user rebuilding an EA; and more importantly, `provider`, `source_venue`,
`market_type`, `canonical_symbol`, `aggregation_scope` and `underlying_venues` are all facts about the
REGISTRY, not about the file. Copying them into 131 data files would create 131 copies of a fact that
docs/architecture/providers.json already owns -- the precise duplication this repo's single-source rule
exists to prevent. The file keeps its small header; this module joins it to the registries.

**availableTime is computed, not stored.** A completed candle with open time T on timeframe D is knowable at
T+D and not one second earlier. Storing that per row would add a field to every one of 576 rows to restate a
rule; deriving it keeps one rule in one place. This is the function CLAUDE.md §8's
`availableTime <= decisionTime` invariant is built on, which is why it is a named function here rather than
an expression inlined at a call site.

**What this module does NOT do:** it does not gate anything. Producing a quality state is §7; refusing a
decision because of one is §20 and §36. The `quality` vocabulary here is deliberately the four states
docs/architecture/schemas/data-validation-status.schema.json already defines -- PARTIAL / INVALID / UNKNOWN
are §20's work and are not invented early.
"""
import datetime
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import instruments as I
import providers as P
import history_store as _HS   # THE shared reader (single-file or split-gz), CLAUDE.md §58 -- see its own
                               # module docstring for why a second copy of the split logic was rejected.

# automation.py already owns the timeframe vocabulary -- the ladder (TIERS/next_rung) and
# docs/architecture/timeframe-mapping.md are generated from it. Reading the duration from there rather than
# writing a fifth copy: build-artifact.py:59, automation.py:167, event-ledger.py:29 and
# strategy-runner.py:98 each carry their own table today, and scripts/tests/test_normalized.py fails if any
# of them drifts from this one. A wrong duration here is not cosmetic -- available_time() is what CLAUDE.md
# §8's point-in-time invariant is measured against.
_spec = importlib.util.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py"))
_auto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_auto)
TF_MINUTES = dict(_auto.TF_MINUTES)

# Four states, matching schemas/data-validation-status.schema.json. Not extended here on purpose (see docstring).
QUALITY = ("AVAILABLE", "STALE", "MOCK", "UNAVAILABLE")

# CLAUDE.md §10's "preprocessing version": the version of how this layer INTERPRETS a stored series.
# Bump it whenever a change here alters what the same bytes on disk mean -- the availability rule, the quality
# thresholds, the shape of a provenance field. A research snapshot records this number so a later re-run can
# tell "the data changed" from "our reading of the data changed", which are different findings and were
# previously indistinguishable. Do NOT bump it for a comment, a docstring or a new pure accessor.
SNAPSHOT_INPUTS_VERSION = 1

# A series is STALE when its last write is older than this many of its own bars. Project parameter: no source
# gives a number, and it is stated here rather than buried so /improve can tune it (CLAUDE.md §57).
STALE_AFTER_BARS = 3


def _parse(ts):
    """ISO-8601 Z timestamp -> aware datetime. Accepts the trailing-Z spelling every writer in this repo uses."""
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def tf_seconds(timeframe):
    if timeframe not in TF_MINUTES:
        raise ValueError(f"unknown timeframe {timeframe!r}; known: {sorted(TF_MINUTES)}")
    return TF_MINUTES[timeframe] * 60


GRID_TOLERANCE_S = 2   # an exporter's clock jitter, not a market fact: the MT5 EA stamps some bars 1 s either side of the grid


def snap_to_grid(iso, timeframe, tolerance_s=GRID_TOLERANCE_S):
    """`iso` moved onto the timeframe's bar grid when it is within `tolerance_s` of it; unchanged otherwise.

    Found by the 2026-09-18 drill (docs/audits/2026-09-18-e2e-drill.md §4.4): the MT5 export EA writes the same
    1H bar first as `09:00:01Z`, later as `09:00:00Z` (and 250 of 600 15m bars as `:44:59Z`/`:59:59Z`), so
    scripts/feed_health.py saw "the newest bar went backwards" and, correctly, refused the series as INVALID.
    A one-second exporter jitter is not a market fact and must not read as one -- but a bar genuinely off the
    grid by more than the tolerance is left alone, because THAT is a fact the quality gate must still see.
    """
    import datetime as _dt
    secs = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "2H": 7200, "4H": 14400, "1D": 86400, "1W": 604800}.get(timeframe)
    if not secs or not isinstance(iso, str) or not iso.endswith("Z"):
        return iso
    try:
        t = _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return iso
    epoch = int(t.replace(tzinfo=_dt.timezone.utc).timestamp())
    if timeframe == "1W":
        # the weekly grid is anchored on Monday 00:00 UTC (1970-01-01 was a Thursday: +3 days)
        off = (epoch + 3 * 86400) % secs
    else:
        off = epoch % secs
    delta = off if off <= secs // 2 else off - secs
    if delta == 0 or abs(delta) > tolerance_s:
        return iso
    return _dt.datetime.fromtimestamp(epoch - delta, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snap_series(candles, timeframe, tolerance_s=GRID_TOLERANCE_S):
    """A NEW list with every bar's `time` snapped per snap_to_grid(); the input is not mutated."""
    return [dict(c, time=snap_to_grid(c.get("time"), timeframe, tolerance_s)) for c in candles]


def available_time(candle, timeframe):
    """When this candle became knowable: its OPEN time plus one bar.

    The row's `time` is the bar's OPEN. A bar is not complete -- and its high, low and close are not knowable
    -- until one full period later. Reading a bar's close at its open time is the commonest form of
    look-ahead there is, and the one scripts/live_rules.py already guards by index; this gives the same
    invariant a wall-clock form so it can be checked against news, corrections and derived analytics too."""
    return _parse(candle["time"]) + datetime.timedelta(seconds=tf_seconds(timeframe))


def path_for(symbol, timeframe, base=None):
    """The CONVENTIONAL single-file path for this symbol's candles -- unchanged since before the split-gz
    shape existed. `base=None` is the live feed (a small rolling file, never split); `instruments.data_dir()`
    owns that directory mapping. With a `base` (a research-history root), this is a GUESS at the plain-file
    location -- `resolve_path()`/`load()` below are the shape-aware entry points that also check for a
    split-gz directory; use this only when you specifically want the conventional single-file guess (e.g. to
    name where a NEW file would be written)."""
    if base:
        return os.path.join(base, f"ohlcv.{symbol}.{timeframe}.json")
    return os.path.join(ROOT, "data", "live", I.data_dir(symbol), f"ohlcv.{symbol}.{timeframe}.json")


def resolve_path(symbol, timeframe, base=None):
    """(path, shape) -- the REAL on-disk location, `shape` in {'file', 'split'}, or (None, None) if missing.

    Only meaningful for a research-history `base` (data/history, data/history/ftmo, ...): the live feed
    (`base=None`) is always a single rolling file written by the live bridge/fetcher and is never split, so
    it is resolved directly rather than through `history_store` (whose own `HISTORY_ROOT` default is a
    research root, not the live feed, and would be the wrong default here)."""
    if not base:
        p = path_for(symbol, timeframe, base=None)
        return (p, "file") if os.path.exists(p) else (None, None)
    return _HS.resolve(symbol, timeframe, root=base)


def provenance(raw, symbol, timeframe, source_identifier, now=None):
    """The fifteen §7 fields for one loaded series, joined from the file header and the registries."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    market = I.market_of(symbol)
    is_mock = bool(raw.get("_mock"))
    provider = P.by_source_marker(raw.get("_source")) if raw.get("_source") else None

    candles = raw.get("candles") or []
    received = raw.get("last_updated")
    received_dt = _parse(received) if received else None

    if candles:
        first_open, last_open = _parse(candles[0]["time"]), _parse(candles[-1]["time"])
        last_available = available_time(candles[-1], timeframe)
    else:
        first_open = last_open = last_available = None

    # Quality. MOCK outranks everything: a fixture must never read as live however fresh it looks
    # (SYSTEM-DESIGN.md §3's mock-mode integrity rule).
    if is_mock:
        quality = "MOCK"
    elif not candles:
        quality = "UNAVAILABLE"
    elif received_dt and (now - received_dt).total_seconds() > STALE_AFTER_BARS * tf_seconds(timeframe):
        quality = "STALE"
    else:
        quality = "AVAILABLE"

    return {
        # who and where
        "provider": provider,
        "source_venue": P.venue_of(provider) if provider else None,
        "source_identifier": repo_rel(source_identifier, ROOT),
        "aggregation_scope": P.provider(provider)["aggregation_scope"] if provider else None,
        "underlying_venues": list(P.provider(provider)["underlying_venues"]) if provider else [],
        # what
        "symbol": symbol,
        "canonical_symbol": I.canonical(symbol),
        "market": market,
        "market_type": P.data_market_type(provider) if provider else None,
        "timeframe": timeframe,
        # when -- the three times §7 keeps distinct because they answer different questions
        "event_time": last_open.isoformat().replace("+00:00", "Z") if last_open else None,
        "available_time": last_available.isoformat().replace("+00:00", "Z") if last_available else None,
        "received_time": received,
        # how much, and how good
        "data_scope": {"bars": len(candles),
                       "first_open": candles[0]["time"] if candles else None,
                       "last_open": candles[-1]["time"] if candles else None},
        "freshness_seconds": int((now - received_dt).total_seconds()) if received_dt else None,
        "quality": quality,
    }


def load(symbol, timeframe, base=None, now=None):
    """A normalized series: the candles as written, plus the provenance record that says what they are.

    Raises FileNotFoundError when there is no file -- deliberately, rather than returning an UNAVAILABLE
    record with no candles. "The file is missing" and "the file is there and empty" are different facts and a
    caller that cannot tell them apart will eventually treat one as the other.

    Shape-aware since the split-gz format (code review, 2026-09-29): `resolve_path()` finds either a plain
    file or a split-gz directory under `base`, and `history_store.read_at()` parses whichever it is into the
    same dict shape. The `path` recorded in `provenance()`'s `source_identifier` is therefore the REAL
    location (a directory, for a split series) -- not a guess that may not even exist."""
    path, shape = resolve_path(symbol, timeframe, base)
    if shape is None:
        raise FileNotFoundError(path_for(symbol, timeframe, base))
    raw = _HS.read_at(path, shape)
    return {"candles": raw.get("candles") or [],
            "provenance": provenance(raw, symbol, timeframe, path, now=now),
            "raw_header": {k: v for k, v in raw.items() if k != "candles"}}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Normalized data layer: show a series' provenance.")
    ap.add_argument("symbol")
    ap.add_argument("timeframe")
    a = ap.parse_args()
    try:
        s = load(a.symbol, a.timeframe)
    except FileNotFoundError as exc:
        print(f"no series on disk: {exc}", file=sys.stderr)
        sys.exit(2)
    for k, v in s["provenance"].items():
        print(f"{k:20} {json.dumps(v) if isinstance(v, (dict, list)) else v}")
