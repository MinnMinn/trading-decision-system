# Amendment 2 to the Claude discretionary ICT pre-registration (2026-10-05): disclosures, no rule change

**Amends / extends:** `docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md` and
`docs/plans/2026-10-05-claude-ict-amendment-1.md`. Neither is edited.

**Made:** 2026-10-05T01:05Z, while the single run is in progress (about 100 of 338 decisions stored; none of the
window's outcomes has been computed or looked at by anyone: `evaluate` has not run). It changes NO rule: not the
verdict, not the evaluator (blob `4c0fe4fa1fb6ef4bd6a5545c9f2b3ab565e3e63f`, frozen at the start commit 873672c), not the
prompts. It records two limitations found by the pre-registration's reviewer (session "Khám phá hệ thống FTMO", review
of commit 251a444: no blocking defect; evaluator safe to run in the PASS direction; 97 tests, all 338 prompts rebuilt
with identical sha256, six prompts checked against the 5m data with no bar closed after a killzone open) and commits to
what the report will show about them. The reviewer's measurements below used bars before 2026-07-01 and random
directions only; the coordinator did not reproduce them.

## 1. The primary test's control is asymmetric by order type (a limitation, not a gate)

**What.** Amendment 1 explained the primary test's over-rejection for limit books by mean reversion alone (the
control's opposite trade starts at the fill instant, in the direction of the move a limit just faded). Part of it comes
from the fill-bar rule instead. On the fill bar the order of the bar's extremes is unknown. The evaluator resolves it
against the trade (stop first), but for the CONTROL the same unknown extreme falls on the control's STOP side while it
falls on C's TARGET side; the stop is nearer than the target, so the two are not symmetric (`control_pair`,
`claude_ict_eval.py` lines 275-291, with the exit rules at lines 205-207).

**Measured (reviewer; bars before the window; random directions): mean(R_C - R_opp) per filled trade.**

| US500 | market | limit | stop |
|---|---|---|---|
| as the evaluator computes it | 0 | +0.095 R | -0.108 R |
| if the control started on bar f+1 (not adopted) | - | +0.074 R | -0.02 R |

So about 0.04 R per direction of the limit / stop gap comes from the fill-bar rule and the rest from mean reversion.
Direction of the bias: a direction-blind LIMIT book is favoured by the primary test (over-rejection, as in amendment 1's
table); a direction-blind STOP book is disfavoured (under-rejection, 1.8 % to 2.9 % in the calibration).

**Consequence.** A false PASS is not possible through this: the mirror-order test, which is symmetric, is a gate
(amendment 1). A book made mostly of STOP orders could be failed by the primary test without cause.

**Commitment.** The report gives, for every order type and instrument, next to the primary test's p-value:
the number of filled trades, mean(R_C - R_opp) and the mirror test's p-value (descriptive; none of it gates beyond
what amendment 1 says). If the verdict is FAIL and the filled book is mostly STOP orders (more than half of the filled
trades), the report says in its first paragraph that the primary test is biased against stop books by about -0.1 R and
reads the mirror p-value beside it. The evaluator is not changed.

## 2. Arm M ran on a shortened 15m series

**What.** The 15m history the arm-M scan reads ends earlier than the window: US500 at 2026-09-28 17:00Z, XAUUSD at
2026-10-01 02:00Z, against a window end of 2026-10-02 20:45Z (`m_scan`, `claude_ict_eval.py` lines 489-564). Arm M
misses about 4 days of US500 and 1.7 days of XAUUSD. Importing newer 15m bars would change a frozen input and
`require_frozen_inputs` would refuse the evaluation, so the series stays as it is.

**Commitment.** The report states these end times and the number of killzone days of each instrument that M could not
scan, next to the "C beats M" condition. An M with no filled trade stays "not evaluable" (amendment 1).

## 3. Notes the report will state (no action)

- **Cost may be understated:** the spread is the median of the 2022-07 to 2026-09 table at the server hour of the
  killzone open (`ftmo_demo_2026_09`), and commission has not been measured for these CFDs. After `evaluate`, one
  descriptive line is computed from the same stored decisions with the spread doubled, by a separate script that the
  evaluation does not depend on. It gates nothing.
- **R:R >= 1 is checked on the model's own entry price.** A market order fills at the next bar's open, so its realised
  reward/risk can be below 1.
- **Arms M and T** may hold a trade past 17:00 ET, never past the FTMO rollover.
- **Daylight saving** is exercised only by the synthetic tests: the whole window is on EDT / EEST.

## 4. Unchanged

Everything in the pre-registration and in amendment 1, including the verdict rules, the 60-trade minimum, the
fourth PASS condition, the pinned model, CLI and effort, and the rule that the run is done once and `evaluate` runs once.
Step 5 of the run (evaluate) waits for this amendment to be committed, as the reviewer asked.
