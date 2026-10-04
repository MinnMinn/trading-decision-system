#!/usr/bin/env python3
"""Registration guard for the 2026-10-04 research-direction drafts (VC, OIL, CAL): a read runs only from committed code whose
sha256 the SEALED pre-registration lists, and never overwrites an earlier read.

A draft pre-registration ends in "-DRAFT.md". Sealing = the coordinator commits the final text under the name without
"-DRAFT", carrying its tag (e.g. "[VC-P1]"), a line that is exactly "Status: SEALED" (and no line starting "Status: DRAFT"),
and one line per code file, exactly as `manifest_lines` prints them:

    code-sha256 <64 hex> <repo-relative path>

At read time the guard recomputes every listed file's sha256 and refuses on any difference (code edited and committed after
the seal), and refuses when a file the read needs is not listed. While the read runs, `trace_start` records every repository
file the process opens (an audit hook, so modules loaded through importlib.util.spec_from_file_location are seen too);
`require_covered` then refuses to write the result if a repository .py file outside the manifest was executed. Non-Python
files opened outside data/history are recorded with their sha256 (`opened_files`) for reproducibility (CLAUDE.md §46)."""
import hashlib
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


def refuse_overwrite(path):
    if os.path.exists(path):
        raise Refused(f"refused: {path} exists (each read runs once)")
