"""Shared source-scanning helper for the tests that ban a token from CODE without banning it from PROSE.

Extracted from scripts/tests/test_one_system.py on 2026-09-13 when a second test file
(scripts/tests/test_min_rr_and_risk.py) needed the same thing. It is here rather than copied because a copy of
this helper is exactly the kind of second source the one-system work exists to remove: if the stripping rule ever
changes, one edit must be enough.

The rule it encodes, learned the hard way FOUR times in one day: a test that bans a token everywhere also bans
the sentence EXPLAINING why the token was removed. It once forced an implementer to edit unrelated docstrings in
htf_context.py just to satisfy a scan, and it made three separate fix commits fail their own new test. Prose may
discuss a deleted thing; code may not resolve it.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def code_lines(rel):
    """Lines of `rel` with comments AND docstrings removed, 1-indexed as (lineno, text).

    `rel` is relative to the repo root. `.py` files lose their module/class/function docstrings via `ast`;
    every file type loses whole-line `#` and `<!--` comments. A trailing comment on a code line is KEPT --
    stripping it would need a real tokenizer per language, and a token that appears only in a trailing comment
    next to live code is close enough to a code claim to be worth flagging.
    """
    src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    skip = set()
    if rel.endswith(".py"):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
               and isinstance(first.value.value, str):
                skip.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if i in skip or line.lstrip().startswith(("#", "<!--")):
            continue
        out.append((i, line))
    return out


def code_text(rel):
    """`code_lines(rel)` joined back into one string, for whole-file substring assertions."""
    return "\n".join(line for _, line in code_lines(rel))
