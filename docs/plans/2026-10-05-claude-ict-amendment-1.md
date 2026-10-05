# Amendment 1 to the Claude discretionary ICT pre-registration (2026-10-05)

**Amends:** `docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md` (commit 7f2b142, cherry-picked as 0a0e87c).
That file is NOT edited. This file states what changes and what does not.

**Made:** 2026-10-05T00:50Z, BEFORE any decision was generated, before the harness was committed and before any model
call of the experiment (the only model calls so far are one-line smoke tests of the isolation, on 2026-10-04, that carry
no price data). Decided by the lead of the session "Challenging the system" and agreed by the pre-registration's reviewer
(session "Khám phá hệ thống FTMO", message of 2026-10-05). The account owner is told and may override before the run.
The owner said "Chạy đi" on 2026-10-05, after being told about the mirror finding (item 1) and the cost.

## 1. What changes (a stricter PASS)

**A fourth PASS condition: the mirror-order test.** For every ORDER arm C places, filled or not, the same order on the
other side is simulated by the same code (same kind, mirrored around the mid price at placement, same stop and target
distances; a market order from its own fill). The statistic is the mean R per order (0 when it did not fill). One-sided
p < 0.05 by 2,000 seeded shuffles of C's direction labels within each instrument (implementation note §4 item 21b).

**PASS now needs all of:** the pre-registered primary test (§6, unchanged); the mirror-order test; C's mean net R > 0;
C beats M on mean net R (with the arm-M rules below). Nothing else about §6 changes. Both p-values are reported whatever
the verdict.

**Why.** The pre-registered primary test shuffles the direction of C's FILLED trades and gives the control the opposite
trade at C's fill instant. For a LIMIT order the fill depends on the direction (a buy limit fills when price falls to
it), so the opposite trade at that instant enters in the direction of the move the limit just faded: a direction-blind
book is not a placebo there. Measured on the bars before the window (2026-03-02 .. 2026-06-30), with seeded random
orders at real killzone opens and a fair coin for the side (so no skill exists), the primary test over-rejects limit
books:

| order kind | instrument | primary test rejects at p<0.05 | mirror test rejects at p<0.05 |
|---|---|---|---|
| market | XAUUSD | 4.3 % | 4.7 % |
| market | US500 | 5.2 % | 4.4 % |
| limit | XAUUSD | 8.4 % (run C); 6.5 % (run B); 6.8 % (run A) | 6.4 % (C); 5.0 % (B); 4.0 % (A) |
| limit | US500 | 7.7 % (run C); 13.1 % (run B); 9.8 % (run A) | 4.1 % (C); 4.9 % (B); 5.3 % (A) |
| stop | XAUUSD | 2.9 % | 4.6 % |
| stop | US500 | 1.8 % | 4.8 % |

Run C (`claude_ict_eval.py calibrate --reps 2000`, all kinds) is the table's main figure; runs A (600 replicates, all
kinds) and B (2,000 replicates, limit only) are listed for limit books because the three runs draw different random
order sets (the calibration's random stream is shared across kinds, so the set depends on which kinds and how many
replicates are run), which moves the limit figure between 6.5 % and 13.1 %. Every draw is above 5 % for limit orders;
the mirror test stays between 4.0 % and 6.7 % in every cell of every run (4.0 % to 6.4 % for limit orders). The raw logs are `docs/experiments/claude-ict/calibration/`. They use
bars before 2026-07-01 only; no bar of the window was read.

Adding a condition can only make PASS harder, never easier. The primary test is kept as written and reported.

## 2. What is fixed by the implementation (choices the pre-registration leaves open)

All are in `docs/plans/2026-10-04-claude-ict-implementation.md` §4. The reviewer accepted these:

- **338 decision points,** not about 325: 68 weekdays x 5 killzones, minus 2 US500 New York PM days with no data
  (2026-07-03 and 2026-09-07).
- **The primary shuffle is within instrument,** stricter than the pre-registration's text (a global shuffle can pass with
  no skill when the instruments differ in drift and direction mix).
- **A new verdict state NOT_PASS:** the primary test passed but another PASS condition failed. The pre-registration names
  no state for it; it is not a PASS.
- **Arm M** is the repo ICT engine's order intents at the pilot's 15m settings, run through the same simulator. A leakage
  probe (cut the future after each signal and detect again) runs inside `evaluate`. If it fails, or M has no filled
  trade, "C beats M" is recorded as "not evaluable" and the verdict is at most "INCOMPLETE (C vs M not evaluable)".
  M is sparse (10 order intents in the three months before the window).
- **Arm T** is reported as written (v3) with one descriptive line for v4 (the demo book since 2026-10-03T18:10Z). It
  does not gate.
- **Time:** killzones in America/New_York; the "day" is the FTMO server day via `real_costs.server_zone` (US-DST
  dates, measured in docs/audits/2026-09-29-ftmo-server-timezone.md); the spread is the median of the
  `ftmo_demo_2026_09` profile at the server-hour bucket of the killzone open.
- **Isolation per decision:** `claude -p --safe-mode --tools "" --strict-mcp-config --no-session-persistence --model
  claude-opus-5-5 --system-prompt-file <file> --output-format json --effort high`, prompt on stdin, in an empty directory.
  A decision is valid only if the CLI's `modelUsage` names exactly the pinned model (never `--fallback-model`; if the
  served model cannot be verified the record says so), with `num_turns` 1, no tool use and no permission denial.
  Otherwise it is a technical failure, retried once (logged); a usage limit or a model-pin mismatch only pauses the single
  run. Every start, pause and resume is a record in `decisions.jsonl`.

## 3. Pinned for the run (§46)

- Model: `claude-opus-5-5`. CLI: Claude Code 2.1.286. Thinking effort: `high` (pinned: the CLI default is version
  dependent and its result does not record it).
- Template, knowledge-base files, harness and evaluator are committed before the first call; no change after the first
  decision. A pause is not a re-run (`run` resumes with the committed template and never regenerates a stored decision).

## 4. Unchanged

Hypothesis and H0; the window (2026-07-01 -> 2026-10-02 20:45 UTC, FTMO 5m XAUUSD and US500); no secondary window for
the verdict; the minimum of 60 filled C trades (INSUFFICIENT below); the primary test as written; the fill rule (buy
limit fills when ASK <= entry, stop first when one bar touches both, flat at 16:00 ET); arms R, M, T; "a PASS is evidence
for a forward demo test, not for live use".
