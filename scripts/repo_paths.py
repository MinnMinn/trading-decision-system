"""Shared repo-relative-path helper.

`os.path.relpath(p, ROOT)` is what nearly every script in this directory uses to turn an absolute path into
something short enough to print, or to store in a persisted field (`_path`, `source`, `source_identifier`,
`record_path`, ...). It raises `ValueError` on Windows whenever `p` and `ROOT` are on different drives (a
`..`-walk between C:\\ and D:\\ is not expressible) -- and a test's `TMP`/`TEMP` landing on a different drive
from the repo checkout is exactly the ordinary case that trips it, not an edge case. Before this module, every
one of the (dozens of) call sites it replaces assumed same-drive and crashed the whole process on the first
path that was not: `test_experiment.py`, `test_journal.py` and `test_system_ranking.py` all failed this way
under `TMP=D:/...` while the repo lives on `C:`.

`repo_rel(p, root)` never raises: a path inside `root` gets the same relative walk `os.path.relpath` would
have given (what every existing string comparison, docstring and test fixture already expects), rewritten to
forward slashes; a path OUTSIDE `root` -- a different drive, or any other case with no `..`-expressible walk,
or simply a path that is not actually under `root` at all -- gets its absolute path back, also with forward
slashes rather than `os.sep`, so the shape of the output does not change based on whether the path happened to
resolve inside or outside the tree.

The forward-slash rewrite is deliberate, not incidental: it is what lets the (POSIX-authored) call sites this
replaces keep comparing their result against string literals like `"docs/architecture/..."` without a
platform branch, on Windows exactly as they always did on macOS/Linux. On Windows, `os.path.relpath` returns
backslashes -- so `repo_rel()`'s output is byte-different from the old `os.path.relpath()` call ONLY on
Windows, and ONLY for callers that persist the result into a written artifact rather than print it or compare
it against a POSIX literal. See the call sites this module replaces for which ones do; none of them write into
a file that is already committed to this repository (the committed `data/history/stability/*.json` rows were
all produced on macOS/Linux, where `os.sep` is already `/`, so this change does not alter their bytes).

`root` is a required parameter, not a hidden default: every caller already computes its own `ROOT` constant
(`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`), and `scripts/policy.py` computes a WALKED
root that is deliberately not the repository root at all (CLAUDE.md §58: no implicit configuration) -- making
`root` explicit means this module cannot be misread as asserting there is only one root concept in the tree.
"""
import os


def repo_rel(p, root):
    """Repo-relative POSIX path when `p` is inside `root`; absolute POSIX path otherwise. Never raises."""
    p = os.path.abspath(p)
    try:
        rel = os.path.relpath(p, root)
    except ValueError:
        # Different drives on Windows: os.path.relpath cannot express any `..`-walk between them at all.
        return p.replace(os.sep, "/")
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):   # not `..x`, a file named so inside root
        # Same drive, but `p` is not under `root` -- a `..`-prefixed path is exactly as unhelpful in a
        # persisted field as a cross-drive one would have been, so both cases get the same absolute fallback.
        return p.replace(os.sep, "/")
    return rel.replace(os.sep, "/")
