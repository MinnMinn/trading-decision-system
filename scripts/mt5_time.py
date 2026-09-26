#!/usr/bin/env python3
"""MT5 broker server time -> UTC, with the zone as a read fact. The ONE place this conversion happens.

    python3 scripts/mt5_time.py sync                      # convert every live .server.json that is newer
    python3 scripts/mt5_time.py sync --symbols XAUUSD     # one symbol
    python3 scripts/mt5_time.py sync --dir <bridge dir>   # a different bridge folder (tests, a second terminal)

Two exporters write broker SERVER time with no `Z`, and both are converted here:

* `integrations/mt5/ExportHistory.mq5` -> `history.<SYM>.<TF>.json`, converted by `scripts/import-mt5-history.py`
  (strict: it refuses an ambiguous or nonexistent local time, see `to_utc`).
* `integrations/mt5/ExportOHLCV.mq5` v1.03+ -> `ohlcv.<SYM>.<TF>.server.json`, converted by `sync_live` below into
  the `ohlcv.<SYM>.<TF>.json` shape every reader already consumes (strategy-runner, ict-scan, build-artifact,
  scan-loop, mt5-bridge-check). Audit PAR-5 / ADR 0006.

WHY PYTHON AND NOT THE EA (audit PAR-5, 2026-09-24)
---------------------------------------------------
Up to v1.02 the live EA stamped EVERY bar with today's rounded `TimeCurrent() - TimeGMT()`. An EET broker is
UTC+2 in winter and UTC+3 in summer, so every bar on the other side of a DST change was one hour off the history
file the backtest reads (216 of 596 XAUUSD D1 bars). MQL5 cannot report the offset in force for a past bar; real
tzdata can. And its `last_updated = IsoTime(TimeCurrent())` was TimeGMT() +/- 450 s by construction, so a frozen
quote stream still looked fresh (CLAUDE.md §52). v1.03 exports the symbol's last tick time as `last_quote_server`,
and `last_updated` here is THAT instant in UTC -- so the runner's existing staleness rule fires on a frozen feed.
A weekend therefore reads as STALE, which is correct: there is no live quote to trade from.

THE ZONE HAS ONE SOURCE
-----------------------
`docs/architecture/providers.json mt5_bridge.server_timezone`, and only for the server named in
`mt5_bridge.server`. No default, no flag, no fallback to the export's own offset. A wrong zone is a silent
one-hour error in every bar, which is worse than no data -- no data at least reads as STALE.

DST TRANSITIONS
---------------
* Spring-forward gap (local 03:00-04:00 does not exist): refused on both paths. A server clock running on the
  declared zone cannot produce it, so seeing one means the zone claim is wrong.
* Fall-back hour (local 03:00-04:00 happens twice): the history importer refuses (its documented choice). The
  live converter resolves it deterministically by ORDER, because the bars are already in time order: an
  ambiguous stamp takes the EARLIER instant (fold=0) unless that would not be after the previous bar, in which
  case it is the repeat and takes the later instant (fold=1). A lone ambiguous bar is therefore the earlier
  instant, the bar's true open. The count is recorded in `_dst_ambiguous_resolved`.
"""
import argparse
import datetime
import glob
import json
import os
import sys
import time
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import providers as P        # noqa: E402

BRIDGE_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
ZONE_SOURCE = "docs/architecture/providers.json mt5_bridge.server_timezone"
LIVE_SOURCE = "mt5_bridge_live"
SERVER_SUFFIX = ".server.json"
# How far `last_quote_server` (converted) may sit after the EA's own PC-clock heartbeat before the pair is
# judged impossible. PC clocks drift by seconds, not minutes; a whole hour here means the zone is wrong.
FUTURE_TOLERANCE_SEC = 300
UTC = datetime.timezone.utc


class Refused(Exception):
    """A conversion that must not happen, carrying the reason a human needs to act on."""


def server_zone():
    """(name, ZoneInfo) from the provider registry, or Refused. Never a default."""
    prov = P.provider("mt5_bridge")
    name = prov.get("server_timezone")
    if not name:
        raise Refused(
            "docs/architecture/providers.json mt5_bridge declares no `server_timezone`. The export writes RAW "
            "server time, so without the zone there is nothing to convert it with -- and a default here would "
            "be a guess that reads as a fact in every bar it touches.")
    if "/" not in name:
        raise Refused(f"mt5_bridge.server_timezone is {name!r}. A real IANA zone is Region/City; an "
                      f"abbreviation like 'EET' is a permanent offset with no daylight saving, which is the "
                      f"exact error this conversion exists to prevent.")
    try:
        return name, zoneinfo.ZoneInfo(name)
    except Exception as exc:
        raise Refused(f"mt5_bridge.server_timezone {name!r} is not a zone this system can load ({exc}).")


def check_server(server, where):
    """The declared zone is a claim about ONE server. Any other server's timestamps refuse."""
    declared = P.provider("mt5_bridge").get("server")
    if declared and server != declared:
        raise Refused(
            f"{where}: exported from server {server!r}, but providers.json declares {declared!r} and its "
            f"`server_timezone` is a claim about THAT server only. Applying one broker's zone to another's "
            f"timestamps is a silent one-hour error in every bar.")


def _local(stamp, zone, zone_name, where):
    """Parse a raw server stamp; refuse one that already claims an offset or that does not exist locally.
    Returns (naive, aware_fold0, ambiguous)."""
    if not isinstance(stamp, str) or not stamp:
        raise Refused(f"{where}: missing server timestamp ({stamp!r}).")
    if stamp.endswith("Z") or "+" in stamp:
        raise Refused(
            f"{where}: timestamp {stamp!r} already claims a UTC offset. The exporters write server time with "
            f"NO `Z` precisely so this conversion is made once, here. A file that makes the claim itself came "
            f"from a different exporter and must not be converted a second time.")
    try:
        naive = datetime.datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise Refused(f"{where}: {stamp!r} is not a timestamp ({exc}).")
    local = naive.replace(tzinfo=zone)
    # PEP 495. Both a NONEXISTENT local time (spring-forward gap) and an AMBIGUOUS one (autumn fall-back) have
    # two different `fold` offsets, so the offsets alone cannot tell them apart -- and `utcoffset()` never
    # returns None for a ZoneInfo. The round trip does separate them: a nonexistent time comes back as a
    # DIFFERENT wall clock, an ambiguous one comes back unchanged.
    if local.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive:
        raise Refused(f"{where}: local time {stamp} does not exist in {zone_name} (spring-forward gap).")
    ambiguous = local.utcoffset() != local.replace(fold=1).utcoffset()
    return naive, local, ambiguous


def to_utc(stamp, zone, zone_name, where):
    """STRICT (history import): one server-local timestamp -> aware UTC, refusing both DST edge cases."""
    _, local, ambiguous = _local(stamp, zone, zone_name, where)
    if ambiguous:
        raise Refused(
            f"{where}: local time {stamp} happens twice in {zone_name} (autumn fall-back). This should be "
            f"impossible for a broker whose transition falls on a Sunday with the market closed; the "
            f"assumption is wrong, so stopping is the only honest move.")
    return local.astimezone(UTC)


def to_utc_ordered(stamp, zone, zone_name, where, prev_utc):
    """LIVE: like `to_utc`, but an ambiguous stamp is resolved by order (module docstring). -> (utc, resolved)"""
    _, local, ambiguous = _local(stamp, zone, zone_name, where)
    if not ambiguous:
        return local.astimezone(UTC), False
    first = local.replace(fold=0).astimezone(UTC)
    if prev_utc is None or first > prev_utc:
        return first, True
    return local.replace(fold=1).astimezone(UTC), True


def iso_z(dt):
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------------------------- live export --

def convert_live(raw, zone_name, zone, where="export"):
    """A v1.03 `.server.json` document -> the `ohlcv.<SYM>.<TF>.json` document. Pure; raises Refused."""
    if raw.get("_source") != LIVE_SOURCE:
        raise Refused(f"{where}: `_source` is {raw.get('_source')!r}, not {LIVE_SOURCE!r}.")
    if raw.get("_time_basis") != "server":
        raise Refused(f"{where}: `_time_basis` is {raw.get('_time_basis')!r}, not 'server'. Only a file that "
                      f"declares raw server time is converted; anything else would be converted twice.")
    check_server(raw.get("_server"), where)
    sym, tf = raw.get("symbol"), raw.get("timeframe")
    if not sym or not tf:
        raise Refused(f"{where}: missing symbol/timeframe.")

    out, prev, resolved = [], None, 0
    for i, c in enumerate(raw.get("candles") or []):
        t, amb = to_utc_ordered(c.get("time_server"), zone, zone_name, f"{where} bar {i}", prev)
        if prev is not None and t <= prev:
            raise Refused(f"{where}: bar {i} at {iso_z(t)} is not after the previous bar {iso_z(prev)}.")
        prev = t
        resolved += amb
        row = {"time": iso_z(t)}
        for k in ("open", "high", "low", "close", "volume"):
            row[k] = c.get(k)
        out.append(row)
    if not out:
        raise Refused(f"{where}: the export contains no candles.")

    # Freshness is the last REAL quote, never the EA heartbeat (PAR-5). No quote -> no freshness -> no file.
    lq = raw.get("last_quote_server")
    if not lq:
        raise Refused(f"{where}: no `last_quote_server`; without the last tick time freshness cannot be "
                      f"stated, and a file without it would read as whatever the reader defaults to.")
    last_quote = to_utc_ordered(lq, zone, zone_name, f"{where} last_quote_server", None)[0]
    beat = raw.get("_exported_at_utc")
    if beat:
        try:
            beat_dt = datetime.datetime.fromisoformat(beat.replace("Z", "+00:00"))
        except ValueError:
            beat_dt = None
        if beat_dt is not None and (last_quote - beat_dt).total_seconds() > FUTURE_TOLERANCE_SEC:
            raise Refused(f"{where}: last quote {iso_z(last_quote)} is after the export itself ({beat}). "
                          f"A quote from the future means the declared zone {zone_name} is wrong for this "
                          f"server (CLAUDE.md §8).")

    doc = {
        "symbol": sym,
        "timeframe": tf,
        "candles": out,
        "last_updated": iso_z(last_quote),
        "_source": LIVE_SOURCE,
        "_server": raw.get("_server"),
        "_server_timezone": zone_name,
        "_server_timezone_source": ZONE_SOURCE,
        "_time_basis_converted_from": "server",
        "_last_quote_server": lq,
        "_exported_at_utc": beat,
        "_ea_version": raw.get("_ea_version"),
        "_dst_ambiguous_resolved": resolved,
        "_volume_caveat": raw.get("_volume_caveat")
        or "tick_volume, not real traded volume -- see comment in ExportOHLCV.mq5",
    }
    return doc


def _atomic_write(path, doc, mtime=None, attempts=6):
    """temp file + os.replace, so a reader sees the old file or the new one, never half of one. On Windows a
    replace over a file another process holds open fails transiently; retry briefly, then give up (the next
    call converts again). The output mtime is set to the SOURCE's, so `mtime(json) >= mtime(server.json)`
    means "already converted" and the file's age still means "when the EA last exported"."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    try:
        for n in range(attempts):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if n == attempts - 1:
                    raise
                time.sleep(0.05)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def sync_file(server_path, zone_name=None, zone=None):
    """Convert one `.server.json` if it is newer than its `.json`. Never raises; returns a status dict:
    converted | up_to_date | refused | unreadable | busy. On anything but `converted` the `.json` is untouched."""
    out = server_path[: -len(SERVER_SUFFIX)] + ".json"
    name = os.path.basename(server_path)
    try:
        src_m = os.path.getmtime(server_path)
    except OSError as exc:
        return {"file": name, "status": "unreadable", "why": str(exc)}
    if os.path.exists(out) and os.path.getmtime(out) >= src_m:
        return {"file": name, "status": "up_to_date"}
    try:
        with open(server_path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        # The EA may be mid-write (it writes a temp file and moves it, but an older terminal build or a sync
        # tool may not). Leave the old output alone; the next call tries again.
        return {"file": name, "status": "unreadable", "why": str(exc)[:200]}
    try:
        if zone is None:
            zone_name, zone = server_zone()
        doc = convert_live(raw, zone_name, zone, where=name)
        want = os.path.basename(out)[len("ohlcv."):-len(".json")]
        if want != f"{doc['symbol']}.{doc['timeframe']}":
            raise Refused(f"{name}: carries {doc['symbol']} {doc['timeframe']}, not what its file name says.")
    except Refused as exc:
        return {"file": name, "status": "refused", "why": str(exc)}
    try:
        _atomic_write(out, doc, mtime=src_m)
    except OSError as exc:
        return {"file": name, "status": "busy", "why": str(exc)[:200]}
    return {"file": name, "status": "converted", "last_updated": doc["last_updated"], "bars": len(doc["candles"])}


def sync_live(bridge_dir=None, symbols=None, timeframes=None, log=None):
    """Convert every live `.server.json` in the bridge folder that is newer than its `.json`.

    No `.server.json` (an EA older than v1.03 still attached) = nothing to do: the legacy `.json` it writes is
    left exactly as it is. Never raises -- a refusal leaves the old `.json` in place, which then ages into
    STALE on the reader's own rule, the fail-safe (CLAUDE.md §20, §52). `log(msg)` is called per refusal."""
    bridge_dir = bridge_dir or BRIDGE_DIR
    results = []
    try:
        paths = sorted(glob.glob(os.path.join(bridge_dir, "ohlcv.*" + SERVER_SUFFIX)))
    except OSError:
        return results
    zone_name = zone = None
    for p in paths:
        stem = os.path.basename(p)[len("ohlcv."):-len(SERVER_SUFFIX)]
        sym, _, tf = stem.rpartition(".")
        if symbols and sym not in symbols:
            continue
        if timeframes and tf not in timeframes:
            continue
        if zone is None:
            try:
                zone_name, zone = server_zone()
            except Refused as exc:
                r = {"file": os.path.basename(p), "status": "refused", "why": str(exc)}
                results.append(r)
                if log:
                    log(f"MT5 server-time conversion refused: {r['file']}: {r['why']}")
                continue
        r = sync_file(p, zone_name, zone)
        results.append(r)
        if log and r["status"] in ("refused", "unreadable", "busy"):
            log(f"MT5 server-time conversion {r['status']}: {r['file']}: {r.get('why', '')}"[:400])
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert MT5 live exports from server time to UTC (audit PAR-5).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="convert every ohlcv.<SYM>.<TF>.server.json newer than its .json")
    s.add_argument("--dir", default=None, help="bridge folder (default data/live/mt5-bridge)")
    s.add_argument("--symbols", default="", help="comma-separated symbols (default: all)")
    a = ap.parse_args(argv)
    syms = {x for x in a.symbols.split(",") if x} or None
    res = sync_live(a.dir, symbols=syms)
    bad = [r for r in res if r["status"] == "refused"]
    for r in res:
        line = f"{r['status']:10} {r['file']}" + (f"  {r['why']}" if r.get("why") else "")
        print(line, file=sys.stderr if r["status"] in ("refused", "unreadable", "busy") else sys.stdout)
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
