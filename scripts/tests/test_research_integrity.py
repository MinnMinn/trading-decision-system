"""CLAUDE.md §9 -- the eleven biases must each be accounted for, and "unknown" must stay a valid state.

§9 names eleven biases. Two were guarded. The failure mode this file exists to prevent is not "a bias is
unguarded" -- nine of them are, openly, and each row names the section that owns closing it. It is the
quieter one: "we protect against look-ahead" was true, and was being read as "we protect against bias".

So the register in SYSTEM-DESIGN.md §22 must keep one row per bias §9 lists, driven off the spec's own
bullets, and a row that claims a guard must cite a path. Removing a row -- which is what happens when a gap
becomes inconvenient -- fails the build.

The second half pins §9's closing lines, which are the part this repo already does well. `unknown` is a
first-class value that is SILENT rather than dissenting, and the live pilot refuses an order when the
higher-timeframe read is unknown rather than treating absence as permission. Those behaviours are easy to
"simplify" into a confident default by someone who has not read why they exist.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import spec

DESIGN = os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md")
HEAD = "| Bias (CLAUDE.md §9) | Guard here | State |"
PATH = re.compile(r"`((?:scripts|docs|integrations|knowledge|data|mock|config)/[\w./-]+)")


def design():
    with open(DESIGN, encoding="utf-8") as fh:
        return fh.read()


def rows():
    src = design()
    table = src[src.index(HEAD):]
    table = table[:table.index("\n\n")]
    out = []
    for line in table.splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith(HEAD):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3:
            out.append(cells)
    return out


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class BiasRegister(unittest.TestCase):

    def test_the_spec_still_lists_eleven_biases(self):
        """Guard against a vacuous pass: a reformatted §9 would yield an empty list and every check below
        would hold trivially."""
        listed = spec.bullet_list(spec.body(9))
        self.assertEqual(len(listed), 11, f"§9's bias list changed shape: {listed}")
        self.assertIn("look-ahead bias", listed)
        self.assertIn("accidental OOS exposure", listed)

    def test_every_bias_the_spec_names_has_a_row(self):
        names = [r[0].lower() for r in rows()]
        missing = [b for b in spec.bullet_list(spec.body(9)) if b.lower() not in names]
        self.assertEqual(missing, [], (
            f"CLAUDE.md §9 names biases with no row in SYSTEM-DESIGN.md §22: {missing}. Add a row. If nothing "
            f"guards it, say NOT GUARDED and name the section that owns closing it -- an unlisted bias is one "
            f"nobody is tracking."))

    def test_no_extra_rows_invented(self):
        """The register must mirror the spec, not grow a private list beside it."""
        listed = {b.lower() for b in spec.bullet_list(spec.body(9))}
        extra = [r[0] for r in rows() if r[0].lower() not in listed]
        self.assertEqual(extra, [], f"§22 has rows §9 does not name: {extra}")

    def test_a_row_claiming_a_guard_cites_a_path_that_exists(self):
        """An uncited guard is an assertion dressed as evidence (rules/reduce-hallucinations.md)."""
        bad = []
        for cells in rows():
            bias, guard = cells[0], cells[1]
            if guard in ("", "-", "—"):
                continue
            paths = PATH.findall(guard)
            if not paths:
                bad.append(f"{bias!r} claims a guard with no citable path: {guard[:60]}")
            for rel in paths:
                if not os.path.exists(os.path.join(ROOT, rel)):
                    bad.append(f"{bias!r} cites {rel}, which does not exist")
        self.assertEqual(bad, [], "§22 guard claims:\n  " + "\n  ".join(bad))

    def test_an_unguarded_bias_says_so_and_names_its_owner(self):
        for cells in rows():
            bias, guard, state = cells[0], cells[1], cells[2]
            if guard in ("", "-", "—"):
                self.assertIn("NOT GUARDED", state.upper(),
                              f"{bias!r} has no guard but its state does not say NOT GUARDED")
                self.assertRegex(state, r"§\d+", f"{bias!r} is unguarded and names no owning section")

    def test_the_guarded_set_is_the_snapshot_and_changing_it_is_deliberate(self):
        """A snapshot with a purpose: if this changes, either real work landed (update it deliberately) or a
        row was softened. Both deserve a human reading the diff.

        Updated 2026-09-18 by the final full-system pass, which found the register STALE in the safe
        direction -- five rows still said NOT GUARDED for things §38-§45 had since built, so the register was
        understating the repository. Understating is the better failure and is still a failure: a register
        nobody trusts is not read.
        """
        guarded = sorted(r[0] for r in rows() if r[2].upper().startswith(("**GUARDED", "**HALF GUARDED")))
        self.assertEqual(guarded, sorted(["look-ahead bias", "data leakage", "future news revisions",
                                          "future calendar information", "accidental OOS exposure"]),
                         f"the set of fully-guarded biases changed: {guarded}")

    def test_the_still_unguarded_ones_are_named_and_owned(self):
        # Survivorship is structural and stays open; the register must keep saying so rather than quietly
        # dropping the row when it becomes inconvenient.
        unguarded = [r[0] for r in rows() if "NOT GUARDED" in r[2].upper()]
        self.assertIn("survivorship bias", unguarded)


class UnknownIsAValidState(unittest.TestCase):
    """§9's closing lines, in their enforceable form."""

    def test_unknown_is_a_first_class_bias_value(self):
        import htf_context
        self.assertEqual(htf_context.ict_bias({"last": 100.0})[0], "unknown",
                         "a read with no evidence must be unknown, not a direction")

    def test_unknown_is_silent_not_dissenting(self):
        """The distinction that makes `unknown` safe: no data neither votes nor blocks, so a single engaged
        method still stands alone rather than being cancelled by an absent one."""
        import htf_context
        src = open(os.path.join(ROOT, "scripts", "htf_context.py"), encoding="utf-8").read()
        self.assertIn("SILENT", src, "the unknown-is-silent rule lost its explanation")

    def test_the_pilot_refuses_an_order_when_the_htf_read_is_unknown(self):
        """Unknown refuses, not just disagreement -- WA p95-96's rule, and the repo's strongest §62 behaviour.
        Asserted against the source because constructing a full tick here would test the harness, not the
        rule; scripts/tests/test_strategy_runner.py exercises the behaviour itself."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn('sig["htf_pass"] is not True', src,
                      "the htf gate no longer refuses on a non-True (unknown) read")

    def test_too_little_history_is_not_rankable(self):
        """'Do not force causal explanations where evidence is insufficient', enforced: a rule with under 90
        days or under 30 trades is refused selection rather than ranked on thin evidence."""
        import importlib.util
        s = importlib.util.spec_from_file_location("rs", os.path.join(ROOT, "scripts", "rank-setups.py"))
        rs = importlib.util.module_from_spec(s); s.loader.exec_module(rs)
        self.assertGreaterEqual(rs.MIN_WINDOW_DAYS, 90)
        row = {"first": "2026-08-01", "last": "2026-09-11", "w1y": {}, "ruin": None, "ann": 5.0}
        self.assertFalse(rs.solvent(row), "a 41-day row must not be selectable")

    def test_an_unparseable_date_fails_closed(self):
        import importlib.util
        s = importlib.util.spec_from_file_location("rs", os.path.join(ROOT, "scripts", "rank-setups.py"))
        rs = importlib.util.module_from_spec(s); s.loader.exec_module(rs)
        self.assertFalse(rs.solvent({"first": "not-a-date", "last": "also-not", "ruin": None, "ann": 9.9}))


class SelectionPressureIsReal(unittest.TestCase):
    """The register's selection-bias row states numbers. These keep the numbers honest."""

    def test_the_candidate_pool_is_much_larger_than_the_selection(self):
        import glob
        import json
        total = 0
        for p in glob.glob(os.path.join(ROOT, "data", "history", "stability", "*.json")):
            with open(p, encoding="utf-8") as fh:
                total += len(json.load(fh).get("rows", []))
        if total == 0:
            self.skipTest("no stability rows on disk")
        selection = os.path.join(ROOT, "docs", "architecture", "pilot-top20.json")
        with open(selection, encoding="utf-8") as fh:
            picked = len(json.load(fh).get("setups", []))
        self.assertGreater(total, picked * 5,
                           "the register claims substantial selection pressure; the data no longer shows it")

    def test_the_selection_file_still_records_no_candidate_count(self):
        """A failing-forward test: when §43 adds the count, this test should be DELETED along with the
        register's 'unrecorded' wording. Until then it pins the gap so the claim cannot go stale."""
        import json
        with open(os.path.join(ROOT, "docs", "architecture", "pilot-top20.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        keys = " ".join(k.lower() for k in d)
        for token in ("candidate", "rejected", "considered"):
            self.assertNotIn(token, keys,
                             f"pilot-top20.json now records {token!r} -- §43 landed; update §22's "
                             f"selection-bias row and delete this test")


if __name__ == "__main__":
    unittest.main()
