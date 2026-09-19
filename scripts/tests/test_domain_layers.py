"""CLAUDE.md §3 -- every domain layer is accounted for, and no layer quietly vanishes from the map.

§3 names two flows of layers and forbids collapsing them into a generic "strategy" abstraction. A test cannot
check "are these concepts conceptually distinct". What it CAN check is the thing that actually goes wrong:
a layer stops being mentioned anywhere, and its absence becomes invisible. The Evidence layer, the Account
Profile layer and the Trading System layer all have no artifact in this repo today -- that is a known state,
recorded in SYSTEM-DESIGN.md §17 with the spec section that owns each gap. What must never happen is one of
them dropping off the table, because then "we have no Evidence record type" stops being a tracked gap and
becomes something nobody remembers.

So: parse the layers out of the spec, require a row for each, and require that a row claiming an artifact
cites a path that exists. The second half is the anti-fabrication rule (rules/reduce-hallucinations.md) applied
to an architecture map -- a map naming a module that was deleted is worse than a map with a blank.
"""
import os
import re
import unittest

import spec

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESIGN = os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md")
TABLE_HEAD = "| Layer (CLAUDE.md §3) |"

# A path-looking token inside a table cell: `scripts/foo.py`, `docs/architecture/bar.json`,
# `integrations/mt5/Baz.mq5`. Backticked, because that is how this repo writes a path in prose.
PATH = re.compile(r"`((?:scripts|docs|integrations|knowledge|data|mock|config)/[\w./-]+)`")


def layers():
    """Layer names from BOTH arrow chains in §3, deduplicated, order preserved.

    The chains are written as `Name\\n  ↓\\nName`. Anything that is not a chain line (the prose intro, the
    "Technical flow:" heading, the closing rule) is skipped by requiring the line to sit adjacent to an arrow.
    """
    lines = [l.strip() for l in spec.body(3).splitlines()]
    out = []
    for i, line in enumerate(lines):
        if line != "↓":
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines) and lines[j] and lines[j] != "↓" and lines[j] not in out:
                out.append(lines[j])
    return out


def rows():
    src = open(DESIGN, encoding="utf-8").read()
    table = src[src.index(TABLE_HEAD):]
    table = table[:table.index("\n\n")]
    out = []
    for line in table.splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith(TABLE_HEAD):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3:
            out.append(cells)
    return out


@unittest.skipUnless(spec.available(), "CLAUDE.md (the master spec) is not present in this checkout")
class DomainLayers(unittest.TestCase):

    def test_the_spec_still_has_the_shape_this_test_reads(self):
        """Guard against a vacuous pass: a reformatted §3 would otherwise yield zero layers and every
        assertion below would hold trivially."""
        found = layers()
        self.assertGreaterEqual(len(found), 12, f"CLAUDE.md §3 layer chains did not parse: {found!r}")
        for expected in ("Market", "Evidence", "Trading System", "Execution Provider"):
            self.assertIn(expected, found, f"§3 no longer names {expected!r}; this test's premise changed")

    def test_the_table_parses(self):
        self.assertGreaterEqual(len(rows()), 12, "SYSTEM-DESIGN.md §17 table did not parse")

    def test_every_layer_in_the_spec_has_a_row(self):
        """Matching is substring-and-case-insensitive so one row may serve `Setup` and `Setups`, or
        `Event Risk` and `Event Risk / News`, without the table carrying near-duplicate rows."""
        names = [r[0].lower() for r in rows()]
        missing = [l for l in layers() if not any(l.lower() in n for n in names)]
        self.assertEqual(missing, [], (
            f"CLAUDE.md §3 names domain layers with no row in SYSTEM-DESIGN.md §17: {missing}. Add a row. If "
            f"the layer has no artifact, say NO ARTIFACT and cite the spec section that owns the gap -- an "
            f"untracked missing layer is how 'we have no Evidence record type' stops being a known gap."))

    def test_a_row_claiming_an_artifact_cites_a_path_that_exists(self):
        """A map naming a deleted module reads as evidence that the layer is built."""
        bad = []
        for cells in rows():
            layer, artifact = cells[0], cells[1]
            if artifact in ("", "-", "—"):
                continue
            for path in PATH.findall(artifact):
                if not os.path.exists(os.path.join(ROOT, path)):
                    bad.append(f"layer {layer!r} cites {path}, which does not exist")
        self.assertEqual(bad, [], "§17 artifact map points at missing files:\n  " + "\n  ".join(bad))

    def test_a_layer_with_no_artifact_says_so_and_names_the_owning_section(self):
        """The blank must be loud. An empty artifact cell with a cheerful state column would hide the gap."""
        for cells in rows():
            layer, artifact, state = cells[0], cells[1], cells[2]
            if artifact in ("", "-", "—"):
                self.assertIn("NO ARTIFACT", state.upper(),
                              f"layer {layer!r} has no artifact but its state does not say NO ARTIFACT")
                self.assertRegex(state, r"CLAUDE\.md §\d+",
                                 f"layer {layer!r} has no artifact and names no spec section that owns it")


if __name__ == "__main__":
    unittest.main()
