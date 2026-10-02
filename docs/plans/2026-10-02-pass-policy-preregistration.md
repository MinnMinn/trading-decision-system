# FTMO pass-policy study -- pre-registration (2026-10-02, committed BEFORE the run)

Owner request 2026-10-02: "(b). Trong lúc chờ, hãy thử tìm kiếm các hướng khác có khả năng pass quỹ cao trong 3-4 tháng.
Chứng minh độ hiệu quả của các hướng, phương pháp." Code: `scripts/research/pass_policy.py`; tests: `scripts/tests/test_pass_policy.py`.

## 0. Why policy, not more edge

Barrier law (Brownian approximation, ultimate fail <= 10 %): the best P(Phase 1 within 85 weekdays) is ~0.37 at annual Sharpe
1.37 (the baseline), ~0.62 at 1.8, ~0.78 at 2.2. F4/F5 showed the components available today do not raise the book's daily
Sharpe. What is left: (i) path-dependent risk (throttle after drawdown, a daily stop) and stacking validated components at the
1 % per-trade ceiling, (ii) the RETRY policy (a new challenge after a fail). Neither can raise the Sharpe; both can change the
probability of being funded within 3-4 months. This study measures by how much.

## 1. Policy grid (36): book x per-trade risk x throttle x daily stop

- book: base3 (H7 gold, E5 gold, E5 US500) | base3+G9au | base3+G9au+G9ag (the F4 survivors; G9 is paper-only until forward)
- per-trade risk: 0.5 % | 0.75 % | 1 % (never above the 1 % ceiling; the throttle only lowers it)
- throttle: none | dd3 (x1 above 97 % of the initial balance, x0.5 to 94 %, x0.25 below)
- daily stop: none | no new entry on a server day whose realised P&L <= -2 %

FTMO rules modelled: P1 +10 %, P2 +5 % (starts the day after P1), fail at balance <= 90 % or a day's realised loss <= -5 %,
>= 4 traded days per phase, no time limit. P&L realised at each trade's exit (floating P&L not modelled -- disclosed; every
trade carries a protective stop).

## 2. Primary metric and protocol

Primary: P(FUNDED -- both phases passed -- within 122 calendar days of the start), no retry. Secondary: within 91 days; first-
attempt fail rate; the same with retry (a new attempt the day after a fail, until day 122); mean attempts.

1. SELECTION: challenges starting every Monday from the common span start (2021-10) to 2023-12-31. Admissible iff first-
   attempt fail <= 10 %. Chosen (no retry) = the admissible policy with the highest primary metric; chosen (with retry) = the
   highest funded-within-122-days-with-retry, any fail rate.
2. CONFIRMATION: the same policies on starts 2024-01-01 -> end (never used to choose). Reported for every policy.
3. STRESS: stationary block bootstrap of whole weekdays (mean block 20, 3000 paths, seed 20261002) for the chosen policies and the
   reference (base3, 1 %, no throttle, no stop), at the edge as measured AND with every component's mean R cut by 50 %.

A direction is called EFFECTIVE only if the chosen policy beats the reference on the primary metric in the confirmation starts
AND in the 50 %-haircut bootstrap. Otherwise it is reported as not effective. The component edges were read on this history
(disclosed): this study validates the POLICY, the forward paper/demo record validates the EDGE.
