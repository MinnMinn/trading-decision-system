"""THE shared reader for one OHLCV history series, in WHICHEVER on-disk shape it is stored, and the ONE
place a "history root" is resolved from `BT_HISTORY_ROOT`.

    import history_store as HS
    HS.history_root()                  -> data/history, or BT_HISTORY_ROOT if set (read FRESH, never cached)
    HS.resolve("XAUUSD", "1m")         -> (path, "split") | (path, "file") | (None, None)
    HS.read_doc("XAUUSD", "1m")        -> (doc_dict, path) or (None, None)
    HS.digest("XAUUSD", "1m")          -> sha256 identity covering every byte backing the series
    HS.part_digests("XAUUSD", "1m")    -> [{"year": Y, "sha256": ...}, ...] for a split series, else None

Two on-disk shapes exist:
  * **file**   -- `ohlcv.<SYM>.<TF>.json`, one JSON object, `candles` inline. Every series before 2026-09-29.
  * **split**  -- `ohlcv.<SYM>.<TF>/index.json` + one `<year>.json.gz` per UTC calendar year
                  (scripts/import-mt5-history.py `stream_write_split()`). Used when a series is too large
                  for a single plain-JSON file to live in a public repo (a second provider's M1/M5 CFD
                  history, docs/audits/2026-09-29-ftmo-history-coverage.md).

WHY THIS MODULE EXISTS (code review, 2026-09-29, fix round)
-------------------------------------------------------------
The split shape and `HISTORY_ROOT` were first added directly inside `scripts/backtest-methods.py`. That was
fine for the backtest engine itself, but every OTHER research path that reads history
(`scripts/normalized.py` -> `scripts/snapshot.py`'s dataset snapshot, `scripts/prop-search.py`'s own
provenance snapshot, `scripts/stability-report.py`'s dataset snapshot) either hardcoded `data/history`
directly or went through `normalized.load()`, which only knew the single-file shape. Two concrete failures
followed: an FTMO-only symbol (no MetaQuotes-Demo file at all) raised `FileNotFoundError` from these paths
even though `bt.load()` had it; and for a symbol present under BOTH roots (XAUUSD, XAGUSD), the dataset
snapshot silently recorded MetaQuotes-Demo's provenance (server, source marker, bar range) for bars that
`bt.load()` had actually read from FTMO -- a snapshot that lies about which broker's data a result was
computed from, which is exactly what CLAUDE.md §10 exists to prevent.

The fix is not "teach `normalized.py` its own copy of the split-gz format" -- two readers for one on-disk
shape is precisely the drift risk CLAUDE.md §58 warns about ("duplicated domain rules"). This module is the
ONE reader; `backtest-methods.py`, `normalized.py` (via `snapshot.py` and `prop-search.py`) all import it.
"""
import datetime
import gzip
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def history_root():
    """`BT_HISTORY_ROOT`, or the default `data/history`, read FRESH on every call -- never cached as a module
    constant. `scripts/backtest-methods.py` is loaded fresh (importlib) by every caller that wants a
    particular env state, but `history_store` itself is a PLAIN module name, so `import history_store` after
    the first import in a process returns the SAME cached module object (regular `sys.modules` behaviour) --
    a module-level constant computed once would freeze whatever `BT_HISTORY_ROOT` happened to be at that
    FIRST import, silently ignoring a test's later `os.environ["BT_HISTORY_ROOT"] = ...` before constructing
    a fresh `bt`/`prop-search` instance. A function has no such staleness: every caller either reads it once
    at its OWN fresh-exec top level (`backtest-methods.py`'s `HISTORY_ROOT = _HS.history_root()`, matching
    its pre-refactor behaviour exactly) or calls it live at the point of use (`prop-search.py`'s
    `_has_predevelopment_history`, which takes no `bt` argument and so has no other fresh-per-call anchor)."""
    return os.environ.get("BT_HISTORY_ROOT") or os.path.join(ROOT, "data", "history")


#: Parsed history files, keyed by ("file", path, mtime_ns, size) or ("split", dir, <_split_identity(dir)>).
#: One cache for every reader (backtest-methods.py's load(), normalized.py's load() via snapshot/prop-search)
#: so the same bytes on disk are parsed once, not once per caller.
_LOAD_CACHE = {}


def resolve(sym, tf, root=None):
    """(path, shape) for `root` (default `history_root()`) -- 'file' or 'split' -- or (None, None) if
    neither exists. Does not read any content."""
    root = root if root is not None else history_root()
    p = os.path.join(root, f"ohlcv.{sym}.{tf}.json")
    if os.path.exists(p):
        return p, "file"
    d = os.path.join(root, f"ohlcv.{sym}.{tf}")
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "index.json")):
        return d, "split"
    return None, None


def _read_file(p):
    st = os.stat(p)
    key = ("file", p, st.st_mtime_ns, st.st_size)
    d = _LOAD_CACHE.get(key)
    if d is None:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        _LOAD_CACHE[key] = d
    return d


def _split_identity(d):
    """Sorted (name, mtime_ns, size) for every file inside a split-gz history directory `d` -- the cache key."""
    names = sorted(os.listdir(d))
    return tuple((n, os.stat(os.path.join(d, n)).st_mtime_ns, os.stat(os.path.join(d, n)).st_size)
                 for n in names)


def _read_split(d):
    """`d/index.json` + `d/<year>.json.gz` -> the SAME dict shape a plain `ohlcv.<SYM>.<TF>.json` file parses
    to, so every caller sees one contract regardless of which shape is on disk. Years are concatenated in
    ASCENDING order (`index.json["years"]` is already written ascending by construction; sorted here anyway
    so a hand-edited index cannot silently reorder bars).

    Asserts bars are strictly increasing in time ACROSS part boundaries, not just within one gzip part (code
    review fix, 2026-09-29): each part was validated internally at write time
    (`import-mt5-history.py stream_write_split()`'s own per-bar ordering check), but nothing had previously
    checked the SEAM between two parts -- a corrupted/hand-edited/reordered part file would silently produce
    a series with a time regression at exactly the year boundary, undetected until some downstream indicator
    computed a nonsensical value. Fails loud (ValueError) rather than quietly serving a corrupt sequence."""
    key = ("split", d, _split_identity(d))
    cached = _LOAD_CACHE.get(key)
    if cached is not None:
        return cached
    with open(os.path.join(d, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    candles = []
    prev_t = None
    for year in sorted(index.get("years") or ()):
        part = os.path.join(d, f"{year}.json.gz")
        with gzip.open(part, "rt", encoding="utf-8") as fh:
            year_candles = json.load(fh)["candles"]
        for c in year_candles:
            t = datetime.datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
            if prev_t is not None and t <= prev_t:
                raise ValueError(
                    f"{d}: {year}.json.gz bar at {c['time']} is not after the previous bar "
                    f"{prev_t.isoformat().replace('+00:00', 'Z')} -- a split-gz series must be strictly "
                    f"increasing in time across part boundaries, same as within one part. Corrupt or "
                    f"hand-edited part file; refusing to serve it rather than silently returning a series "
                    f"with a time regression.")
            prev_t = t
        candles.extend(year_candles)
    doc = dict(index)
    doc["candles"] = candles
    _LOAD_CACHE[key] = doc
    return doc


def read_at(path, shape):
    """The doc at an ALREADY-RESOLVED (path, shape) pair -- for a caller that called `resolve()` itself and
    wants to avoid resolving twice."""
    return _read_file(path) if shape == "file" else _read_split(path)


def read_doc(sym, tf, root=None):
    """(doc, path) for `sym`/`tf` under `root` (default `history_root()`), or (None, None) if missing. `doc` is
    the full parsed document: `symbol`, `timeframe`, `candles`, and every provenance header field
    (`_source`, `_server`, `last_updated`, ...) -- identical shape whichever shape was on disk."""
    path, shape = resolve(sym, tf, root=root)
    if shape is None:
        return None, None
    return read_at(path, shape), path


def _file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def digest(sym, tf, root=None):
    """sha256 identity covering every byte backing this series. For a plain file: sha256 of the file's own
    bytes -- IDENTICAL to `scripts/snapshot.py`'s pre-existing `file_digest()` for every series that predates
    the split shape, so no existing single-file snapshot's recorded sha256 changes. For a split directory:
    sha256 over (name, content) for every file inside (`index.json` first, then each `<year>.json.gz` in
    sorted order) -- a rename or reorder of the parts changes the digest, which a bare content-concatenation
    would not have caught. Raises FileNotFoundError (not None) when the series is missing -- a caller wanting
    a snapshot needs to know that as a hard failure, matching `normalized.load()`'s existing contract."""
    path, shape = resolve(sym, tf, root=root)
    if shape is None:
        raise FileNotFoundError(f"no history for {sym} {tf} under {root if root is not None else history_root()}")
    if shape == "file":
        return _file_sha256(path)
    h = hashlib.sha256()
    for name in sorted(os.listdir(path)):
        h.update(name.encode("utf-8") + b"\0")
        h.update(bytes.fromhex(_file_sha256(os.path.join(path, name))))
    return h.hexdigest()


def part_digests(sym, tf, root=None):
    """`[{"year": Y, "sha256": ...}, ...]` for a split series (one entry per gz part, in year order), or
    `None` for a plain-file series (there is only the one file; `digest()` already covers it) or a missing
    series. CLAUDE.md §10 reproducibility: the combined `digest()` proves the WHOLE series is unchanged, but
    naming which YEAR a later discrepancy would live in is only possible with the per-part breakdown."""
    path, shape = resolve(sym, tf, root=root)
    if shape != "split":
        return None
    with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
        years = sorted((json.load(fh).get("years")) or ())
    return [{"year": y, "sha256": _file_sha256(os.path.join(path, f"{y}.json.gz"))} for y in years]
