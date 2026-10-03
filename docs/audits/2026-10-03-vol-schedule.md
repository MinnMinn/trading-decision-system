# A1 -- phase-aware volatility through the stop width, on fvg-book v3 -- result (2026-10-03)

**DESCRIPTIVE / EXPOSED** (the H7 / G9 XAUUSD sequences were already read). Pre-registration:
docs/plans/2026-10-03-vol-schedule-preregistration.md (final at 2bfe0cb, before the run). Code `scripts/research/vol_schedule.py`
at that commit; raw `docs/audits/2026-10-03-vol-schedule.json`. Base v3 = H7 + G9 XAUUSD, 1 % of the initial balance at the
stop, dd3, full gold history 2004 -> 2026-09 (5,979 trades). Post-hoc diagnostics are marked **[post hoc]**.

## 1. Verdict by the pre-registered rule: 0 of 5 policies PROPOSED

Every tighter-stop policy clears the value test (Delta E[net] > 0 at the 50 % haircut) and the fail test (first-attempt fail
<= 10 % in the confirmation starts and in the haircut bootstrap), and every one FAILS the tail test: the worst single trade
in the history loses more than the 1.2 % gap tolerance -- **1.39 % of the balance at k = 1.4, 1.94 % at k = 1.0**. The
owner's rule is "1 % = the maximum loss at the stop"; a gap through the stop breaks it.

| policy (k_P1 / k_P2) | Delta E[net] edge x1 | Delta E[net] haircut 50 % | Delta E[net] edge 0 | confirmation 1st fail | haircut-bootstrap 1st fail | worst trade, % of balance | PROPOSED |
|---|---|---|---|---|---|---|---|
| 2.0 / 2.0 (reference, v3 today) | -- | -- | -- | 0.00 | 0.003 | 1.18 | -- |
| 2.0 / 1.4 | +0.55 | +0.15 | +0.02 | 0.00 | 0.005 | 1.39 | no (tail) |
| 2.0 / 1.0 | +0.80 | +0.24 | +0.04 | 0.00 | 0.023 | 1.94 | no (tail) |
| 1.4 / 2.0 | +1.19 | +0.36 | -0.03 | 0.00 | 0.036 | 1.39 | no (tail) |
| 1.4 / 1.4 | +1.78 | +0.59 | +0.01 | 0.00 | 0.041 | 1.39 | no (tail) |
| 1.4 / 1.0 | +2.12 | +0.72 | +0.02 | 0.00 | 0.063 | 1.94 | no (tail) |

(Delta E[net] in % of the initial balance, 12-month horizon, fee 0.6 %, split 80 %, monthly payouts -- named defaults.)

## 2. What the numbers say

- **Leverage on a real edge, not variance.** Per-trade Sharpe is about constant across stops (mean / sd R: 0.073 / 0.54 at
  k = 2, 0.109 / 0.75 at 1.4, 0.148 / 1.00 at 1.0); at edge 0 the value change is ~0 (+-0.04 %), so the gain needs the edge.
- **Value**: E[net] per 12-month horizon at the measured edge rises from +1.5 % of the balance (reference) to +3.7 %
  (1.4 / 1.0); at the half edge from -0.17 % (a losing proposition after fees) to +0.55 %.
- **Speed**: funded <= 122 days, bootstrap at the measured edge 0.035 -> 0.20; historical confirmation starts (2024+, 116
  starts) 0.009 -> 0.38; selection starts (2004-2023, 1,014) 0.11 -> 0.38. Funded eventually stays 0.94-1.00 (selection).
- **Fails**: first-attempt fail stays <= 6 % with the half edge; at edge 0 a tighter Phase-1 stop raises it to 25-29 %.
- **The reference itself breaks the strict rule**: at today's k = 2 the worst trade in 22 years lost 1.18 % of the balance.

## 3. [post hoc] Where the tail comes from

Material gaps through the stop are rare -- trades with R < -1.05: 2 of 5,979 at k = 2, 4 at k = 1.4, 6 at k = 1.0 -- and the
worst are news gaps: 2012-06-01 12:05 UTC (entry 25 min before the US payrolls release; -1.39 R at k = 1.4, -1.94 R at k = 1.0),
2021-03-17 17:15 UTC (entry 45 min before that day's FOMC statement at 18:00 UTC; -1.58 R at k = 1.0). The live platform blocks NEW entries 10 min either
side of HIGH releases (CLAUDE.md §24) but does not flatten an open position before one, and the research replay has no
historical release calendar at all (event-calendar.json is a 2026 snapshot).
(The JSON field `gap_beyond_1R_share` is mis-specified: it counts every stopped trade, because the spread pushes a stop exit
just below -1 R. The counts above are the honest measure.)

## 4. What it would take (a NEW pre-registration, not a reinterpretation of this one)

Two ways to keep "1 % = the maximum loss" true including gaps, each a separate, pre-registered policy study:
1. **Size for the gap**: risk_pct = 1 % / (worst gap multiple) -- e.g. ~0.7 % at k = 1.4 -- trading part of A1's gain for a
   hard cap. The worst gap multiple is itself an in-sample number; a tail model or a margin above it must be pre-declared.
2. **Be flat across HIGH-impact releases** (no open position from N minutes before a release to M minutes after). This needs a
   point-in-time historical release calendar (US payrolls, CPI, FOMC are published schedules; not in the repo today).

Experiment budget: 6 policies (incl. the reference) on exposed data; 1 post-hoc tail diagnostic.
