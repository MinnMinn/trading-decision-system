"""A disk cache for `bt.scan()` results, so one scan is computed ONCE and reused by every consumer.

Why (owner-approved 2026-09-28): the four CFD stability files (accounts none / ftmo / the5ers / pilot) each ran
the SAME 72 scans -- an account only changes the simulation after the scan -- and the four jobs all hit
GitHub's 6 h job limit. The prop search re-scans the same (symbol, tf, config, method) for its single-symbol
and pooled candidates. A scan is a deterministic function of its inputs, so computing it once and replaying
it everywhere changes no number; it only stops the same work being done four times.

Correctness rests on the KEY. An entry is served only when every input that can change `bt.scan()`'s output
matches the one it was computed under:

  * the in-process key the caller already uses (`stability-report._scan_cache_key`: symbol, tf, every
    scan-relevant OPTS key, the bias-reading methods) -- passed in as `scan_key`;
  * `only` -- which runner methods were computed;
  * the point-in-time cutoff (`bt._PIT_CUTOFF`, CLAUDE.md §8) and the bars limit (`bt._BARS_LIMIT`);
  * a digest of EVERY history file of the symbol (`data/history/ohlcv.<SYM>.*.json`) -- all timeframes, because
    the HTF gate loads the symbol's higher timeframes during the scan;
  * a digest of the code and configuration the scan reads: every `scripts/*.py` and every
    `docs/architecture/**/*.json`. Deliberately broad: a narrower list is one more hand-kept list that can go
    stale, and an over-broad digest only costs a recompute, never a wrong answer.

The full key is stored inside the entry and compared on read, so a filename collision or a hand-copied file
can never be served for the wrong key. A mismatch is a miss (recomputed), reported on stderr.

The entry also carries the `(symbol, tf)` loads the scan made, so the consumer can replay `bt.load()` for
them and keep CLAUDE.md §20/§38 data-quality flags identical to a run that scanned in-process (the same
contract `stability-report._worker_scan` already has with its parallel path).

Entries are pickles written by this code only (a local directory, or a GitHub Actions artifact produced by
the same workflow run). Never point `--scan-cache` at a directory from anyone else.
"""
import glob, hashlib, os, pickle, sys

FORMAT = 1   # bump when the entry layout or the key recipe changes; old entries then simply miss

_DIGESTS = {}


def _expand_dirs(paths):
    """Directories pass through as their own FILES, sorted -- a split-gz history series (a second provider's
    large series, scripts/import-mt5-history.py `stream_write_split()`: `ohlcv.<SYM>.<TF>/index.json` +
    `<year>.json.gz` parts) is a DIRECTORY, and a key built from "the directory exists" would not change when
    a part inside it did. Plain files (the default, unchanged, case) pass through untouched."""
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                yield os.path.join(p, name)
        else:
            yield p


def _digest_files(paths, root):
    """sha256 over (relative path, bytes) of `paths`, sorted -- memoised per (path, mtime, size) set."""
    paths = list(_expand_dirs(paths))
    ident = tuple(sorted((os.path.relpath(p, root).replace(os.sep, "/"), os.stat(p).st_mtime_ns, os.stat(p).st_size)
                         for p in paths))
    if ident in _DIGESTS:
        return _DIGESTS[ident]
    h = hashlib.sha256()
    for rel, _m, _s in ident:
        h.update(rel.encode() + b"\0")
        with open(os.path.join(root, rel), "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    _DIGESTS[ident] = h.hexdigest()
    return _DIGESTS[ident]


def code_digest(root):
    paths = glob.glob(os.path.join(root, "scripts", "*.py")) + \
        glob.glob(os.path.join(root, "docs", "architecture", "**", "*.json"), recursive=True)
    return _digest_files(paths, root)


def data_digest(root, sym, history_root=None):
    """`history_root` (default None -> `root/data/history`, unchanged) lets a second provider's history root
    (backtest-methods.HISTORY_ROOT, e.g. data/history/ftmo) be digested the same way -- `full_key()` passes
    it automatically so a caller pointed at the alternate root never gets served a cache entry keyed on the
    default root's files (or vice versa)."""
    base = history_root or os.path.join(root, "data", "history")
    paths = glob.glob(os.path.join(base, f"ohlcv.{sym}.*.json")) + \
        [p for p in glob.glob(os.path.join(base, f"ohlcv.{sym}.*")) if os.path.isdir(p)]
    return _digest_files(paths, root)


def full_key(root, bt, sym, scan_key, only=None):
    return (FORMAT, repr(scan_key), repr(tuple(only) if only is not None else None),
            repr(bt._PIT_CUTOFF), repr(bt._BARS_LIMIT),
            data_digest(root, sym, history_root=getattr(bt, "HISTORY_ROOT", None)), code_digest(root))


def traced_scan(bt, sym, tf, only=None, opts=None):
    """`bt.scan()` in THIS process, returning `(result, loads)` -- `loads` being every (symbol, tf) `bt.load()`
    was first asked for during the scan, in call order (what an entry stores, see the module docstring). Unlike
    `stability-report._worker_scan` nothing is suppressed: this runs where its output belongs."""
    loads, seen, real_load = [], set(), bt.load

    def traced(s, t):
        if (s, t) not in seen:
            seen.add((s, t)); loads.append((s, t))
        return real_load(s, t)

    bt.load = traced
    try:
        return bt.scan(sym, tf, only=only, opts=opts), loads
    finally:
        bt.load = real_load


def cached_scan(disk, root, bt, sym, tf, scan_key, only=None, opts=None):
    """`bt.scan(sym, tf, only=only, opts=opts)` through `disk` (None = no cache, a plain scan). On a hit the
    stored loads are replayed through `bt.load()` so this process's §20/§38 quality state is what an in-process
    scan would have left; on a miss the scan runs here and is stored."""
    if disk is None:
        return bt.scan(sym, tf, only=only, opts=opts)
    key = full_key(root, bt, sym, scan_key, only=only)
    hit = disk.get(key)
    if hit is None:
        result, loads = traced_scan(bt, sym, tf, only=only, opts=opts)
        disk.put(key, result, loads)
        return result
    result, loads = hit
    for s, t in loads:
        bt.load(s, t)
    return result


class ScanCache:
    """`get()` / `put()` over one directory. `hits` / `misses` / `writes` are counted for the run's own log."""

    def __init__(self, directory, root=None):   # `root` unused: keys come from full_key(), which takes its own
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.hits = self.misses = self.writes = 0

    def _path(self, key):
        return os.path.join(self.dir, hashlib.sha256(repr(key).encode()).hexdigest() + ".pkl")

    def get(self, key):
        """(result, loads) for `key`, or None. A stored entry whose key differs is a miss, reported."""
        p = self._path(key)
        if not os.path.exists(p):
            self.misses += 1
            return None
        with open(p, "rb") as fh:
            entry = pickle.load(fh)
        if entry.get("key") != key:
            print(f"scan-cache: {os.path.basename(p)} holds a different key -- ignored, recomputing", file=sys.stderr)
            self.misses += 1
            return None
        self.hits += 1
        return entry["result"], entry["loads"]

    def put(self, key, result, loads):
        p = self._path(key)
        tmp = p + f".tmp{os.getpid()}"
        with open(tmp, "wb") as fh:
            pickle.dump(dict(key=key, result=result, loads=list(loads)), fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, p)   # atomic: a reader never sees half an entry
        self.writes += 1

    def summary(self):
        return f"scan-cache {self.dir}: {self.hits} hit(s), {self.misses} miss(es), {self.writes} written"
