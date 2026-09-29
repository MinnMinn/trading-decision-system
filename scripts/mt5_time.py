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


class UsDatesFixedOffsetZone(datetime.tzinfo):
    """A synthetic zone: FIXED +standard/+dst offsets (no geography), whose transition INSTANTS are the same
    ones `America/New_York` uses -- i.e. the broker's own clock jumps at the same wall-clock moment the US
    market's DST does, but the magnitude of the jump is whatever this provider measured (EET-sized for
    FTMO-Demo: +02:00/+03:00), not New York's own -05:00/-04:00.

    No real IANA zone does this (every geography-tied zone's DST dates follow its own region), which is why
    `mt5_time.server_zone()` refuses a bare abbreviation -- but a *named convention* is not a guess, it is
    what `docs/audits/2026-09-29-ftmo-server-timezone.md` measured from the data. Reading the transition
    instants off the real `America/New_York` zoneinfo object (rather than hardcoding "2nd Sunday of March")
    means historical US rule changes -- e.g. the 2007 shift -- are inherited correctly instead of silently
    wrong for old bars.
    """

    _NY = zoneinfo.ZoneInfo("America/New_York")
    _ZERO = datetime.timedelta(0)

    def __init__(self, standard, dst):
        self._std = standard
        self._dst = dst

    def _ny_dst_active(self, naive_utc):
        aware = naive_utc.replace(tzinfo=UTC)
        return aware.astimezone(self._NY).dst() != self._ZERO

    def _offsets(self, dt):
        """(offset_if_std_consistent, offset_if_dst_consistent) -- see utcoffset()."""
        naive = dt.replace(tzinfo=None)
        std_is_consistent = not self._ny_dst_active(naive - self._std)
        dst_is_consistent = self._ny_dst_active(naive - self._dst)
        return std_is_consistent, dst_is_consistent

    def utcoffset(self, dt):
        if dt is None:
            return self._std
        std_ok, dst_ok = self._offsets(dt)
        if std_ok and not dst_ok:
            return self._std
        if dst_ok and not std_ok:
            return self._dst
        if not std_ok and not dst_ok:
            # Neither guess is self-consistent -- the spring-forward GAP: this local wall-clock value never
            # happens. Return a value (round-trip check in _local() is what actually refuses this) rather
            # than raising here, so callers that only need SOME offset (e.g. dst()) do not crash.
            return self._std
        # Both guesses are self-consistent -- the autumn AMBIGUOUS hour, repeated once. PEP 495: fold=0 is
        # the FIRST (chronologically earlier) occurrence, which is the one still on the old (DST) rules.
        return self._dst if dt.fold == 0 else self._std

    def dst(self, dt):
        if dt is None:
            return self._ZERO
        return self.utcoffset(dt) - self._std

    def fromutc(self, dt):
        """UTC -> local, called by `aware_utc_dt.astimezone(this_zone)` (Python's default `astimezone()`
        implementation always routes through the TARGET zone's `fromutc()`). Overridden because the base
        `tzinfo.fromutc()` guesses the offset from `dt`'s OWN wall-clock digits treated as local time -- and
        near a transition that is exactly backwards: `dt` here still carries the UTC digits (only its
        `tzinfo` has been swapped to `self`), so the default algorithm's self-consistency check reads the
        WRONG side of the transition for instants up to `dst - std` after the true UTC transition (code
        review 2026-09-29: 2026-03-08 06:00-08:00Z round-tripped one hour late and jumped by TWO hours
        instead of one -- `real_costs.crosses_rollover`/`nights_held`, which convert stored UTC bar times to
        this zone via `.astimezone()`, inherited the error). The correct question is not "what does this
        wall-clock value look like" but "is THIS UTC INSTANT inside NY's DST season" -- answered directly by
        asking the real `America/New_York` zone (whose own transition handling is correct) rather than by
        re-deriving US DST rules a second time (CLAUDE.md §58), then applying THIS zone's own std/dst
        magnitude.

        `fold` MUST be set on the result (fix within the fix, caught by `FromUtcIsExactAcrossDstTransitions`
        in scripts/tests/test_real_costs.py): the UTC instant itself is never ambiguous, but the LOCAL
        wall-clock value this method returns can be -- this zone's own fall-back hour repeats a wall-clock
        label just like a real zone's does (e.g. FTMO's own 08:00-08:59 local happens once under +03:00 and
        again, an hour later in UTC, under +02:00). Without an explicit `fold`, `utcoffset()`/`dst()` called
        on the RESULT (e.g. by `isoformat()`/`strftime()`, or by a second `.astimezone()`) re-derive the
        offset from `_offsets()`'s wall-clock self-consistency check, which is ambiguous on exactly that
        repeated label and silently defaulted to `fold=0` (`self._dst`) -- so a `fromutc()` that had
        correctly computed the STD side still rendered as DST the moment its wall-clock digits were
        re-interpreted. `fold=0` for the DST (earlier) interpretation, `fold=1` for STD (later) --
        matching `utcoffset()`'s own existing convention (`self._dst if dt.fold == 0 else self._std`).

        Does NOT change `utcoffset()`/`dst()`/`classify()` themselves or anything built on them: `_local()`'s
        LOCAL -> UTC path (the MT5 history/live importers) uses `classify()`, never `fromutc()`, and is
        unaffected -- confirmed by `scripts/tests/test_ftmo_history.py` / `test_audit_par5_mt5_time.py`
        still passing byte-for-byte after this change."""
        if not isinstance(dt, datetime.datetime):
            raise TypeError("fromutc() argument must be a datetime")
        if dt.tzinfo is not self:
            raise ValueError("dt.tzinfo is not self")
        aware_utc = dt.replace(tzinfo=UTC)
        dst_active = aware_utc.astimezone(self._NY).dst() != self._ZERO
        result = dt + (self._dst if dst_active else self._std)
        return result.replace(fold=0 if dst_active else 1)

    def tzname(self, dt):
        return f"FTMO-US-DATES({self._std}/{self._dst})"

    def classify(self, naive):
        """(kind, offset) for a naive local wall-clock value, computed DIRECTLY from the std/dst consistency
        test rather than through the generic tzinfo round-trip `_local()` uses for a real zoneinfo zone --
        that round trip goes through the base class's default `fromutc()`, which is not reliable for a
        hand-rolled zone at exactly the edge instants this whole module exists to get right. `kind` is one of
        'normal' (offset is the one, unambiguous answer), 'gap' (offset is None -- this wall-clock value
        never happens), 'ambiguous' (offset is (dst_offset, std_offset), the two answers in fold order)."""
        std_ok, dst_ok = self._offsets(naive)
        if std_ok and not dst_ok:
            return "normal", self._std
        if dst_ok and not std_ok:
            return "normal", self._dst
        if not std_ok and not dst_ok:
            return "gap", None
        return "ambiguous", (self._dst, self._std)   # fold=0 -> dst (first/earlier), fold=1 -> std (second)


def server_zone(provider="mt5_bridge"):
    """(name, tzinfo) from the provider registry, or Refused. Never a default.

    `provider` generalizes this beyond `mt5_bridge` (MetaQuotes-Demo) so a second MT5 server -- e.g.
    `mt5_bridge_ftmo` -- can declare its own zone the same way, without touching the first provider's
    declaration. Two shapes are recognised:
      * `server_timezone`: a real IANA `Region/City` string (unchanged behaviour, the only path before this).
      * `server_timezone_convention`: a named convention this module implements when no real zone applies --
        see `UsDatesFixedOffsetZone` and docs/audits/2026-09-29-ftmo-server-timezone.md.
    Declaring neither, or declaring an unknown convention name, refuses exactly like a missing zone always
    has -- a convention is not a second way to guess.
    """
    prov = P.provider(provider)
    conv = prov.get("server_timezone_convention")
    if conv:
        return _convention_zone(provider, prov, conv)
    name = prov.get("server_timezone")
    if not name:
        raise Refused(
            f"docs/architecture/providers.json {provider} declares no `server_timezone` (and no "
            f"`server_timezone_convention`). The export writes RAW server time, so without the zone there is "
            f"nothing to convert it with -- and a default here would be a guess that reads as a fact in "
            f"every bar it touches.")
    if "/" not in name:
        raise Refused(f"{provider}.server_timezone is {name!r}. A real IANA zone is Region/City; an "
                      f"abbreviation like 'EET' is a permanent offset with no daylight saving, which is the "
                      f"exact error this conversion exists to prevent.")
    try:
        return name, zoneinfo.ZoneInfo(name)
    except Exception as exc:
        raise Refused(f"{provider}.server_timezone {name!r} is not a zone this system can load ({exc}).")


_CONVENTIONS = ("us_dst_dates_fixed_offset",)


def _convention_zone(provider, prov, conv):
    if conv not in _CONVENTIONS:
        raise Refused(f"{provider}.server_timezone_convention is {conv!r}; this module implements "
                      f"{list(_CONVENTIONS)}. An unimplemented convention name is not a fallback to guessing "
                      f"-- either implement it (with measured evidence, docs/audits/) or fix the declaration.")
    std_sec = prov.get("server_utc_offset_standard_sec")
    dst_sec = prov.get("server_utc_offset_dst_sec")
    if std_sec is None or dst_sec is None:
        raise Refused(f"{provider} declares server_timezone_convention {conv!r} but is missing "
                      f"server_utc_offset_standard_sec/server_utc_offset_dst_sec -- the convention names the "
                      f"TRANSITION DATES only; the offset MAGNITUDE is still a separate measured fact.")
    zone = UsDatesFixedOffsetZone(datetime.timedelta(seconds=std_sec), datetime.timedelta(seconds=dst_sec))
    name = f"{provider}:{conv}(std={std_sec}s,dst={dst_sec}s)"
    return name, zone


def check_server(server, where, provider="mt5_bridge"):
    """The declared zone is a claim about ONE server. Any other server's timestamps refuse."""
    declared = P.provider(provider).get("server")
    if declared and server != declared:
        raise Refused(
            f"{where}: exported from server {server!r}, but providers.json declares {declared!r} for "
            f"'{provider}' and its zone is a claim about THAT server only. Applying one broker's zone to "
            f"another's timestamps is a silent one-hour error in every bar.")


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
    if isinstance(zone, UsDatesFixedOffsetZone):
        # `classify()` answers gap/ambiguous/normal DIRECTLY from the std/dst consistency test (see its own
        # docstring) instead of the round-trip below -- that round trip depends on the base `tzinfo.fromutc()`
        # default algorithm being correct for a hand-rolled zone at exactly the edge instants this module
        # exists to get right, and it is not reliably so. zoneinfo.ZoneInfo (the branch below) has no such
        # problem, so this branch does not touch it.
        kind, offset = zone.classify(naive)
        if kind == "gap":
            raise Refused(f"{where}: local time {stamp} does not exist in {zone_name} (spring-forward gap).")
        if kind == "ambiguous":
            return naive, local, True
        return naive, local, False
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
