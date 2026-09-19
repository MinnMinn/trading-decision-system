"""CLAUDE.md §18 -- what may count toward a Confluence Score, checked rather than described.

    import confluence as C
    C.check(record, instrument="BTCUSDT")   -> [] when the record is conformant, else the reasons

§18 has two halves. The naming half was already satisfied: the repo says Confluence Score everywhere, and the
one `confidence` field is a pre-trade human 1-5 recorded before the outcome is known, not a probability. The
counting half was **not**, and §15 is what exposed it.

`confluence-score.schema.json` defined a dimension's `eligible` as:

    "false if data source for this dimension is MOCK/UNAVAILABLE/STALE, or the dimension wasn't used"

Availability and use -- the preset appears nowhere. `SYSTEM-DESIGN.md` §6 and `.claude/commands/analyze.md`
step 6 said the same thing in the same words. Before 2026-09-18 that was *accidentally* safe: a dimension the
preset did not trade was also not analysed, so it never had a reading to score. §15 removed exactly that
coincidence. Wyckoff is now live-sourced, analysed, and written up every tick under preset `ict` -- so a
DecisionAgent reading that definition would mark it `eligible: true`, and an untraded methodology would enter
both the numerator and the denominator of a score that decides trades.

That is the failure §18 names in two separate sentences: *"Confluence must only include explicitly configured
methodologies"* and *"Do not count unrelated methodology analysis."*

So eligibility is the INTERSECTION of two independent questions, and neither alone is enough:

    eligible  =  the preset engages it (methods.dispatch_plan -> engaged)     <- §18, trading configuration
             AND its data is live and fresh (not MOCK/STALE/UNAVAILABLE)      <- §6/§20, data quality

The first is what §15 made load-bearing. The second is what the schema already had.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M

# §18: "Do not count ... news/event risk as methodology confluence." Event risk is a gate (§24), not a lane,
# and a key by any of these names in `dimensions` means someone scored it as one.
NOT_A_DIMENSION = ("news", "event_risk", "news_event_state", "calendar", "event")


def check(record, instrument=None, engaged=None):
    """Reasons this confluence record violates §18, or [] if it is conformant.

    `engaged` may be passed directly (a backtest replaying a historical configuration); otherwise it is
    resolved from the live registry for `instrument`.
    """
    problems = []
    dims = record.get("dimensions") or {}

    if engaged is None:
        if instrument is None:
            raise ValueError("check() needs either `engaged` or an `instrument` to resolve it from")
        engaged = M.dispatch_plan(instrument)["engaged"]
    engaged = set(engaged)

    scored = {d for d, v in dims.items() if (v or {}).get("eligible")}

    # --- §18: only explicitly configured methodologies may count.
    for d in sorted(scored - engaged):
        why = "is analysed but NOT traded by the active preset" if d in M.ALL_DIMENSIONS \
              else "is not a methodology at all"
        problems.append(
            f"dimension {d!r} is eligible=true but {why}; CLAUDE.md §18 counts only explicitly configured "
            f"methodologies. Analysis scope (§15) is a separate question -- being read does not make a "
            f"lane countable. Engaged: {sorted(engaged) or 'none'}")

    # --- §18: news/event risk is not a methodology.
    for d in sorted(dims):
        if d.lower() in NOT_A_DIMENSION:
            problems.append(f"{d!r} appears as a scored dimension; CLAUDE.md §18/§24: event risk is a gate, "
                            f"not methodology confluence, and must never contribute points")

    # --- The denominator must match what was counted, or the percentage means nothing.
    if "engaged_count" in record and record["engaged_count"] != len(scored):
        problems.append(f"engaged_count is {record['engaged_count']} but {len(scored)} dimension(s) are "
                        f"eligible; raw_pct's denominator (engaged_count x 25) would not match its numerator")

    # --- §19: contradiction tolerance belongs to the active configuration, so it is read from the mode
    # registry rather than hardcoded. A record that declares its mode is held to that mode's limit.
    mode = record.get("methodology_mode")
    unresolved = record.get("unresolved_high_impact_contradictions")
    if mode and unresolved is not None:
        limit = tolerance(mode)
        if limit is not None and unresolved > limit:
            problems.append(
                f"{unresolved} unresolved HIGH-impact contradiction(s) but mode {mode} tolerates at most "
                f"{limit} (docs/architecture/methods.json modes.{mode}.max_unresolved_high_impact); "
                f"CLAUDE.md §19: the active Trading System determines the blocking behaviour, and this "
                f"record trades through its own limit")

    # --- §19: a contradiction from an ANALYSED-but-untraded lane still counts as a penalty, deliberately.
    # This is the asymmetry with §18 and it is not an oversight: a lane may not add points it did not earn
    # the right to add (§18), but disagreement it can see is still information, and suppressing it would be
    # the silent resolution §19 forbids. Stated here so a later tidy-up does not "fix" it.
    #
    # --- A dimension that cannot count must not carry points either: 0 points and eligible=false are the
    # same claim, and a non-zero score on an ineligible lane is how a lane gets counted by a later reader.
    for d, v in sorted(dims.items()):
        if not (v or {}).get("eligible") and (v or {}).get("points"):
            problems.append(f"dimension {d!r} is eligible=false but carries {v['points']} points; an "
                            f"uncounted lane scores 0 (SYSTEM-DESIGN.md §6.1)")

    return problems


def tolerance(mode):
    """How many unresolved HIGH-impact contradictions this mode will still trade through (§19).

    Read from docs/architecture/methods.json. Before 2026-09-18 the rule existed only inside STRICT's own
    note -- "enforced in the DecisionAgent procedure, not this table" -- which is the shape a rule takes
    just before it stops being applied.
    """
    return (M.MODES.get(mode) or {}).get("max_unresolved_high_impact")


def eligible_dimensions(instrument, available):
    """The dimensions that MAY count, given the preset and which lanes have live, fresh data.

    `available` is the set whose data is AVAILABLE (not MOCK/STALE/UNAVAILABLE) -- a runtime fact this module
    does not try to compute. Returns the intersection, which is the whole point: either question alone
    admits a lane §18 or §6 excludes.
    """
    return sorted(set(M.dispatch_plan(instrument)["engaged"]) & set(available))
