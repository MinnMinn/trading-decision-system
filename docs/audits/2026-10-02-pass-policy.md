# FTMO pass-policy study -- results (2026-10-02)

Pre-registration: docs/plans/2026-10-02-pass-policy-preregistration.md (commit d0a511b, before the run). Raw:
`docs/audits/2026-10-02-pass-policy.json`; descriptive add-on (post hoc, not used to choose): `...-pass-policy-descriptive.json`.
"Funded" = Phase 1 (+10 %) AND Phase 2 (+5 %) both passed. Span 2021-10 -> 2026-09.

## 1. Verdict

| | reference: base3 @1 % | chosen: base3 + G9 gold @1 %, dd3 throttle |
|---|---|---|
| CONFIRMATION starts 2024-01 -> (115): funded <= 91 d | 0.12 | 0.18 |
| CONFIRMATION: funded <= 122 d | 0.23 | **0.36** |
| CONFIRMATION: first-attempt fail | 0.00 | 0.00 |
| CONFIRMATION: median days to funded | 206 | 147 |
| BOOTSTRAP edge as measured: funded <= 122 d / 1st fail | 0.10 / 0.06 | **0.22 / 0.01** |
| BOOTSTRAP edge -50 %: funded <= 122 d / 1st fail | 0.05 / 0.18 | **0.13 / 0.06** |
| SELECTION starts 2021-10 -> 2023 (116): funded <= 122 d | 0.00 | 0.07 |

Pre-registered criterion (beats the reference in confirmation AND in the 50 %-haircut bootstrap): **MET** -- stacking G9 gold
with the drawdown throttle roughly doubles the chance of being funded within 4 months AND lowers the fail rate (the throttle
is what makes the extra component safe: without it the same book fails 17 % / 35 % of first attempts in the bootstrap).

But the absolute level is NOT "high": 13-36 % within 4 months depending on the edge and the regime; ~70-98 % eventually.

## 2. Directions that do NOT work (measured)

- Daily stop at -2 %: no gain anywhere (the -5 % FTMO day limit is never the binding failure of these books).
- Lower risk (0.5 % / 0.75 %): almost never funded within 4 months.
- Adding G9 silver: more speed only in 2024-26, 67-87 % first-attempt fail in 2021-23; with the throttle still 4-78 %. Rejected.
- Retry after a fail: the chosen policy almost never fails, so retry adds nothing (with retry = without).
- Two accounts started 28 days apart (descriptive): any funded <= 122 d 0.23 vs 0.21 for one -- the paths are the same market.

## 3. Regime dependence (descriptive, funded <= 122 d by start year, chosen policy)

2021 0.00 | 2022 0.12 | 2023 0.04 | 2024 0.21 | 2025 0.50 | 2026 0.40 (reference: 0 / 0 / 0 / 0.04 / 0.39 / 0.40). The books
are gold-trend books: fast in a trending gold market, slow otherwise. No policy changes that.

## 4. What it means for the goal

- Barrier law: ~80 % funded within 4 months needs an annual Sharpe >= ~2.2 on the book; today's is 1.37. Policy cannot buy
  Sharpe; only a new INDEPENDENT return source can (forex was the identified candidate; owner chose to wait, 2026-10-02).
- The best verified improvement is a Trading System change: base3 + G9 gold, 1 % per trade, dd3 throttle. G9 gold is still
  paper-only (forward stage (a) pending), so adopting it in the demo is an owner decision (version-significant, CLAUDE.md §47).

## 5. Full grid (selection = starts < 2024; confirmation = starts >= 2024)

| policy | SEL funded<=122d | SEL 1st fail | CONF funded<=91d | CONF funded<=122d | CONF 1st fail | CONF <=122d with retry |
|---|---|---|---|---|---|---|
| base3|r0.005|none|stopNone | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3|r0.005|none|stop0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3|r0.005|dd3|stopNone | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3|r0.005|dd3|stop0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3|r0.0075|none|stopNone | 0.00 | 0.00 | 0.01 | 0.03 | 0.00 | 0.03 |
| base3|r0.0075|none|stop0.02 | 0.00 | 0.00 | 0.01 | 0.03 | 0.00 | 0.03 |
| base3|r0.0075|dd3|stopNone | 0.00 | 0.00 | 0.01 | 0.03 | 0.00 | 0.03 |
| base3|r0.0075|dd3|stop0.02 | 0.00 | 0.00 | 0.01 | 0.03 | 0.00 | 0.03 |
| base3|r0.01|none|stopNone | 0.00 | 0.01 | 0.12 | 0.23 | 0.00 | 0.23 |
| base3|r0.01|none|stop0.02 | 0.00 | 0.01 | 0.12 | 0.22 | 0.03 | 0.22 |
| base3|r0.01|dd3|stopNone | 0.00 | 0.00 | 0.12 | 0.22 | 0.00 | 0.22 |
| base3|r0.01|dd3|stop0.02 | 0.00 | 0.00 | 0.12 | 0.22 | 0.00 | 0.22 |
| base3+G9au|r0.005|none|stopNone | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3+G9au|r0.005|none|stop0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3+G9au|r0.005|dd3|stopNone | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3+G9au|r0.005|dd3|stop0.02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| base3+G9au|r0.0075|none|stopNone | 0.00 | 0.28 | 0.07 | 0.11 | 0.00 | 0.11 |
| base3+G9au|r0.0075|none|stop0.02 | 0.00 | 0.28 | 0.05 | 0.10 | 0.00 | 0.10 |
| base3+G9au|r0.0075|dd3|stopNone | 0.00 | 0.00 | 0.07 | 0.10 | 0.00 | 0.10 |
| base3+G9au|r0.0075|dd3|stop0.02 | 0.00 | 0.00 | 0.05 | 0.09 | 0.00 | 0.09 |
| base3+G9au|r0.01|none|stopNone | 0.08 | 0.44 | 0.20 | 0.38 | 0.09 | 0.38 |
| base3+G9au|r0.01|none|stop0.02 | 0.08 | 0.47 | 0.18 | 0.39 | 0.12 | 0.39 |
| base3+G9au|r0.01|dd3|stopNone | 0.07 | 0.00 | 0.18 | 0.36 | 0.00 | 0.36 |
| base3+G9au|r0.01|dd3|stop0.02 | 0.06 | 0.00 | 0.17 | 0.36 | 0.00 | 0.36 |
| base3+G9au+G9ag|r0.005|none|stopNone | 0.00 | 0.21 | 0.01 | 0.04 | 0.00 | 0.04 |
| base3+G9au+G9ag|r0.005|none|stop0.02 | 0.00 | 0.21 | 0.01 | 0.04 | 0.00 | 0.04 |
| base3+G9au+G9ag|r0.005|dd3|stopNone | 0.00 | 0.00 | 0.01 | 0.04 | 0.00 | 0.04 |
| base3+G9au+G9ag|r0.005|dd3|stop0.02 | 0.00 | 0.00 | 0.01 | 0.04 | 0.00 | 0.04 |
| base3+G9au+G9ag|r0.0075|none|stopNone | 0.00 | 0.87 | 0.14 | 0.32 | 0.03 | 0.32 |
| base3+G9au+G9ag|r0.0075|none|stop0.02 | 0.00 | 0.87 | 0.14 | 0.32 | 0.03 | 0.32 |
| base3+G9au+G9ag|r0.0075|dd3|stopNone | 0.00 | 0.04 | 0.14 | 0.30 | 0.00 | 0.30 |
| base3+G9au+G9ag|r0.0075|dd3|stop0.02 | 0.00 | 0.04 | 0.14 | 0.29 | 0.00 | 0.29 |
| base3+G9au+G9ag|r0.01|none|stopNone | 0.00 | 0.67 | 0.36 | 0.70 | 0.08 | 0.70 |
| base3+G9au+G9ag|r0.01|none|stop0.02 | 0.00 | 0.78 | 0.36 | 0.67 | 0.11 | 0.67 |
| base3+G9au+G9ag|r0.01|dd3|stopNone | 0.00 | 0.77 | 0.33 | 0.58 | 0.00 | 0.58 |
| base3+G9au+G9ag|r0.01|dd3|stop0.02 | 0.00 | 0.78 | 0.33 | 0.57 | 0.00 | 0.57 |
