# Crypto + CFD method design (2026-10-03) -- synthesis of a 13-agent design workflow

**Type:** design record (no pre-registration, no read). Produced by a workflow of one repo-inventory agent, five literature
sweeps (time-series momentum, seasonality, derivatives flow, reversal/breakout, cross-asset) each followed by an adversarial
critic, one CFD gap sweep and one synthesis. Raw outputs of every agent: docs/audits/2026-10-03-crypto-cfd-design-workflow.json.
**What the agents read:** literature (cited URLs), repo files, Binance archive listings, and UNCONDITIONAL statistics on
data/history/binance_um (volatility, realized funding, trigger counts). No forward return conditioned on any candidate's signal
was read. The owner's direction (2026-10-03): crypto and CFD first, forex parked; 1 % = the maximum loss at the stop.
The pre-registrations that follow from it are separate files (C1, M1, H7x), each committed before its first read.

---

**Status: DONE_WITH_CONCERNS.** This was research only. No repo file was edited, and no strategy or outcome returns were read. My concerns are about statistical power and two decisions the owner has to make (section 6).

## 0. Bottom line

- **Rank 1: C1, a daily Donchian-ensemble trend book on BTC/ETH/SOL perps.** It is the published Zarattini-Pagani-Barbon "Combo", corrected for perps, funding and latency. It has the highest P(real after costs), costs little in fees and should be almost independent of the gold H7/G9 book. Its weakness is that the published spec was fitted on 2015 → 2025-03-19. That makes DISCOVERY and CONFIRMATION robustness reads only. EXPOSED (2025-03-20 → 2026-09-30) is the only clean read. Full pre-registration in section 2.
- **Rank 2: M1, the month-end pension-rebalancing effect on US index CFDs** (Harvey-Mazzoleni-Melone). It is cheap to run, tradable on FTMO, and its discovery window (2018-01 → 2021-08 daily bars) has probably never been read. Its power is weak. Optional pre-registration in section 3.
- **Rank 3: the H7 rule transferred to crypto, with G9 as a non-independent second member.** It is queued after C1 (sketch in section 4).
- **Honest expected yield.** By my priors, the chance that C1 ends VALIDATED is about 5-10% and M1 about 3%. The most likely result for both is INCONCLUSIVE, meaning "not found at this power", which is not "dead". They are still worth running because they are cheap, mostly on unread data, and a PROMISING result can feed a forward monitor.
- **Nothing else survives as a family.** Every other crypto hypothesis fails on cost (SEAS-1/XA1, XA4), on power (DF-3, DF-4, NSR, XA2, XA3, XA5, SEAS-4), on execution (DF-1/DF-2 need a spot account), or is the same mechanism as C1 or H7 (section 5).

## 1. Ranked plan

EV = P(real after costs) × frequency × size × independence, as specified. All numbers are **my judgment priors**, built from the upstream verdicts. None are measurements.

| # | Candidate | P(real, net) | Frequency | Size if real (R/yr; R = 1% of equity lost at the stop) | Independence from H7/G9 | EV (R/yr) | P(3 reads validate \| real) | Cost to run |
|---|---|---|---|---|---|---|---|---|
| 1 | **C1** crypto daily Donchian ensemble (CRY-TSMOM-1, corrected) | 0.40 | Daily weights, ~60 sub-model entries per coin per year | 2-6 (point 4) [a] | 0.9 | ~1.4 | ~0.35 at the full published effect, ~0.03 at half | Moderate: spot 1d/5m import needed; perp 5m and funding are already in the repo |
| 2 | **M1** month-end rebalancing, US index CFDs (CFD-R1) | 0.30 | ~60 trade days per index per year (12 episodes) | 1.5-3.5 (point 2.5) | 0.8 (tail co-movement in crisis months) | ~0.6 | ~0.03 at 10 bp, ~0.13 at 15 bp, ~0.4 at 20 bp | Low: 1D bars are in the repo; DGS10 is one CSV |
| 3 | **CRY-H7** transfer, pooled BTC+ETH(+SOL), with G9 as a non-independent member | 0.20 | ~140 triggers per coin per year | 2-8 nominal (point 4) [b] | 0.7 (same trend-continuation style; raw BTC-XAU daily correlation 0.19) | ~0.6 | ~0.10-0.15 at a gold-like per-trade z | Low to moderate: the detector exists; perp 5m is in the repo |
| 4 | Pre-FOMC overnight drift, US30 | — | ~8 per year | — | — | ≈0 now | — | Forward-only. Decay documented after 2015 (CFD sweep, item 1) |
| 5 | Weekend crypto → Monday US index short (B4 / SEAS-4 / XA3) | — | ~10 per year | — | — | ≈0 now | <0.10 | Forward-only. 42 events since 2022 |
| 6 | BTC 21-23 UTC window (SEAS-1 / XA1) | — | — | — | — | <0 at taker | — | Report-only measurement of decay. It cannot pay at taker fees |

[a] Here is my arithmetic, unverified on data. At the paper's full vol-target exposure, the open risk to the midpoint stops is several percent of equity per coin. Capping it at 1R per coin cuts exposure about 4-8x. If a net Sharpe of 0.5-0.8 survives, that leaves roughly 2-6 R/yr across 3 coins.
[b] If the edge is +5-10 bp net per trade and the stop sits at the opposite prior-day boundary (~3% on BTC), each trade is worth about 0.02-0.03 R. The three coins fire together, so open risk reaches about 3R on the same days.

Ranks 2 and 3 are tied within the noise of my priors. M1 ranks higher on independence, FTMO tradability and run cost. H7 is the cleaner out-of-sample test, because its parameters come from gold rather than from crypto data.

## 2. Family C1 pre-registration draft (crypto)

**Name.** C1: daily Donchian-ensemble trend on Binance USDT-M perps, funded. The spec is a frozen copy of the Zarattini-Pagani-Barbon Combo per coin, plus the corrections the adversarial review required. No parameter is tuned.

**2.1 Universe.** BTCUSDT, ETHUSDT, SOLUSDT. A coin joins the sleeve on the first day it has 360 spot closes: BTC and ETH on 2018-08-12, SOL on 2021-08-06. Spot 1d data starts 2017-08-17 for BTC/ETH and 2020-08-11 for SOL (first open times in the archive files, checked today).

**2.2 Data and import** (all paths checked today in the S3 listing unless marked otherwise)
- **Signals: spot 1d.** `https://data.binance.vision/data/spot/monthly/klines/{SYM}/1d/{SYM}-1d-{YYYY}-{MM}.zip`. BTC and ETH run 2017-08 → 2026-08 (109 files each); SOL runs 2020-08 → 2026-08 (73 files). September 2026 comes from `data/spot/daily/klines/{SYM}/1d/{SYM}-1d-2026-09-{01..30}.zip`. Check each file against its `.CHECKSUM`. **Trap:** spot timestamps are in microseconds from 2025-01-01 onward (binance-public-data README, line 11).
- **Fills before the perp archive: spot 5m.** `data/spot/monthly/klines/{SYM}/5m/{SYM}-5m-{YYYY}-{MM}.zip`, used for 2017-08 → 2019-12. The BTC listing starts 2017-08 (checked). I did not check the ETH 5m listing.
- **Fills and P&L: perp 5m.** Already in the repo as `data/history/binance_um/ohlcv.{SYM}.5m` (split-gz-year-v1, `_source: binance_um_public_archive`). BTC and ETH cover 2020-01-01 → 2026-09-30; SOL covers 2020-09-14 → 2026-09-30.
- **Funding.** Already in the repo as `data/history/binance_um/funding.{SYM}.json.gz`, with fields time, interval_hours and rate. BTC and ETH have 7,395 rows each, SOL 6,700. The source is `data/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-{YYYY}-{MM}.zip`. For pre-2020 funding, use REST `https://fapi.binance.com/fapi/v1/fundingRate?symbol={SYM}&startTime=1567900800000&endTime=1577836799999&limit=1000` (BTC from 2019-09-10, verified upstream).
- **Store location.** Write spot history to a new root such as `data/history/binance_spot/`, with `_source: binance_spot_public_archive` and `market_type: SPOT`. Never write it under `data/history`, because `history_store.resolve()` reads the plain file first and would shadow or collide with the existing spot files.

**2.3 Day boundary.** UTC [00:00, 24:00), 7 days a week, weekends included, with no session or density filter.
- A missing spot 1d bar means no state update that day; report the count.
- A missing 5m fill bar means the fill moves to the next available 5m open.
- P&L days are never dropped.

**2.4 Signal.** For each coin and each n in {5, 10, 20, 30, 60, 90, 150, 250, 360}, with C_t = the spot 1d close of UTC day t:
- Up_n,t = max(C_{t−n+1..t}), Dn_n,t = min(C_{t−n+1..t}), Mid_n,t = (Up + Dn)/2. Today's close is included, as in the paper.
- **Entry.** If flat and C_t = Up_n,t: go long, and set the stop for tomorrow, TS_n,t+1 = Mid_n,t.
- **Exit and ratchet.** If long: exit if C_t < TS_n,t (the stop in force during day t). Otherwise set TS_n,t+1 = max(TS_n,t, Mid_n,t), so the stop never moves down.
- **Weights.** σ_t = SD of the last 90 daily log returns × √365. w_n,t = min(0.25/σ_t, 2.0) × Pos_n,t. Coin target W_t = (1/9) Σ_n w_n,t.

**2.5 Execution.**
- The decision is taken at 00:00 UTC on day t+1. The fill is the open of the 5m bar starting **00:05:00 UTC**, so no trade happens inside 00:00 ± 1 min.
- Fills use the perp 5m bar where perp data exists; before that, the spot 5m bar.
- **Trade rule.** Any sub-model entry or exit trades straight to the target. A volatility-only drift trades only when |W_target − W_held| > 0.20 × W_target. This relative reading is frozen; the absolute reading is never computed.
- **Capital.** Equal capital per eligible coin, re-split at the fill on the first UTC day of each month and when SOL joins. Those re-split trades are charged.

**2.6 Cost model.**
- **Fees:** taker 0.05% per side plus 1 bp slippage per side, on all traded notional. The fee is the repo's assumed VIP-0 rate, not verified at the venue.
- **Funding:** at every realized fundingTime τ, pay rate_τ × q × P_τ, where P_τ is the perp 5m open at τ (a proxy for the mark price). Longs pay when the rate is positive. The 00:00 stamp is paid by the position held *before* the 00:05 fill.
- **Before 2020-01-01:** P&L is on spot. Financing uses REST realized funding where it exists, and otherwise 0.01% per 8h at 00, 08 and 16 UTC on long notional.
- Actual intervals are taken from `interval_hours`, because SOL has 2h and 4h prints.

**2.7 Null and tests.** These are daily-horizon tests, so no time-of-day null is needed.
- **Daily net sleeve return** r_S,d is measured over [00:05 d, 00:05 d+1).
- **Benchmark** r_B,d = the equal-capital same-interval perp return of the eligible coins (spot before the perp archive), with no costs and no funding. This is deliberately conservative: the strategy must beat its own funding.
- **T1 (decision test):** the sleeve's α in r_S = α + β·r_B + ε, one-sided. The decision uses **Newey-West SE with 10 lags**. CR1 by date is also reported. This deviates from the repo default because on a single daily series CR1 by date reduces to White SE and ignores the serial dependence of trend P&L.
- **T2-T4:** the same test per coin, each coin against its own perp return.
- **BH family m = 4, q = 0.10.**
- **Placebo gate.** Circular-shift each coin's nine Pos_n series jointly, by one offset k ~ U{60 … L−60} days shared across coins. Recompute the weights with the σ of the destination date, and recompute fees and funding. Use 1,000 draws with seed 20261003. p_P = (1 + #{α_k ≥ α_obs}) / 1001. The gate passes if p_P ≤ 0.10.

**2.8 Reads.** Each is run once. The simulator runs on data truncated at the read's end and reports statistics for the read window only; positions open at the window's start carry over.

| Read | Window | Days | Status |
|---|---|---|---|
| DISCOVERY | 2018-08-12 → 2022-07-28 | 1,447 | Source in-sample. BTC/ETH are on spot before 2020-01. SOL from 2021-08-06 |
| CONFIRMATION | 2022-07-29 → 2025-03-19 | 965 | Source in-sample |
| EXPOSED | 2025-03-20 → 2026-09-30 | 560 | First data after publication (source sample ends 2025-03-19) |

**2.9 Decision thresholds** (these mirror docs/plans/2026-10-02-edge-f5-preregistration.md:23-26)
- **DISCOVERY.** CANDIDATE if BH rejects T1, the mean net daily return is above 0, and p_P ≤ 0.10.
- **CONFIRMATION.** T1 one-sided p < 0.05; net > 0; net > 0 at 2× slippage; p_P ≤ 0.10.
- **EXPOSED.** T1 one-sided p < 0.10; net > 0.
- **Labels.**
  - VALIDATED: all three reads pass.
  - PROMISING: discovery and confirmation pass, and exposed is net > 0 with p ≥ 0.10. Forward paper monitor only.
  - DEAD: α ≤ 0 in discovery, or α ≤ 0 in confirmation.
  - INCONCLUSIVE: anything else. A null result is always worded "inconclusive at this power".
- **Regime flag.** "Regime-driven" is added to the label if more than 50% of a read's α comes from 3 calendar months or fewer.
- **Single coins.** T2-T4 are secondary. A single coin can be promoted only if T1 is VALIDATED and that coin also passes all three reads.

**2.10 Diagnostics outside the BH family** (reported in every read)
- **N1, Detzel MA arms.** BTC and ETH only. S_L = 1 if C_t > MA_L,t, for L in {5, 10, 20, 50, 100}, held long/flat at 1x, plus the mean E_t. Same execution, costs and funding. These parameters predate 2018, so these arms are the only ones that are fully post-source.
- **N2, owner sizing (1% lost at the stop).**
  - Per-coin open risk = Σ_n (w_n/9) × max(0, (P_fill − TS_n)/P_fill) × capital_i/equity must stay ≤ 1%; otherwise scale all of that coin's w_n down. Total open risk ≤ 3%.
  - Report CAGR, max drawdown, R/yr and months to +10%.
  - Report realized loss divided by planned stop loss per ensemble exit. Stops act on daily closes, so a crash day can cost a multiple of 1%. Also report the worst day.
  - **Deployment gate:** N2 net > 0 in CONFIRMATION and in EXPOSED.
- **N3.** Gross vs net; funding drag by calendar year; 2× slippage.
- **N4.** α by calendar year, and the share of α from the best 3 months.
- **N5.** Daily P&L correlation with H7+G9 via `scripts/research/book_sim.py compare` against `docs/architecture/book-baseline.json`. Each UTC day d maps to the FTMO server day ending at 21:00/22:00 UTC on d; Saturday and Sunday map to the next server day.
- **N6.** α against a funded benchmark (one that also pays funding).

**2.11 Power.** These inputs come from the upstream estimate of the in-sample appraisal ratio (about 1.15 for BTC, about 1.4 at best for the 3-coin sleeve). That estimate assumes BTC vol of about 70%, which is unverified.
- **Full published effect.** Sleeve t ≈ 2.8 / 2.3 / 1.7 across the three reads, so joint pass probability ≈ 0.35-0.40 (BTC alone ≈ 0.21).
- **Half the effect,** net of the 2-5%/yr funding drag: t ≈ 1.4 / 1.1 / 0.9, so joint pass ≈ 0.03.
- The test can confirm an edge close to the published size. It cannot tell a modest real edge from zero.

**2.12 Prior-read disclosures**
- **Source parameters.** The spec's parameters were chosen by the source on 2015-01-01 → 2025-03-19 data. A discovery+confirmation pass may therefore not be called "validated" on its own.
- **What upstream agents read on 2026-10-03:**
  - Realized funding by year: BTC averaged 11.7%/yr, with 30.6% in 2021, 5.1% in 2025 and 2.2% in 2026 YTD. ETH averaged 13.8%/yr and SOL 0.2%/yr.
  - Unconditional SDs: 7-day SD of BTC 8.4%, ETH 11.4%, SOL 15.8%; 1h, 2h and 6h SDs by year.
  - Raw BTC-XAU daily correlation of 0.19.
  - XA2 counts of 10-day-high signals at 16:00 ET, which is close to a Donchian n=10 signal (counts only, no forward returns).
  - H7, G9 and shock trigger counts.
- **Not read by anyone.** No forward return conditioned on a trend signal.
- **Earlier repo crypto work.** ICT and Wyckoff studies on spot data from 2022-08 onward, a different mechanism. The research ledger marks 2023-09-13 → 2026-09-11 as development (`research-ledger.json:128-135`). The window 2026-03-11 → 2026-09-11 was used twice by the criteria-oos6m selection. The 2021-2022 bull and bear regimes are public knowledge.

**2.13 Gates before any read**
- A leakage probe on the signal function, following the pattern of `scripts/tests/test_detector_leakage_probe.py`.
- Unit tests for the stop ratchet, the 20% threshold and funding timing.
- Data QA (missing and duplicate bars, the µs-to-ms conversion) that touches no returns.
- New period ids recorded in the research ledger.

## 3. Family M1 pre-registration draft (CFD, optional)

**3.1 Universe.**
- **US basket (decision test):** US500, US30, USTEC. The signal is built from US500 and the 10-year Treasury yield.
- **Non-US basket:** DE40, FRA40, AUS200, using the same signal with a one-day lag, as in the paper (Sec. 3.5).

**3.2 Data**
- **Prices.** `data/history/ftmo/ohlcv.{SYM}.1D`. US500, USTEC, DE40 and FRA40 start at server day 2017-12-29; US30 and AUS200 at 2019-02-08. The US500 data ends on server day 2026-09-28.
- **Spreads.** `data/history/costs/ftmo/symbolspec.{US500,US30,US100,GER40,FRA40,AUS200}.cash.json`.
- **10-year yield.** FRED DGS10 from `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` (opened today). It goes into a new root with `_source: fred_dgs10`. **PIT lag of 1 business day:** the Fed's H.15 page says the release "is posted daily Monday through Friday at 4:15pm", which is before the 16:55 ET decision.
- **NYSE holiday calendar.** Static and known in advance. The source has **not yet been chosen** and must be pinned in the pre-registration.

**3.3 Day.** The FTMO server day runs 17:00 → 17:00 ET (docs/audits/2026-09-29-ftmo-server-timezone.md). A trade runs from the server-day open (the first quote after the 17:00-18:00 ET break) to the 1D close. Positions are flat across the rollover, so there is no swap and no weekend hold.
- The 1D close is a tick or two later than the 16:55 exit in the source spec. On 2021-09 onward, report the mean difference between the 16:55 exit and the 1D close as a descriptive check.

**3.4 Signal.** T(m) is the last NYSE business day of month m. For each business day t:
- Equity leg: R_E(t) = US500 close(t) / close(T(m−1)) − 1.
- Bond leg: R_B(t) = −8.5 × (y_{t−1} − y_{T(m−1)}) / 100, where y is DGS10 in percent. This duration proxy is an approximation fixed in advance; the paper uses 10-year T-note futures returns.
- Signal: S(t) = 0.6(1+R_E) / (0.6(1+R_E) + 0.4(1+R_B)) − 0.6. This matches the paper's "w − 60%" construction, which I checked in the NBER text today.
- Position s(t) = −sign(S(t)). No trade when S = 0.

**3.5 Events.** For each t in {T−4 … T} (the paper's week4 = Dummy5Days):
- The US members hold s(t) on server day t+1, so the return days are T−3 … T+1.
- The non-US members hold s(t) on server day t+2, so the return days are T−2 … T+2.

**3.6 Costs.** The round trip is the median FTMO hourly relative spread at the entry hour plus the exit hour. Stress uses the p90 spread. There is no swap.

**3.7 Seasonal null and tests.** For each member, use only its week-4 return days and fit the OLS r_d = c + γ·s_d + ε.
- The intercept absorbs the drift of those calendar days, which is the seasonal null. G7's known positive month-end drift is absorbed there and does not count as signal.
- H1: γ > 0, one-sided, with **CR1 clustered by episode (month)**.
- The net gate is mean(s_d·r_d) − cost > 0.
- Tests: T1 = US basket (the decision test), T2 = US500, T3 = US30, T4 = USTEC, T5 = non-US basket. **BH m = 5, q = 0.10.**

**3.8 Reads, by episode month**

| Read | Episodes | Count | Note |
|---|---|---|---|
| DISCOVERY | 2018-01 → 2021-08 | 44 (US30/AUS200 from 2019-03) | Probably unread |
| CONFIRMATION | 2021-09 → 2024-02 | 30 | |
| EXPOSED | 2024-03 → 2026-08 | 30 | 2026-08 is the last complete episode in the repo data |

**3.9 Decision thresholds** (same as F5)
- **DISCOVERY:** BH rejects T1, and net > 0.
- **CONFIRMATION:** p < 0.05, net > 0, and net > 0 at the p90 spread.
- **EXPOSED:** p < 0.10, and net > 0.
- T5 can be promoted only by passing all three reads itself.

**3.10 Diagnostics outside the family**
- The equity-only signal.
- The paper's falsification test: the same rule on non-week-4 days with the same weekday.
- The paper's first-business-day reversal, shown descriptively.
- Return days T−3 … T−1 only, which G7 never read.
- **Owner sizing:** stop = 2.0 × the trailing 20-server-day SD of open-to-close returns (point-in-time), size = 1% / stop. Report the hit rate and the net result. The time exit stays the primary rule.
- Correlation with H7+G9, including crisis months.

**3.11 Power.** US500 open-to-close SD is 114 bp (from the sweep; unconditional, no outcome read).
- MDE at 80% power is about 21 bp in DISCOVERY (one-sided 0.025), about 23 bp in CONFIRMATION and about 20 bp in EXPOSED.
- Joint pass probability is about 0.03 at a true 10 bp, about 0.13 at 15 bp and about 0.4 at 20 bp. The traded effect (sign only, a single index, equity-only) is not reported by the paper.
- The paper itself shows a partial coefficient of 17 bp per one-SD move in the signal.

**3.12 Prior-read disclosures**
- **G7** read days T and T+1 (long, in all reads). Its nets were positive: US500 +4.1 / +9.1 / +6.6 bp (reframes R6(b)).
- **H1** read the 20-day momentum sign on all days in all three reads; momentum won in confirmation. This informs the non-week-4 diagnostic.
- **Dense intraday families** read 2021-09 onward, so CONFIRMATION and EXPOSED are not pristine.
- **Upstream sweep** computed unconditional SDs and episode counts only.
- **Me:** I read the NBER paper text, the H.15 page and the January 1997 head of the DGS10 CSV. That is outside every read window.
- **Gate before reading:** a ledger check that the FTMO daily bars for 2018-01 → 2021-08 were never used to choose anything. If they were, DISCOVERY is relabelled as exposed.

## 4. Queued after C1 (not pre-registered here)

**CRY-H7x.**
- **Rule.** The H7 rule copied verbatim from `docs/plans/2026-10-02-edge-f3-preregistration.md`, with the server day replaced by the UTC day.
- **Tests.**
  - Primary: pooled BTC+ETH(+SOL).
  - G9: a second member, declared non-independent. 76-81% of its trigger days overlap H7's, and 86-90% of those are in the same direction.
  - BH m = 2. Direction fixed at +1; one-sided.
- **Exit and placebo.** Exit at 23:55:00 UTC, before the 00:00 funding stamp. The placebo is matched on entry slot, weekday and MOM20 sign.
- **Data and reads.** Development runs 2017-08-17 → 2024-02-29: spot before 2020, charged perp fees and no funding; perp after. DISCOVERY is the first 60%, CONFIRMATION the last 40%. EXPOSED runs 2024-03-01 → 2026-09-30.
- **Owner sizing.** A stop at the opposite prior-day boundary, as a diagnostic.
- **Power.** BTC DISCOVERY has about 540 trades, with an MDE of about 25-35 bp gross. A gold-sized edge has about a 10-15% chance of surviving all three reads.
- **Data.** Perp 5m is already imported; spot 5m comes from `data/spot/monthly/klines/{SYM}/5m/` (BTC from 2017-08, checked).

**Folded into C1 rather than rejected.**
- CRY-TSMOM-4 becomes arm N1.
- CRY-DON is merged: C1 uses its primary spec, corrected.
- CRY-TSMOM-2 becomes an extension report, run only if C1 is VALIDATED, and judged on what it adds over C1.

## 5. Rejected (one line each)

**Crypto**
- **CRY-TSMOM-2:** the same mechanism as C1; its own source shows that more coins did not raise Sharpe (top-10 1.50 vs BTC-only 1.56); perp history covers only about 2 regimes.
- **CRY-TSMOM-3:** a top-quintile week is almost always a Donchian n=5/10 entry; the effective sample is about 5-8 rallies; expanding quintiles are distorted by changing volatility.
- **SEAS-1 / XA1:** the source's gross (~7.8 bp per trade) is below the 10 bp taker round trip; maker fills cannot be modelled from klines; the DST diagnostic is mis-specified.
- **SEAS-2:** "most return comes overnight" is nearly a tautology (18 of 24 hours plus weekends); the session gate adds a round trip and adverse funding.
- **SEAS-3:** avoiding funding is uneconomic at the threshold; zero BTC/ETH events in the exposed window; the funding estimate (fhat) ignores Binance's linear weights.
- **DF-1:** needs a spot leg (a new venue and API key, i.e. a trust-boundary decision); the whole sample sits inside HMRV's; entry is about 7 SD above the post-2022 mean.
- **DF-2:** the same spot-leg gap; the test is biased by the 0.01%/8h funding pin; only 5-15 effective episodes; carry turned negative in 2025.
- **DF-3:** MDE of 4-5% per week against a plausible effect under 1%; the OI archive was re-uploaded retroactively.
- **DF-4:** MDE of about 1% against plausible tens of bp; OI rows are missing during cascades; there is no USDT-M liquidation history.
- **CRY-G9 (standalone):** the same factor as H7 on crypto; the open anchor means nothing on a 24/7 market. It is kept only as a non-independent member of the queued H7 family.
- **CRY-NSR:** core source not verifiable (paywall); MDE 100-140 bp at 24h; the repo's own shock-fade tests were null or showed continuation.
- **XA2:** power under 15%; the 3×ATR stop binds on 40-65% of trades; weekend funding costs 0.2-0.6% per trade.
- **XA4:** the 12-15 bp hurdle exceeds the 10 bp gap filter; likely a stale-print artifact; testnet cannot validate latency.
- **XA5:** 71 events in total, MDE about 1%; no source definition of the shock.

**CFD**
- **SEAS-4 / XA3:** 42 events since 2022, MDE 0.8-0.9%; practitioner evidence flips sign; the residual after the reopen is unmeasured. Forward-only.

The rest are the CFD sweep's killed classes:
- **Pre-FOMC drift:** decayed after 2015. Forward-only at most.
- **Macro-announcement premium:** it needs about 45 years of data for 80% power.
- **FOMC-cycle even weeks:** the sign flipped in 2017-2021.
- **Market intraday momentum (gamma):** E7 already read that outcome window; no options gamma data.
- **Closing-auction (MOC) imbalance:** no imbalance data; F6 showed continuation.
- **Futures expiry and quad witching:** about 4 events per year, MDE about 48 bp.
- **Options-expiration week:** the effect is relative to small caps, and there is no small-cap leg.
- **Gold around the LBMA auctions:** decayed after the 2015 reform.
- **Gold around COMEX settlement:** no mechanism found.
- **Gold vs real yields or USD:** no point-in-time intraday data, and it loads on the H7 factor.
- **Gold time of day:** no cited directional window.
- **DE40 Xetra closing auction:** no index-level effect found.
- **ECB/RBA announcement days:** no premium for non-Fed central banks.
- **Unconditional overnight drift:** negative after spread, and F6 already read it.
- **Turn-of-month:** G7 is contaminated.
- **Pre-holiday:** no source, and MDE about 32 bp.
- **Harvey Threshold signal:** too close to H1.

## 6. Owner decisions and caveats

1. **Power and protocol.** Under the strict 3-read protocol, both families will most likely end INCONCLUSIVE. Collapsing C1's two in-sample reads into one "replication read" would raise joint power at half effect from about 0.03 to about 0.19, by my arithmetic. Doing that is a protocol change that would have to be decided before any read. I recommend keeping the protocol strict.
2. **DF-1 and DF-2 need a Binance spot account.** That is a new venue and API-key surface, so it is a trust-boundary decision. I do not recommend it now.
3. **The 1%-at-stop rule is not a hard cap here.** C1 exits on daily closes, so gap days can exceed it (that is what N2 measures). Live sizing (`scripts/risk_model.py:135-159`) also leaves fees and slippage out of the 1%. A deployable version needs stop orders placed on the exchange, which makes it a different strategy, and its forward test must use mainnet prices.
4. **FTMO relevance of crypto results.** FTMO's crypto CFDs and their costs are not in the repo and I have not verified them. A validated C1 would be a Binance book, not an FTMO book.
5. **Value of delay.** The owner does not know what a month of delay is worth. So the plan runs the historical reads first, which involve no calendar wait, and keeps forward monitors only for items 4-6.

## 7. Sources and evidence

**Checked by me on 2026-10-03**
- **Archive listings** (`https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=...`):
  - spot 1d BTC/ETH from 2017-08 and SOL from 2020-08;
  - spot 5m BTC from 2017-08;
  - perp 1d BTC 2020-01 → 2026-09;
  - SOL fundingRate 2020-09 → 2026-09;
  - spot daily files for 2026-09.
- **First open times:** 1502928000000 (2017-08-17) and 1597104000000 (2020-08-11).
- **Microsecond note:** https://raw.githubusercontent.com/binance/binance-public-data/master/README.md, line 11.
- **NBER w33554:** https://www.nber.org/system/files/working_papers/w33554/w33554.pdf. Confirmed:
  - the sample 1997-09-10 → 2023-03-17;
  - predictability "peaks in the last four days"; week4 = Dummy5Days; Calendar × week4 coefficient −0.30***;
  - one-day lag for international markets;
  - "results become even stronger" through 2025;
  - the strategy and reversal definitions.
- **Zarattini-Pagani-Barbon:** text extracted from https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf. Confirmed the initial midpoint stop, the 25% target, the 200% cap, the 20% threshold applied only to vol-driven rebalancing, and the sample 2015-01-01 → 2025-03-19.
- **H.15 release time (4:15pm):** https://www.federalreserve.gov/releases/h15/.
- **DGS10 CSV** opened.
- **Repo files:** `docs/plans/2026-10-02-edge-f5-preregistration.md:19-26`, `docs/plans/2026-10-03-reframes.md:185-215`, `docs/architecture/research-ledger.json:128-135`, the FTMO 1D coverage, and `data/history/binance_um/*`.

**Verified by the upstream verdict agents, not re-opened by me.** Hudson-Urquhart, Liu-Tsyvinski, Detzel et al., HMRV, BIS WP 1087, the Binance funding FAQ, Kang-Ryu, Quantpedia, Corbet et al., Caporale-Plastun, Mourey et al., and the other URLs in the input. The upstream funding statistics, SDs and counts also come from them.

**Scratch files** (not in the repo), in `/private/tmp/claude-502/-Users-tungnguyen-TYME-Trading/9b9e48dc-3fc7-4a18-97de-5505cf66a3b3/scratchpad/`: `hmm33554.txt`, `h15.txt`, and `synth/*.zip`, which hold first-row timestamps only.