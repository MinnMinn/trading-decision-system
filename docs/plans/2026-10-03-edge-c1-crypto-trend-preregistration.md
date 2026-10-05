# Family C1 -- daily Donchian-ensemble trend on Binance USDT-M perps (BTC, ETH, SOL) -- pre-registration (2026-10-03)

**Committed BEFORE any read of C1 outcomes.** Code: `scripts/research/edge_c1.py`; tests: `scripts/tests/test_edge_c1.py`
(hand-built series only) and the detector leakage probe. Origin: docs/plans/2026-10-03-crypto-cfd-design.md (rank 1; the
design workflow's adversarial critic required every correction below). Owner direction 2026-10-03: crypto and CFD first;
1 % = the maximum loss at the stop. A validated C1 is a **Binance** book, not an FTMO book.

## 1. Hypothesis and source

Crypto trends persist: a long/flat ensemble of Donchian breakouts with trailing midpoint stops, volatility-targeted, earns a
positive alpha over holding the coins. Source: Zarattini, Pagani, Barbon, "Catching Crypto Trends" (Concretum, 2025; PDF
https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf), "Combo" model, CoinMarketCap spot data
2015-01-01 -> 2025-03-19, Table 3 net of 10 bp with a 20 % rebalance threshold (BTC Sharpe 1.56, ETH 1.51, SOL 1.68). Related:
Liu & Tsyvinski (time-series momentum in crypto); Detzel et al. (moving-average rules) as a non-decision arm. **Every
parameter is the source's, frozen**; nothing is tuned here. Direction fixed: long/flat; one-sided tests.

## 2. Data (point-in-time; imported by `scripts/import-binance-um-history.py`, checksum-verified)

- Signals: Binance SPOT 1d closes (UTC days), `data/history/binance_spot/ohlcv.{SYM}.1d` (BTC/ETH from 2017-08-17, SOL
  from 2020-08-11). No spot/perp splice in the signal.
- Fills and P&L: perp 5m opens `data/history/binance_um/ohlcv.{SYM}.5m` from 2020-01-01 (SOL 2020-09-14); before that spot 5m
  `data/history/binance_spot/ohlcv.{SYM}.5m` (BTC/ETH 2017-08 -> 2019-12), P&L on spot.
- Funding: realized, `data/history/binance_um/funding.{SYM}.json.gz` (2020-01 ->) and `funding_rest.{SYM}.json.gz` (REST,
  BTC 2019-09-10 ->, ETH 2019-11-27 ->); before a symbol's perp listing, a proxy of 0.01 % per 8 h at 00/08/16 UTC on long
  notional. Actual settlement times are used (SOL prints 2 h / 4 h intervals).

## 3. Rules (per coin; n in {5, 10, 20, 30, 60, 90, 150, 250, 360})

- C_t = spot 1d close of UTC day t. Up = max(C_{t-n+1..t}), Dn = min(C_{t-n+1..t}), Mid = (Up + Dn) / 2 (today included).
- Entry: flat and C_t == Up_{n,t} -> long; stop for t+1: TS = Mid_{n,t}. Exit: long and C_t < TS_{n,t} (the stop in force
  during day t) -> flat; else TS_{n,t+1} = max(TS_{n,t}, Mid_{n,t}) (never lowered).
- Weight: sigma_t = SD of the last 90 daily log returns of C x sqrt(365); w_{n,t} = min(0.25 / sigma_t, 2.0) x Pos_{n,t};
  coin target W_t = (1/9) x sum_n w_{n,t}.
- A coin is eligible from its first day with 360 prior spot closes (BTC/ETH 2018-08-12, SOL 2021-08-06).
- Execution: decided at 00:00 UTC of day t+1 from C_t; filled at the OPEN of the 5m bar starting 00:05:00 UTC (never inside
  00:00 +/- 1 min). Any sub-model entry or exit trades to the target; a volatility-only change trades only when
  |W_target - W_held| > 0.20 x W_target (the relative reading, frozen).
- Capital: equal per eligible coin, re-split at the fill of the first UTC day of each month and when a coin becomes
  eligible (those trades are charged).

## 4. Costs

Taker 0.05 % per side (the repo's assumed VIP-0, docs/architecture/risk-config.json) + 1 bp slippage per side, on every traded
notional. Funding at every realized settlement tau: rate_tau x q x P_tau (q = units held, P_tau = the 5m open at tau as the mark
proxy); a settlement at 00:00 is paid by the position held BEFORE the 00:05 fill.

## 5. Tests

- Daily net sleeve return r_S,d over [00:05 d, 00:05 d+1) on the equal-capital sleeve; benchmark r_B,d = the equal-capital
  same-interval return of the eligible coins (perp; spot before), no costs, no funding (conservative: the sleeve must beat its
  own funding).
- **T1 (decision):** alpha in r_S = alpha + beta r_B + e, one-sided H1 alpha > 0, Newey-West SE with 10 lags (CR1 by date
  reported too; on a single daily series it is White SE and ignores trend P&L's serial dependence). T2-T4: the same per coin
  against its own return. **BH over T1-T4, q = 0.10.**
- **Placebo gate:** circular-shift every coin's nine Pos_n series jointly by one shared offset k ~ U{60 .. L-60} days,
  recompute weights with the destination date's sigma, recompute fees and funding; 1,000 draws, seed 20261003;
  p_P = (1 + #{alpha_k >= alpha_obs}) / 1001.

## 6. Reads (each ONCE, each in its own commit; the simulator runs on data truncated at the read's END and reports the read's
window only; positions open at the window's start carry over)

| read | window | status |
|---|---|---|
| DISCOVERY | 2018-08-12 -> 2022-07-28 | in the SOURCE's sample: a venue / perp / funding robustness read, not out-of-sample |
| CONFIRMATION | 2022-07-29 -> 2025-03-19 | in the source's sample (same caveat) |
| EXPOSED | 2025-03-20 -> 2026-09-30 | the only data after the source's sample end; never read for this hypothesis |

Thresholds: DISCOVERY -- CANDIDATE iff BH rejects T1, mean net daily return > 0, p_P <= 0.10. CONFIRMATION -- T1 one-sided
p < 0.05, net > 0, net > 0 at 2x slippage, p_P <= 0.10. EXPOSED -- T1 one-sided p < 0.10, net > 0. Labels: VALIDATED (all
three), PROMISING (discovery + confirmation pass, exposed net > 0 with p >= 0.10: forward paper only), DEAD (alpha <= 0 in
discovery or in confirmation), INCONCLUSIVE (anything else; worded "inconclusive at this power"). "Regime-driven" is added when
> 50 % of a read's alpha comes from <= 3 calendar months. A single coin is promoted only if T1 is VALIDATED and the coin passes
all three reads itself. A discovery + confirmation pass is NOT called validated (source in-sample).

## 7. Diagnostics outside the BH family (reported at every read)

- N1 Detzel MA arms (BTC, ETH): S_L = 1 if C_t > MA_L for L in {5, 10, 20, 50, 100}, long/flat 1x, and their mean; same
  execution, costs, funding.
- N2 owner sizing (1 % lost at the stop): per-coin open risk = sum_n (w_n / 9) x max(0, (P_fill - TS_n) / P_fill) x
  capital_i / equity capped at 1 % (scale the coin's w_n down), total <= 3 %; report CAGR, max drawdown, R / yr, months to +10 %,
  realized loss / planned stop loss per ensemble exit (stops act on daily closes: a crash day can cost a multiple of 1 %) and
  the worst day.
- N3 gross vs net, funding drag by year, 2x slippage. N4 alpha by calendar year and the best-3-months share. N5 daily P&L
  correlation with fvg-book v3 (H7 + G9 gold): UTC day d -> the FTMO server day that ends on d (weekend days -> next server
  day). N6 alpha against a FUNDED benchmark.

## 8. Power (stated before reading)

Source in-sample appraisal ratio ~1.15 (BTC) to ~1.4 (3-coin sleeve), assuming ~70 % BTC vol (unverified). Full published
effect: sleeve t ~ 2.8 / 2.3 / 1.7 by read, joint pass ~0.35-0.40. Half the effect net of 2-5 %/yr funding: t ~ 1.4 / 1.1 / 0.9,
joint pass ~0.03. The test can confirm an edge near the published size; it cannot separate a modest edge from zero.

## 9. Prior reads (disclosed)

- The source chose every parameter on 2015-01-01 -> 2025-03-19 (overlaps DISCOVERY and CONFIRMATION).
- The design workflow (2026-10-03) read UNCONDITIONAL statistics on the perp history: realized funding by year (BTC 11.7 %/yr
  average, 30.6 % in 2021, 5.1 % in 2025, 2.2 % in 2026 YTD; ETH 13.8 %; SOL 0.2 %), return SDs by horizon, the BTC-XAU daily
  correlation (0.19), and trigger COUNTS of 10-day-high signals. No forward return conditioned on a trend signal was read.
- Earlier repo crypto work: ICT / Wyckoff on spot 2022-08 -> (research-ledger `crypto-history-2023-2026`, development); a
  different mechanism, same bars.
- The 2021-2022 bull and bear markets are public knowledge.

## Amendment [C1-A1] (2026-10-04, before any read, outcome-blind)

Implementation choices where §2-§7 left room, fixed by the implementer and two adversarial reviewers (design workflow
`implement-c1-m1-h7x`) BEFORE any C1 outcome existed; they are also written into every read's meta
(`scripts/research/edge_c1.py` RESOLVED_AMBIGUITIES). Data: the SOLUSDT perp 5m days 2022-02-26..28 and 2022-04-01..02, absent
from the archive's monthly files, are filled from its daily files (checksum-verified); the EXPOSED read's END mark (the
2026-10-01 00:05 bar) and the 2026-10-01 00:00 settlement come from the archive's daily files and the REST funding endpoint.
C1's point-in-time probe is the `PointInTime` class of scripts/tests/test_edge_c1.py (truncating closes never changes a past
signal, stop, sigma, eligibility, target or held weight; perturbing every price after a read's END leaves that read's JSON
identical): C1's decisions are daily weights, not bar events, so the shared event probe does not apply.

1. decide/held_at: W_held = the weight set at the coin's last trade (not the price-drifted exposure since); the 20 % rule compares W_target with it.
2. coin_signals: a missing spot 1d close = no state update (positions and stops carry); sigma's log returns are taken between consecutive AVAILABLE closes, sample SD (n - 1); a sub-model whose n closes do not exist yet stays flat; entry needs C_t == Up exactly.
3. build/coverage: eligible from the first fill day with 360 prior spot closes (sigma then always defined); the dates must equal ELIGIBLE_FROM (§3) and the window's first day must be a grid day, or the read refuses.
4. simulate: benchmark r_B = equal-capital SUB-ACCOUNTS re-split on the sleeve's re-split days (first day, first UTC day of a month, a coin joining) and drifting with each coin's P1/P0 between them; N6's funded benchmark the same with P1/P0 - F/P0.
5. simulate: positions open at the window's start are placed at an equal split of capital 1.0 without a fee; units = held weight x the coin's capital BEFORE the fee / P0, the fee then leaves the coin's cash.
6. simulate: the one interval spanning the spot -> perp switch books the spot/perp basis in sleeve and benchmark; no switch trade is charged.
7. coverage/price_at: every fill (every eligible day from the coin's eligibility) and the END mark need a 5m bar OPENING at 00:05:00 UTC; one missing -> the read refuses (never a delayed fill).
8. funding_mark: P_tau = the open of the 5m bar starting at tau; with no bar there, the close of the last bar ending at or before tau (never a later price), counted in meta.funding_mark_lookups.
9. load_coin/settlements_in/coverage: REST rows before the archive, the archive from its first month (the archive wins on an equal stamp); before the first realized settlement the 0.01 %/8 h proxy at 00/08/16 UTC; the read refuses on a step > 8 h between realized settlements in the window or without the 00:00 settlement after the last day.
10. regress: one-sided p of the Newey-West t against Student-t with n - 2 df; fewer than 12 observations -> no test.
11. T2-T4: the coin's sub-account net daily return regressed on its own P1/P0 - 1; each read's thresholds are T1's.
12. placebo: the shift acts on each coin's list of eligible window days (L_c of them); L_c = L -> k; a coin joining inside the window -> k_c = 60 + (k - 60) mod (L_c - 119), so 60 <= k_c <= L_c - 60; L_c < 120 -> unshifted and its own p_P is None; the carried-in weight of a shifted coin = its first eligible day's lev x the circular predecessor's mask.
13. p_placebo: a draw whose alpha is undefined counts as alpha_k >= alpha_obs (conservative).
14. regime: 'alpha from <= 3 months' = the 3 best calendar months' summed contribution (1/N) sum (y - beta x) / alpha.
15. N2: the target is scaled so the coin's open risk <= 1 % and the total <= 3 % (_n2_scales), and the HELD weight is capped at the same limits (_n2_cap: a cap forces a trade inside the 20 % band).
16. single-coin promotion: T1's label VALIDATED and the coin's own read pass in all three reads.
