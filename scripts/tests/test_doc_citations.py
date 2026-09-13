"""Every `scripts/<file>:<line>` citation in docs/ must resolve.

Why this exists: the threat model docs/security/2026-09-11-top5-pilot.md cites its own enforcement points by
line number in ~26 places. On 2026-09-13 a security review verified that ELEVEN of them were already stale --
it cited demo-pilot.py:63 for a call that had moved to :65 -- and every one of those sat inside a
CRITICAL/HIGH rule. Then the same day's edits moved them AGAIN while the review was being read.

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
CITE = re.compile(r"\b(?:scripts/)?([a-z0-9_-]+\.(?:py|sh)):(\d+(?:[-,]\d+)*)`?"
                  r"(?:\s*\(`([^`\n]{2,60})`\))?")
ANCHOR_SLACK = 3        # lines either side; absorbs a comment added above the anchor without a false alarm

# Docs that are dated records of their own moment, not descriptions of the current tree. Their line numbers
# were true when written and are not maintained; re-pointing them would falsify the record.
HISTORICAL = ("docs/audits/", "docs/prompts/", "docs/plans/", "docs/backtests/")


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


class DocCitationsResolve(unittest.TestCase):
    def test_every_cited_script_exists(self):
        missing = sorted({(doc, s) for doc, s, _, _ in citations()
                          if not os.path.exists(os.path.join(ROOT, "scripts", s))})
        self.assertEqual(missing, [], f"citations point at scripts that do not exist: {missing}")

    def test_every_cited_line_is_in_range(self):
        counts, bad = {}, []
        for doc, script, line, _ in citations():
            p = os.path.join(ROOT, "scripts", script)
            if not os.path.exists(p):
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
            p = os.path.join(ROOT, "scripts", script)
            if not os.path.exists(p):
                continue
            srcs.setdefault(script, open(p, encoding="utf-8").read().splitlines())
            lines = srcs[script]
            lo, hi = max(0, line - 1 - ANCHOR_SLACK), min(len(lines), line + ANCHOR_SLACK)
            if not any(anchor in l for l in lines[lo:hi]):
                found = [i + 1 for i, l in enumerate(lines) if anchor in l]
                bad.append(f"{doc} cites {script}:{line} ({anchor}) but that token is at {found or 'nowhere'}")
        self.assertEqual(bad, [], "citations that drifted off their anchor:\n  " + "\n  ".join(bad))

    def test_the_checker_actually_finds_citations(self):
        """A regex that matches nothing would make the tests above pass vacuously -- which is exactly how the
        first version of two tests in test_min_rr_and_risk.py passed against the bugs they were written for."""
        found = list(citations())
        self.assertGreater(len(found), 10, f"only {len(found)} citations found; the regex is probably wrong")


if __name__ == "__main__":
    unittest.main()
