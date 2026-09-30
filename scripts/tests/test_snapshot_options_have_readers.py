"""A0b (docs/plans/2026-09-28-methodology-improvement-plan.md §A0b) -- a config-snapshot field that LOOKS like
a live parameter but has no reader on the scan/simulate path is exactly the defect this test guards against.
`ict_target="range"` was recorded on every stability/prop-search run while `scripts/ict-scan.py`'s
`setup_candidate()` ignored it outright (it always targets the -2sigma projection, falling back to the
dealing-range edge); `range_touches` was recorded in `custom_constraints` while no scan()/simulate()/walk()
code path ever read `OPTS["range_touches"]` at any value. Both are corrected in
docs/experiments/prop-search-2026-09-27/ERRATUM-2026-09-28.md; this test is the regression guard so a future
option can be added to a config snapshot without silently repeating the same lie.

The rule enforced: every option name written into `snapshot.backtest_config_snapshot()`'s `custom_constraints`
field, and every `run_params`/`setup` label in `scripts/stability-report.py` / `scripts/snapshot.py` shaped
like an engine option, must EITHER
  (a) be read on the scan/simulate path (scripts/backtest-methods.py: walk/resolve_methods/ict_setups_live/
      _fires_from/scan/scan_for_trader/simulate -- the functions between OPTS being SET and a trade being
      produced), OR
  (b) carry an explicit, non-empty disclosure key in the same source file explaining that it does not gate
      anything (the pattern this task established for `ict_target`, kept only for
      scripts/rank-setups.py system-naming continuity -- see `ict_target_effective` in scripts/snapshot.py).

A field satisfying neither is a dead key masquerading as configuration -- CLAUDE.md §11: "Do not rely on
mutable external configuration for historical reproducibility" applies with equal force to a key that looks
authoritative and is not.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BT_PATH = os.path.join(ROOT, "scripts", "backtest-methods.py")
SNAPSHOT_PATH = os.path.join(ROOT, "scripts", "snapshot.py")
STABILITY_PATH = os.path.join(ROOT, "scripts", "stability-report.py")

# The scan/simulate path: every function an OPTS overlay can actually reach before or while a trade is
# produced. An explicit, named list -- not "the whole file" -- so a read inside main()'s CLI wiring (which
# SETS OPTS, it does not consume it for a decision) cannot count as a "reader" and hide a truly dead key.
# Re-audit this list (grep `^def ` in backtest-methods.py) if the engine's function boundaries change.
# b3-speed re-audit: the per-bar / per-fire bodies of ict_setups_live() and scan() were moved VERBATIM into
# `_ict_ctx` / `_ict_candidate` / `_ict_trade` and `_wy_window` / `_wy_fire` so scripts/scan_many.py can run them per
# overlay; a read that lives there is a read on the scan path, so they are listed with the functions they came from.
_READER_FUNCTIONS = ("walk", "resolve_methods", "ict_setups_live", "_ict_ctx", "_ict_candidate", "_ict_trade",
                     "_fires_from", "_wy_window", "_wy_fire", "scan", "scan_for_trader", "simulate")


def _function_bodies(source, names):
    """Concatenate the named top-level `def ...` bodies from `source`. Crude but sufficient for this file's
    layout: every top-level function starts at column 0 and ends at the next column-0 `def `/`class `."""
    out = []
    for name in names:
        m = re.search(rf"^def {re.escape(name)}\(.*?\n", source, re.MULTILINE)
        if not m:
            raise AssertionError(f"{name!r} is not a top-level `def` in {BT_PATH} anymore -- "
                                 f"_READER_FUNCTIONS needs re-auditing (see this file's module docstring)")
        start = m.end()
        nxt = re.search(r"^(def |class )", source[start:], re.MULTILINE)
        out.append(source[start:start + nxt.start()] if nxt else source[start:])
    return "\n".join(out)


def _has_reader(opts_key, reader_src):
    """True if `reader_src` READS OPTS[key] / OPTS.get(key) -- not if it merely sets or echoes it."""
    return (f'OPTS["{opts_key}"]' in reader_src or f"OPTS['{opts_key}']" in reader_src or
            f'OPTS.get("{opts_key}"' in reader_src or f"OPTS.get('{opts_key}'" in reader_src)


def undisclosed_dead_fields(written, reader_src, disclosed):
    """`written`: option names captured into a snapshot. `disclosed`: the subset carrying an explicit
    companion note (e.g. `ict_target_effective`) that says they are non-functional. Returns the names that are
    BOTH unread on the scan/simulate path AND undisclosed -- the exact shape of the A0b defect."""
    return sorted(k for k in written if not _has_reader(k, reader_src) and k not in disclosed)


class OptionsWrittenIntoASnapshotHaveAReaderOrADisclosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader_src = _function_bodies(open(BT_PATH, encoding="utf-8").read(), _READER_FUNCTIONS)

    def test_todays_custom_constraints_fields_all_have_a_reader(self):
        # scripts/snapshot.py backtest_config_snapshot()'s CONFIG_FIELDS.custom_constraints extraction tuple.
        written = ("types", "htf", "sloped_gate", "st_min", "phase_d")
        dead = undisclosed_dead_fields(written, self.reader_src, disclosed=())
        self.assertEqual(dead, [], f"custom_constraints field(s) with no scan/simulate reader: {dead}")

    # Matches the key/flag actually being WRITTEN (a quoted dict key, a kwarg assignment, or the CLI flag) --
    # not prose mentioning the name, e.g. this file's and A0b's own explanatory comments/docstrings, which use
    # backticks (`range_touches`) rather than Python-string quotes or `=`.
    _WRITTEN_RANGE_TOUCHES = re.compile(r"""['"]range_touches['"]|\brange_touches\s*=|--range-touches""")

    def test_range_touches_is_not_written_into_any_snapshot_anymore(self):
        """A0b: range_touches had no reader at ANY value and is now removed everywhere, not just disclosed --
        there is nothing this key still needs to LABEL (unlike ict_target, no naming depends on it)."""
        snap_src = open(SNAPSHOT_PATH, encoding="utf-8").read()
        self.assertIsNone(self._WRITTEN_RANGE_TOUCHES.search(snap_src),
                          "range_touches has no scan/simulate reader (A0b) and must not be captured into a "
                          "config snapshot again")
        sr_src = open(STABILITY_PATH, encoding="utf-8").read()
        self.assertIsNone(self._WRITTEN_RANGE_TOUCHES.search(sr_src))
        # sanity: the module-level OPTS default dict itself must not carry the key back in either.
        bt_src = open(BT_PATH, encoding="utf-8").read()
        opts_base = re.search(r"^OPTS = dict\(.*?\n.*?\)\n", bt_src, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(opts_base, "scripts/backtest-methods.py's OPTS default dict moved or was renamed; "
                             "re-locate it before trusting this check")
        self.assertIsNone(self._WRITTEN_RANGE_TOUCHES.search(opts_base.group()))

    def test_ict_target_is_disclosed_not_silently_written(self):
        """A0b kept `ict_target` for scripts/rank-setups.py system-naming continuity even though
        scripts/ict-scan.py never reads it -- allowed ONLY because scripts/snapshot.py now says so explicitly,
        next to the value, every time it is written."""
        snap_src = open(SNAPSHOT_PATH, encoding="utf-8").read()
        self.assertIn("ict_target_effective", snap_src,
                     "ict_target has no reader on the scan/simulate path; it must carry a disclosure "
                     "explaining that (or must not be written into a snapshot at all)")
        # the disclosure must sit in the SAME `setup` field as ict_target, not merely exist somewhere in the
        # file -- a stray comment elsewhere would not stop a reader from trusting the field. Bounded by the
        # next sibling CONFIG_FIELDS key (`entry_rules`) rather than brace-matching: the `setup` value itself
        # contains a `{}` literal (`configs or {}`), so a naive `.*?\},` stops on that, not on the field's end.
        start = snap_src.index('"setup":')
        end = snap_src.index('"entry_rules":', start)
        setup_block = snap_src[start:end]
        self.assertIn("ict_target_effective", setup_block)

    def test_it_would_have_caught_the_pre_a0b_fields(self):
        """Fixture of the PRE-fix state (docs/audits/2026-09-28-method-fidelity.md §2.3): `range_touches`
        inside custom_constraints, and `ict_target` present with NO disclosure alongside it -- exactly what
        scripts/snapshot.py / scripts/stability-report.py wrote before A0b. The checker must flag both, which
        is the proof this test is not vacuous."""
        pre_a0b_written = ("types", "range_touches", "htf", "sloped_gate", "st_min", "phase_d", "ict_target")
        dead = undisclosed_dead_fields(pre_a0b_written, self.reader_src, disclosed=())
        self.assertEqual(dead, ["ict_target", "range_touches"])

    def test_a_disclosed_field_is_not_flagged(self):
        """The checker's `disclosed` allowance is not a loophole that swallows everything -- only the named,
        explicitly-disclosed field is exempted; a second, undisclosed dead field next to it still fails."""
        dead = undisclosed_dead_fields(("ict_target", "totally_undeclared_dead_key"), self.reader_src,
                                       disclosed=("ict_target",))
        self.assertEqual(dead, ["totally_undeclared_dead_key"])


if __name__ == "__main__":
    unittest.main()
