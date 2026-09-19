"""Reader for the master specification, `CLAUDE.md`, so a test can assert against the spec's own words.

Why this exists: `CLAUDE.md` is the single source of truth for what this system must be (its own §0), and
several of its sections state lists that the architecture doc, the schemas and the code are supposed to
honour. Before this module those lists were re-typed into whichever file needed them, which is the exact
drift `docs/architecture/SYSTEM-DESIGN.md` §1 already fights for the instrument allowlist and the method
registry -- a copy of a rule goes stale silently, and a stale copy reads as evidence
(`rules/reduce-hallucinations.md`).

So: tests parse the spec, they do not restate it. A test that says "the never-override list has six items and
here they are" is a second copy; a test that says "every item the spec lists must appear in this table" keeps
working when the spec gains a seventh.

Section shape in CLAUDE.md -- a line of exactly 60 '=' characters, the heading, another 60 '=' line:

    ============================================================
    1. PRIORITY
    ============================================================

`section(1)` returns everything between that heading's closing rule and the next section's opening rule.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "CLAUDE.md")

RULE = "=" * 60
# "1. PRIORITY", "0.1 ADAPTIVE ORCHESTRATION" -- the number may carry a sub-part, the title is free text.
HEADING = re.compile(r"^(\d+(?:\.\d+)?)\.?\s+(\S.*)$")


def available():
    """CLAUDE.md is the user's spec file and is not always committed to the repo. A test that needs it should
    skip -- not fail -- when it is absent, and say so, rather than turning a fresh clone red for a reason that
    has nothing to do with the change under test."""
    return os.path.exists(PATH)


def _sections():
    with open(PATH, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    marks = []                                  # (number, title, first body line index)
    for i in range(len(lines) - 2):
        if lines[i].strip() == RULE and lines[i + 2].strip() == RULE:
            m = HEADING.match(lines[i + 1].strip())
            if m:
                marks.append((m.group(1), m.group(2), i + 3))
    out = {}
    for j, (num, title, start) in enumerate(marks):
        # A section ends where the NEXT section's opening rule begins, which is 3 lines above its body.
        end = marks[j + 1][2] - 3 if j + 1 < len(marks) else len(lines)
        out[num] = (title, "\n".join(lines[start:end]).strip())
    return out


def section(number):
    """(title, body) for a section number written as the spec writes it: "1", "35", "0.2"."""
    return _sections()[str(number)]


def body(number):
    return section(number)[1]


def numbered_list(text):
    """['Safety', 'Research Integrity', ...] from "1. Safety\\n2. Research Integrity". Order is the spec's."""
    return [m.group(1).strip() for m in re.finditer(r"^\s*\d+\.\s+(\S.*)$", text, re.M)]


def bullet_list(text):
    """['research integrity', ...] from "- research integrity". Plain '-' bullets only."""
    return [m.group(1).strip() for m in re.finditer(r"^\s*-\s+(\S.*)$", text, re.M)]


def after(text, marker):
    """The remainder of `text` following the first line that equals `marker` -- how a section's second list is
    separated from its first without depending on blank-line counts."""
    for i, line in enumerate(text.splitlines()):
        if line.strip() == marker:
            return "\n".join(text.splitlines()[i + 1:])
    raise AssertionError(f"CLAUDE.md: expected a line reading {marker!r}")
