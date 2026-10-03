# A3 -- add G9 XAGUSD (silver volatility breakout) to fvg-book v3? -- pre-registration (2026-10-04) [A3-P1]

**Committed BEFORE the run. DESCRIPTIVE / EXPOSED** by construction: every trade sequence used here was already read (F4,
book-variants, pass-policy). Code: `scripts/research/a3_silver.py` (reuses scripts/research/vol_schedule.py and
pass_policy.py functions unchanged); tests: `scripts/tests/test_a3_silver.py`. Raised by the session "Khám phá hệ thống
FTMO" (2026-10-04): G9 XAGUSD survived all three F4 reads (docs/audits/2026-10-02-edge-f4.md: discovery +43.1 bp,
confirmation +34.4 bp, exposed +25.6 bp net) and was rejected only in pass-policy, stacked on a base that contained the
look-ahead E5 (docs/audits/2026-10-03-e5-lookahead-erratum.md). Unlike a tighter stop (A1), adding a component keeps the
owner's strict "1 % = the maximum loss at the stop" rule, so it is the one speed-up lever left inside that rule.

## 1. Books (1 % of the initial balance at the stop, stop 2 x sigma_5m x sqrt(hold), dd3, flat before the rollover)

- **v3** = H7 XAUUSD + G9 XAUUSD (the demo book). **v3+ag** = v3 + G9 XAGUSD. Nothing else differs.
- Span: from G9 XAGUSD's first trade (XAUUSD components trimmed to the same start) to the end of the stored history, so both
  books are compared on the same days.

## 2. Measurement (as A1, docs/plans/2026-10-03-vol-schedule-preregistration.md §3; floating P&L as FTMO counts it)

1. Historical starts: Mondays before 2024-01-01 (selection) and from it (confirmation): funded <= 122 days, funded eventually,
   median days, first-attempt fail.
2. Stationary block bootstrap of weekdays (mean block 20, 3,000 paths, seed 20261002), the SAME sampled days for both books,
   at edge x {1, 0.5, 0} (haircut = every component's mean R cut by that share): funded <= 122 days, first-attempt fail, and
   the value objective E[payouts + refund - fees] inside a 252-weekday horizon (fee 0.6 % of the balance, split 80 %, monthly
   payout, a funded breach ends the account; named defaults).
3. Daily-R correlation of G9 XAGUSD with v3 over the span; the worst single-trade loss in % of the balance per component.

## 3. Decision rule (fixed now)

v3+ag is PROPOSED to the owner iff, against v3: Delta E[net] > 0 at the 50 % haircut in the bootstrap, AND first-attempt fail
<= 10 % in the confirmation starts and in the haircut bootstrap, AND the worst single-trade loss of G9 XAGUSD <= 1.2 % of the
balance (A1's gap tolerance). If Delta E[net] at edge 0 is also > 0, the proposal must say the gain is variance, not edge.
Otherwise: not proposed. A proposal is version-significant (fvg-book v4): the owner decides.

## 4. Prior reads (disclosed)

F4's three reads; book-variants (2021-10 -> 2026-09: mean R +0.001 per trade, by year -0.17 / 0.00 / -0.08 / +0.07 / +0.04 /
+0.02 for 2021-26, daily correlation 0.02 with the old base); pass-policy's stacked replays (67-87 % first-attempt fail in
2021-23 starts without the throttle, 4-78 % with it, on the E5 base). The prior for a gain is weak; the test is cheap.
Experiment budget: 1 comparison (2 books) on exposed data.
