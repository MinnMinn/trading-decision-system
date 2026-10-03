"""Every `scripts/<file>:<line>` citation in docs/ must resolve.

Why this exists: the threat model docs/security/2026-09-11-top5-pilot.md cites its own enforcement points by
line number in ~26 places. On 2026-09-13 a security review verified that ELEVEN of them were already stale --
one cited a line in the (now-deleted) legacy engine that had moved by two lines -- and every one of those sat
inside a CRITICAL/HIGH rule. Then the same day's edits moved them AGAIN while the review was being read.

A stale citation is worse than no citation: it reads as evidence (rules/reduce-hallucinations.md), and a
reviewer who follows it lands on unrelated code and concludes the rule is satisfied.

The user chose 2026-09-13 to renumber rather than re-anchor to symbols. Renumbering alone buys correctness
until the next edit, so this test is the other half of that decision: it turns the next drift into a failing
test instead of a silent lie.

A range check alone is not enough and this file learned that the hard way: the first version asserted only
"the cited line exists", and it PASSED against all eleven known-stale citations, because a citation that
drifted from :63 to :65 still points at a line that exists. So a citation may carry an ANCHOR -- the token the
line is supposed to contain -- written as `path:line (anchor)`. Where an anchor is present it is checked
within +/- ANCHOR_SLACK lines, which is what actually pins prose to code. Citations without an anchor are
range-checked only; that is a weaker promise, kept deliberately so the doc can be tightened rule by rule
rather than all at once.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "docs")

# `foo.py:123`, `foo.py:123-145`, `foo.py:123,145` -- optionally prefixed with scripts/, optionally followed by
# an anchor as its OWN backticked span: `foo.py:123` (`def bar(`).
#
# The anchor is delimited by backticks, not parentheses. The first version of this regex put the anchor between
# `\(` and `\)`, which silently matched nothing at all: a Python anchor almost always contains an unbalanced
# `(` (`def bar(`, `log("entry"`), so every anchored citation failed to parse and the anchor test passed
# vacuously on a deliberately drifted probe. Backticks cannot appear inside a markdown inline-code span, so
# they are the one delimiter that cannot collide with the code being quoted.
#
# The lookbehind refuses a name that is the tail of a LONGER path (2026-10-03): a security review citing the Python stdlib
# (`.../Lib/multiprocessing/connection.py:713`) is not a citation of this repo's scripts and was reported as a missing
# script. A repo citation is a bare name or `scripts/` / `scripts/tests/` + name; every one of those still matches.
CITE = re.compile(r"(?<![\w/.\\-])(?:scripts/(?:tests/)?)?([a-z0-9_-]+\.(?:py|sh)):(\d+(?:[-,]\d+)*)`?"
                  r"(?:\s*\(`([^`\n]{2,60})`\))?")
ANCHOR_SLACK = 3        # lines either side; absorbs a comment added above the anchor without a false alarm

# Docs that are dated records of their own moment, not descriptions of the current tree. Their line numbers
# were true when written and are not maintained; re-pointing them would falsify the record.
HISTORICAL = ("docs/audits/", "docs/prompts/", "docs/plans/", "docs/backtests/")


# Where a cited script name may live. `scripts/` was the only entry until 2026-09-18, which made a citation of
# a TEST unresolvable -- and a test is often the most honest thing a doc can cite: "this invariant is enforced"
# is evidenced by the test that fails when it stops being true, not by the implementation that claims it.
# SYSTEM-DESIGN.md §1.0's never-override table cites `test_live_rules.py:101` for exactly that reason.
# Order matters only for error messages; a basename collision between the two directories would be a repo
# problem of its own, and the first hit wins.
SCRIPT_DIRS = ("scripts", os.path.join("scripts", "tests"))


def _resolve(script):
    """Absolute path of a cited script name, or None. Searching a short list beats hard-coding one directory
    in three separate assertions, which is what let a tests/ citation read as 'file does not exist'."""
    for d in SCRIPT_DIRS:
        p = os.path.join(ROOT, d, script)
        if os.path.exists(p):
            return p
    return None


def _line_count(path):
    with open(path, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def citations():
    """(doc_relpath, script_name, line_no, anchor_or_None) for every citation in a non-historical doc.

    A range `a-b` yields both ends; the anchor, if any, is attached to the FIRST end only -- an anchor names one
    line, and a range's far end is a span boundary, not a second token."""
    for dirpath, _, files in os.walk(DOCS):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            if rel.startswith(HISTORICAL):
                continue
            src = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            for script, lines, anchor in CITE.findall(src):
                for n, part in enumerate(re.split(r"[-,]", lines)):
                    yield rel, script, int(part), (anchor.strip() or None) if n == 0 else None


# ----------------------------------------------------------------- knowledge/ citations (second family)
#
# The family above covers `scripts/<file>.py:<line>` cited FROM docs/. That left the larger half of this
# repo's citations completely unchecked: ~980 references into knowledge/ across 53 live files, in four
# incompatible spellings (full path, a bare two-digit number, a two-digit range, and a one-letter-plus-number
# shorthand whose expansion table existed in exactly one place -- the mapping file's own header). Nothing read a
# knowledge file at runtime, so every one of those was prose, a docstring, a JSON `cite` string or a live
# prompt body -- which is precisely why breaking one broke nothing visible and stayed broken.
#
# It was not hypothetical: knowledge/ict/models.md cited a sibling under a filename that has never existed, in
# five separate places, and it survived until this test was written.
#
# These tests walk the whole tree, not just docs/, because the heaviest consumers are a skill file, three
# scripts and a JSON parameter file.
KNOWN_ROOTS = ("docs", ".claude", "scripts", "integrations", "knowledge")
KNOWN_FILES = ("README.md",)
KNOWLEDGE_EXT = (".md", ".py", ".sh", ".json", ".js", ".mq5", ".txt")

# A knowledge citation is a path to a real file, optionally followed by a section marker the test ignores.
K_CITE = re.compile(r"knowledge/((?:\.[\w.-]+/)?[\w.-]+(?:/[\w.-]+)*\.md)")
# The two retired spellings. They must not come back: a bare number stops resolving the moment a file is
# renamed, and a shorthand pushes the reader to a table in another file to decode a reference.
K_BARE = re.compile(r"knowledge/0\d(?![\w.-]*\.md)")
K_SHORTHAND = re.compile(r"\bk0\d\b")


def _live_files():
    for r in KNOWN_ROOTS:
        for dirpath, dirs, files in os.walk(os.path.join(ROOT, r)):
            dirs[:] = [d for d in dirs if d != ".git"]
            for fn in sorted(files):
                if not fn.endswith(KNOWLEDGE_EXT):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
                if not rel.startswith(HISTORICAL):
                    yield rel
    for fn in KNOWN_FILES:
        if os.path.exists(os.path.join(ROOT, fn)):
            yield fn


def knowledge_citations():
    for rel in _live_files():
        src = open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read()
        for target in K_CITE.findall(src):
            yield rel, target


class KnowledgeCitationsResolve(unittest.TestCase):
    def test_every_knowledge_path_cited_anywhere_live_exists(self):
        bad = sorted({(doc, t) for doc, t in knowledge_citations()
                      if not os.path.exists(os.path.join(ROOT, "knowledge", t))})
        self.assertEqual(bad, [], "citations point at knowledge files that do not exist:\n  "
                                  + "\n  ".join(f"{d} -> knowledge/{t}" for d, t in bad))

    def test_the_retired_spellings_are_gone_from_live_files(self):
        """The bare-number and short-code spellings were both retired on 2026-09-17 (user decision: rewrite
        every reference with a full path). The two regexes above are the only place either form may appear in
        the live tree. Historical docs keep theirs -- see HISTORICAL above."""
        bad = []
        for rel in _live_files():
            # knowledge/INDEX.md is the one exemption, and it is the reason the exemption is safe: it IS the
            # old->new decode table. Audit documents under docs/audits/ and old commit messages still carry the
            # retired forms, so exactly one live file has to keep them resolvable by hand. Banning them there
            # would delete the map instead of the territory.
            if rel == os.path.join("knowledge", "INDEX.md"):
                continue
            src = open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read()
            for n, line in enumerate(src.splitlines(), 1):
                if K_BARE.search(line):
                    bad.append(f"{rel}:{n} uses a bare knowledge/0N number")
                if K_SHORTHAND.search(line):
                    bad.append(f"{rel}:{n} uses the retired k0N shorthand")
        self.assertEqual(bad, [], f"{len(bad)} retired knowledge reference(s):\n  " + "\n  ".join(bad[:40]))

    def test_the_checker_actually_finds_knowledge_citations(self):
        """Same vacuity guard as the scripts family: a regex that matches nothing passes everything."""
        found = list(knowledge_citations())
        self.assertGreater(len(found), 200, f"only {len(found)} knowledge citations found; the regex is wrong")

    def test_every_knowledge_file_is_reachable_from_the_index(self):
        """An unindexed file is an invisible one: the flat layout had no index at all, which is how a
        five-place citation of a non-existent filename survived."""
        index = os.path.join(ROOT, "knowledge", "INDEX.md")
        self.assertTrue(os.path.exists(index), "knowledge/INDEX.md is missing")
        src = open(index, encoding="utf-8").read()
        unlisted = []
        for dirpath, dirs, files in os.walk(os.path.join(ROOT, "knowledge")):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                rel = os.path.relpath(os.path.join(dirpath, fn), os.path.join(ROOT, "knowledge"))
                if fn.endswith(".md") and rel != "INDEX.md" and rel not in src:
                    unlisted.append(rel)
        self.assertEqual(sorted(unlisted), [], f"knowledge files absent from INDEX.md: {sorted(unlisted)}")


class DocCitationsResolve(unittest.TestCase):
    def test_every_cited_script_exists(self):
        missing = sorted({(doc, s) for doc, s, _, _ in citations() if _resolve(s) is None})
        self.assertEqual(missing, [], f"citations point at scripts that do not exist: {missing} "
                                      f"(searched {', '.join(SCRIPT_DIRS)})")

    def test_every_cited_line_is_in_range(self):
        counts, bad = {}, []
        for doc, script, line, _ in citations():
            p = _resolve(script)
            if p is None:
                continue                        # reported by the test above
            counts.setdefault(script, _line_count(p))
            if line > counts[script]:
                bad.append(f"{doc} cites {script}:{line} but that file has {counts[script]} lines")
        self.assertEqual(bad, [], "out-of-range citations:\n  " + "\n  ".join(bad))

    def test_every_anchored_citation_still_points_at_its_anchor(self):
        """The check a range test cannot make. This is the one that would have caught all eleven stale
        citations the 2026-09-13 review found by hand."""
        srcs, bad = {}, []
        for doc, script, line, anchor in citations():
            if not anchor:
                continue
            p = _resolve(script)
            if p is None:
                continue
            srcs.setdefault(script, open(p, encoding="utf-8").read().splitlines())
            lines = srcs[script]
            lo, hi = max(0, line - 1 - ANCHOR_SLACK), min(len(lines), line + ANCHOR_SLACK)
            if not any(anchor in l for l in lines[lo:hi]):
                found = [i + 1 for i, l in enumerate(lines) if anchor in l]
                bad.append(f"{doc} cites {script}:{line} ({anchor}) but that token is at {found or 'nowhere'}")
        self.assertEqual(bad, [], "citations that drifted off their anchor:\n  " + "\n  ".join(bad))

    def test_a_path_inside_another_tree_is_not_a_repo_citation(self):
        hits = CITE.findall("see `C:/Python314/Lib/multiprocessing/connection.py:713-723` and `scripts/tests/test_x.py:5` "
                            "and `automation.py:12` (`def f(`)")
        self.assertEqual([h[0] for h in hits], ["test_x.py", "automation.py"])

    def test_the_checker_actually_finds_citations(self):
        """A regex that matches nothing would make the tests above pass vacuously -- which is exactly how the
        first version of two tests in test_min_rr_and_risk.py passed against the bugs they were written for."""
        found = list(citations())
        self.assertGreater(len(found), 10, f"only {len(found)} citations found; the regex is probably wrong")


if __name__ == "__main__":
    unittest.main()
