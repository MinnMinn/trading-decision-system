"""CLAUDE.md §1 PRIORITY -- the never-override list must stay accounted for in the architecture doc.

§1 states two things. The 13-item ordering (Safety -> Convenience) is a preference order for resolving
requirement conflicts; no code can check a preference. The second half is different in kind and is the part
this test exists for:

    Performance must never override:
    - research integrity
    - required decision dependencies
    - ... (four more)

That is a closed list of concerns which may not be traded away for speed. It is checkable in exactly one
useful way at the doc level: SYSTEM-DESIGN.md §1.0 carries one table row per listed concern, naming where the
concern is enforced -- or saying plainly that it is not yet. If the spec grows a seventh concern, or someone
quietly drops a row because it was inconvenient to keep honest, this test fails.

What this test deliberately does NOT do: check that a row's claim is TRUE. "risk controls are enforced at
trading_env.py:63" is verified by scripts/tests/test_min_rr_and_risk.py, not here; test_doc_citations.py
separately proves the cited line still holds the cited anchor. Coverage and truth are different jobs, and a
test that tried to do both would end up asserting neither.

Why coverage alone is worth a test: on 2026-09-17 SYSTEM-DESIGN.md §1 stated a FIVE-item priority order
("capital preservation > decision quality > ...") while CLAUDE.md §1 stated a different THIRTEEN-item order,
and nothing connected them -- so "what wins when X conflicts with Y" had two answers and no tiebreak. §1.0 now
names both orders as answers to different questions; this test keeps the second one from silently losing rows.
"""
import os
import re
import unittest

import spec

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESIGN = os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md")
MARKER = "Performance must never override:"


def design_text():
    with open(DESIGN, encoding="utf-8") as fh:
        return fh.read()


@unittest.skipUnless(spec.available(), "CLAUDE.md (the master spec) is not present in this checkout")
class Priority(unittest.TestCase):

    def test_the_spec_still_has_the_shape_this_test_reads(self):
        """A parse failure must look like a parse failure. Without this, a reformatted §1 would yield an empty
        list and every coverage assertion below would pass vacuously -- the failure mode that made the first
        version of test_doc_citations.py green against eleven known-stale citations."""
        title, body = spec.section(1)
        self.assertEqual(title, "PRIORITY")
        order = spec.numbered_list(body)
        self.assertGreaterEqual(len(order), 2, f"CLAUDE.md §1 numbered order did not parse: {order!r}")
        self.assertEqual(order[0], "Safety", "§1's ordering must still open with Safety")
        self.assertEqual(order[-1], "Convenience", "§1's ordering must still close with Convenience")
        self.assertIn("Performance", order, "§1's ordering must still rank Performance among the items")
        never = spec.bullet_list(spec.after(body, MARKER))
        self.assertGreaterEqual(len(never), 2, f"CLAUDE.md §1 never-override list did not parse: {never!r}")

    def test_every_never_override_concern_has_a_row_in_system_design(self):
        """One row per concern in SYSTEM-DESIGN.md §1.0's table -- present and accounted for, enforced or not."""
        body = spec.body(1)
        never = spec.bullet_list(spec.after(body, MARKER))
        design = design_text()
        table = design[design.index("| Performance may never override |"):]
        table = table[:table.index("\n\n")]
        missing = [c for c in never if c.lower() not in table.lower()]
        self.assertEqual(missing, [], (
            f"CLAUDE.md §1 forbids performance overriding {missing}, and SYSTEM-DESIGN.md §1.0's table has no "
            f"row for them. Add a row naming where each is enforced -- or state plainly that it is not yet "
            f"enforced. Dropping the row is the one thing that is not allowed: it turns an open gap into an "
            f"invisible one."))

    def test_a_row_claiming_enforcement_cites_a_path(self):
        """A row may say NOT YET ENFORCED. What it may not do is claim enforcement with no `path:line` -- that
        is an assertion dressed as evidence (rules/reduce-hallucinations.md)."""
        design = design_text()
        table = design[design.index("| Performance may never override |"):]
        table = table[:table.index("\n\n")]
        rows = [r for r in table.splitlines() if r.startswith("|") and not r.startswith("|---")][2:]
        self.assertTrue(rows, "no data rows parsed out of the §1.0 table")
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            concern, where = cells[0], cells[1]
            if where in ("", "-", "—"):
                self.assertIn("NOT YET ENFORCED", row,
                              f"row {concern!r} names no enforcement point and does not say NOT YET ENFORCED")
            else:
                self.assertTrue(re.search(r"\.(py|sh|json|md):\d+|\.json`|instruments\.json", where),
                                f"row {concern!r} claims enforcement at {where!r} with no citable path")


if __name__ == "__main__":
    unittest.main()
