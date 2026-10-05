#!/usr/bin/env python3
"""Registration guard for the 2026-10-04 research-direction drafts (VC, OIL, CAL): a read runs only from committed code whose
sha256 the SEALED pre-registration lists, and runs once (`require_read_once`: one output name per read, refused when an
output of that read is on disk or was ever committed).

A draft pre-registration ends in "-DRAFT.md". Sealing = the coordinator commits the final text under the name without
"-DRAFT", carrying its tag (e.g. "[VC-P1]"), a line that is exactly "Status: SEALED" (and no line starting "Status: DRAFT"),
and one line per code file, exactly as `manifest_lines` prints them:

    code-sha256 <64 hex> <repo-relative path>

At read time the guard recomputes every listed file's sha256 and refuses on any difference (code edited and committed after
the seal), and refuses when a file the read needs is not listed. While the read runs, `trace_start` records every repository
file the process opens (an audit hook, so modules loaded through importlib.util.spec_from_file_location are seen too);
`require_covered` then refuses to write the result if a repository .py file outside the manifest was executed. Non-Python
files opened outside data/history are recorded with their sha256 (`opened_files`) for reproducibility (CLAUDE.md §46).

Dates and inputs a read must not take from the command line: a forward read starts after the seal instant git records
(`seal_time`, `first_forward_day`), and an earlier read's JSON is used only when its name, commit state, tag and read
match (`require_read_json`)."""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys


class Refused(SystemExit):
    pass


SEALED_LINE = re.compile(r"(?m)^Status: SEALED[ \t]*$")
DRAFT_LINE = re.compile(r"(?m)^Status: DRAFT")
MANIFEST_LINE = re.compile(r"(?m)^code-sha256 ([0-9a-f]{64}) (\S+)[ \t]*$")


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=False)


def require_committed(root, paths):
    """Every path exists, is tracked, and has no uncommitted change."""
    for p in paths:
        full = os.path.join(root, p)
        if not os.path.exists(full):
            raise Refused(f"refused: {p} does not exist")
        if _git(root, "ls-files", "--error-unmatch", p).returncode != 0:
            raise Refused(f"refused: {p} is not tracked by git (commit it before a read)")
        if _git(root, "status", "--porcelain", "--", p).stdout.strip():
            raise Refused(f"refused: {p} has uncommitted changes")


def check_sealed_text(text, prereg, tag):
    """The text of a SEALED pre-registration: carries `tag`, a line exactly 'Status: SEALED', no 'Status: DRAFT' line."""
    if tag not in text:
        raise Refused(f"refused: {prereg} lacks {tag}")
    if DRAFT_LINE.search(text):
        raise Refused(f"refused: {prereg} still has a 'Status: DRAFT' line")
    if not SEALED_LINE.search(text):
        raise Refused(f"refused: {prereg} has no line that is exactly 'Status: SEALED'")
    return text


def require_sealed(root, prereg, tag):
    """The sealed pre-registration's text: not a draft name, tracked and clean, sealed per `check_sealed_text`."""
    if prereg.endswith("-DRAFT.md"):
        raise Refused(f"refused: {prereg} is a draft; seal it under its final name first")
    require_committed(root, [prereg])
    with open(os.path.join(root, prereg), encoding="utf-8") as fh:
        return check_sealed_text(fh.read(), prereg, tag)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest_lines(root, paths):
    """The lines to paste into the pre-registration before sealing (one per file, in the given order)."""
    return [f"code-sha256 {file_sha256(os.path.join(root, p))} {p}" for p in paths]


def manifest(text):
    """{path: sha256} from the sealed text's code-sha256 lines; a path listed twice is refused."""
    out = {}
    for sha, path in MANIFEST_LINE.findall(text):
        if path in out:
            raise Refused(f"refused: {path} is listed twice in the code manifest")
        out[path] = sha
    return out


def require_fingerprint(root, text, paths):
    """Every path in `paths` is listed in the sealed manifest; every listed file exists with exactly the listed sha256.
    Returns the manifest (recorded in the read's meta)."""
    man = manifest(text)
    missing = [p for p in paths if p not in man]
    if missing:
        raise Refused("refused: the sealed code manifest does not list " + ", ".join(missing))
    bad = []
    for p, sha in sorted(man.items()):
        full = os.path.join(root, p)
        got = file_sha256(full) if os.path.exists(full) else None
        if got != sha:
            bad.append(f"{p} ({'absent' if got is None else got[:12]} != sealed {sha[:12]})")
    if bad:
        raise Refused("refused: code changed since the seal: " + "; ".join(bad))
    return man


# ------------------------------------------------------------------------------------------------ what a read executed
_TRACE = {"on": False, "root": None, "seen": set()}
_HOOKED = [False]


def _audit(event, args):
    if event != "open" or not _TRACE["on"] or not args or not isinstance(args[0], (str, os.PathLike)):
        return
    p = os.path.abspath(os.fspath(args[0]))
    if not isinstance(p, str):
        return
    root = _TRACE["root"]
    if p.startswith(root + os.sep):
        _TRACE["seen"].add(os.path.relpath(p, root).replace(os.sep, "/"))


def trace_start(root):
    """Start recording the repository files this process opens (sys.addaudithook; the hook cannot be removed, so it is
    installed once and switched by a flag)."""
    if not _HOOKED[0]:
        sys.addaudithook(_audit)
        _HOOKED[0] = True
    _TRACE.update(on=True, root=os.path.abspath(root), seen=set())


def _source_of(rel):
    """scripts/x/__pycache__/m.cpython-314.pyc (or a temp copy of it) -> scripts/x/m.py; a .py path unchanged; else None."""
    d, f = os.path.split(rel)
    if os.path.basename(d) == "__pycache__" and ".pyc" in f:
        return os.path.join(os.path.dirname(d), f.split(".")[0] + ".py").replace(os.sep, "/")
    return rel if rel.endswith(".py") else None


def executed_code():
    """Repository .py files opened (as source or bytecode) since `trace_start`, tests excluded."""
    out = set()
    for rel in _TRACE["seen"]:
        src = _source_of(rel)
        if src and src.startswith("scripts/") and not src.startswith("scripts/tests/"):
            out.add(src)
    return out


def require_covered(listed):
    """Refuse (before a result is written) when the read executed a repository .py file the manifest does not list."""
    extra = sorted(executed_code() - set(listed))
    if extra:
        raise Refused("refused: the read executed code the sealed manifest does not list: " + ", ".join(extra)
                      + " (add it to the script's CODE, re-print the manifest, re-seal)")


def opened_files(root, skip_prefixes=("data/history/",)):
    """{path: sha256} of every non-Python repository file opened since `trace_start`, except under `skip_prefixes` (the
    dataset snapshot covers market history)."""
    out = {}
    for rel in sorted(_TRACE["seen"]):
        if _source_of(rel) or "__pycache__" in rel or rel.startswith(skip_prefixes):
            continue
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            out[rel] = file_sha256(full)
    return out


def git_head(root):
    r = _git(root, "rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def dataset_snapshot(hist_root, pairs):
    """{"SYM|tf": sha256} via history_store.digest for every (symbol, timeframe) a read loads (CLAUDE.md §10, §46)."""
    import history_store as HS
    return {f"{sym}|{tf}": HS.digest(sym, tf, root=hist_root) for sym, tf in pairs}


def candles_digest(candles):
    """sha256 of the bars a read used, in a canonical form: one line [time, open, high, low, close] per bar, in the given
    order (CLAUDE.md §10, §46: a merged series that no single file holds)."""
    h = hashlib.sha256()
    for b in candles:
        h.update(json.dumps([b["time"], b["open"], b["high"], b["low"], b["close"]], separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def refuse_overwrite(path):
    """Never overwrite an output (dry runs and screens; a read also needs `require_read_once`)."""
    if os.path.exists(path):
        raise Refused(f"refused: {path} exists (each read runs once)")


READ_DIR = "docs/audits"


def read_name(family, read):
    """The one output name a read may write: docs/audits/<YYYY-MM-DD>-edge-<family>-<read>.json (any date)."""
    return re.compile(rf"^{READ_DIR}/\d{{4}}-\d{{2}}-\d{{2}}-edge-{re.escape(family)}-{re.escape(read)}\.json$")


def require_read_once(root, out_rel, family, read):
    """'Each read runs once', beyond one output path (`refuse_overwrite` alone lets a second run write elsewhere):
    1. the output must match `read_name(family, read)`;
    2. no file of that name pattern may exist in the working tree, tracked or not;
    3. none may ever have been committed, on any branch (`git log --all`, deleted files included).
    A first output deleted before any commit escapes (3); (2) refuses a re-run while it is still on disk."""
    pat = read_name(family, read)
    if not pat.match(out_rel):
        raise Refused(f"refused: a {family} {read} read writes {READ_DIR}/<YYYY-MM-DD>-edge-{family}-{read}.json, "
                      f"not {out_rel}")
    d = os.path.join(root, *READ_DIR.split("/"))
    here = sorted(f"{READ_DIR}/{f}" for f in (os.listdir(d) if os.path.isdir(d) else ()) if pat.match(f"{READ_DIR}/{f}"))
    if here:
        raise Refused(f"refused: the {family} {read} read already ran ({', '.join(here)}); each read runs once")
    r = _git(root, "log", "--all", "--format=", "--name-only", "--", READ_DIR)
    if r.returncode != 0:
        raise Refused(f"refused: cannot check the git history for an earlier {family} {read} read ({r.stderr.strip()})")
    hist = sorted({ln.strip() for ln in r.stdout.splitlines() if pat.match(ln.strip())})
    if hist:
        raise Refused(f"refused: the {family} {read} read was committed before ({', '.join(hist)}); each read runs once")


def require_read_json(root, path_rel, family, read, tag):
    """An earlier read's output, checked before any of its numbers is used: the path is that read's one output name
    (`read_name`), it is committed unchanged, and its meta carries `tag` and `read`. Returns the parsed JSON."""
    if not read_name(family, read).match(path_rel):
        raise Refused(f"refused: {path_rel} is not the {family} {read} read's output "
                      f"({READ_DIR}/<YYYY-MM-DD>-edge-{family}-{read}.json)")
    require_committed(root, [path_rel])
    with open(os.path.join(root, path_rel), encoding="utf-8") as fh:
        doc = json.load(fh)
    meta = doc.get("meta") or {}
    if meta.get("tag") != tag or meta.get("read") != read:
        raise Refused(f"refused: {path_rel} carries tag {meta.get('tag')!r} and read {meta.get('read')!r}, "
                      f"not {tag!r} and {read!r}")
    return doc


def seal_time(root, prereg):
    """The committer time of the OLDEST commit that added `prereg` (the sealed text) to this branch's history: the seal
    instant. Taken from git, never from a date typed on the command line (an earlier date would let rows from before the
    seal into a window graded FRESH). A later amendment of the text does not move it."""
    r = _git(root, "log", "--diff-filter=A", "--format=%cI", "--", prereg)
    stamps = [datetime.datetime.fromisoformat(x.strip()) for x in r.stdout.splitlines() if x.strip()]
    if r.returncode != 0 or not stamps:
        raise Refused(f"refused: no commit adds {prereg}; the seal instant is unknown")
    return min(stamps)


def first_forward_day(root, prereg, zone):
    """The first server day (`zone`) of forward data: the day AFTER the server day of the seal commit, so nothing that
    started before the seal counts as forward, not even on the seal's own day."""
    return seal_time(root, prereg).astimezone(zone).date() + datetime.timedelta(days=1)
