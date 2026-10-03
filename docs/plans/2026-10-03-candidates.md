# Candidates after the reframes (deliverable B, 2026-10-03)

Follows docs/plans/2026-10-03-reframes.md and its agreed debate outcome (§9): two separate tables -- (A) policy levers on the
edges that survive point-in-time measurement, (B) new return DRIVERS inside the allowlist (docs/architecture/instruments.json
execution list) -- because a lever on the same driver and a new driver are not comparable (round B). Both are ranked by the
agreed arbiter: **expected change of E[net payouts - fees] over 12 months, at the measured edge AND at a 50 % haircut**,
with every gain that comes from variance rather than edge labelled as such. The numbers below are priors and synthetic
hints, not results.

**The base changed during this session.** docs/audits/2026-10-03-e5-lookahead-erratum.md: E5's research selection was
look-ahead; under the executor's point-in-time selection E5 has no edge. The honest base is H7 + G9 gold (one factor,
daily Sharpe ~0.96 on active days, funded <= 122 d ~0.01-0.04, funded eventually ~0.78 of 2024+ starts, median ~246 days;
docs/audits/2026-10-03-e5-live-fill-posthoc.json) or v2 as executed (~0.07-0.10, from variance, fails 11-15 %). That makes
a second driver worth more than any lever.

**Update after the F6 / F7 discovery read (docs/audits/2026-10-03-edge-f6-discovery.md): B1 and B2 are NULL** (0 of 16
candidates; every excess z negative -- the night after a sell-off CONTINUES on these CFDs; gold's null is informative, MDE
5-11 bp). The honest base (H7 + G9 gold, span 2021-10 -> 2026-09) runs at an annual Sharpe of ~0.86 and ~12 %/yr volatility
at 1 % per trade (per weekday, zero days included; [post hoc] arithmetic on already-read trades). Consequences: (1) inside the
allowlist, no bar-based independent driver is left with a mechanism and a prior worth a pre-registration (B3-B5 are weak);
(2) the largest MEASURABLE improvement is A1 on the honest base -- leverage on a driver that survived three reads, to be
labelled as such; (3) the next real driver needs a new asset class (forex: correlation test first) or new data (a historical
event calendar for B5 / B7).

## A. Policy levers on point-in-time edges

| rank | lever | mechanism | evidence so far | correlation with base | cheapest falsification test | status |
|---|---|---|---|---|---|---|
| A1 | phase-aware volatility via stop width (k_P1, k_P2), dd3 kept | the base sits below the speed-optimal volatility; Phase 2's +5 % / -10 % barriers tolerate more | synthetic, Sharpe 1.0 + dd3: funded <= 87 wd 0.08 at 12 %/yr, 0.23 at 18 %, 0.31 at 22 % (fail 0-5 %); a x1.5 Phase-2 boost adds +0.03-0.05 at today's vol | same driver (~1) | pass_policy machinery + a funded-stage replay on the PIT base, 6 policies | **pre-registered**: docs/plans/2026-10-03-vol-schedule-preregistration.md; runs after the owner's E5 decision |
| A2 | drop E5: v3 = H7 + G9 gold | honesty, not speed | erratum §5 | -- | none needed | owner decision |
| A3 | one account vs two once a 2nd driver exists | below optimal vol combine; at optimal vol split | synthetic (reframes R5) | -- | needs a B survivor | waits on B |
| A4 | a challenge-phase risk ceiling different from the funded one | a failed challenge costs a fee, a lost funded account costs the payout stream | reframes R1 | -- | not research: CLAUDE.md §34 default, owner | owner question |
| A5 | retry policy under the value objective | fees per attempt priced, not forbidden | pass_policy: irrelevant while fails ~0 | -- | part of A1's replay | inside A1 |

## B. New drivers inside the allowlist

| rank | candidate | mechanism (why it should pay) | instruments | data, PIT | expected corr. with base | prior / power | cheapest falsification test |
|---|---|---|---|---|---|---|---|
| ~~B1~~ NULL | **F6: overnight reversal after a US cash-session sell-off** -- long from 19:00 New York to 09:00 Berlin (W1) or 09:30 New York (W2), same server day, no swap | dealers absorb end-of-day selling and are paid to hold it until liquidity arrives (Asia, Europe); sell-offs reverse much more than rallies (Boyarchenko, Larsen, Whelan, RFS 2023; NY Fed SR 917). The paper's UNCONDITIONAL 02:00-03:00 ET window loses after the bid-ask spread -- only the conditional version is a candidate | US500, US30, USTEC | dense 5m: US30 2019-02+, US500 / USTEC 2021-09+; hourly median + p90 spread recording | low (other asset, other hours, counter-trend) | moderate prior; LOW power on US500 / USTEC discovery (~60-130 events) | **pre-registered**: docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md; discovery read implemented (`scripts/research/edge_f6.py`) |
| ~~B2~~ NULL | **F7: the same mechanism on XAUUSD** (US-session gold sell-off -> long overnight) | generic inventory / immediacy premium (Grossman-Miller); no gold-specific published evidence that I know of | XAUUSD | 5m 2004+ (22 years: real power) | likely <= 0 (counter-trend to H7 / G9, other hours) | low-moderate prior, high power | **pre-registered**: docs/plans/2026-10-03-edge-f7-gold-overnight-reversal-preregistration.md; same code |
| B3 | index relative value: US30 vs USTEC vs US500 intraday divergence reversal | transient sector-flow dislocations between price-weighted and cap-weighted indices | US30, USTEC, US500 | 5m 2021-09+ | ~0 (market neutral) | weak prior; two spreads per trade; needs a two-leg executor | next-2 h spread return after a 2 sigma divergence, net of two spreads |
| B4 | Binance BTCUSDT weekend move -> Monday open of USTEC / US500 | risk-sentiment transmission while equity CFDs are closed (data source != venue, CLAUDE.md §4) | USTEC, US500 (signal from BTCUSDT) | BTCUSDT 1H 2022-09+ (~200 Mondays) | low | weak prior, low power | sign of Fri-close -> Sun-close BTC return vs the first US-index hour on Monday |
| B5 | FOMC pre-announcement drift (Lucca-Moench 2015) | pre-announcement risk premium | US500, US30, USTEC | needs the public FOMC schedule (PIT: published a year ahead; not in the repo) | low | 8 events / yr; reported weakening after publication (not verified here) | long the FOMC day open -> 14:00 ET |
| B6 | calendar effects (turn of month, month end, pre-holiday) with a calendar null | flows | indices | history CONTAMINATED (G7 / H2 read): forward only | low | 12-48 events / yr forward -> years | forward pre-registration only (round A: no re-read of read data) |
| B7 | post-release drift after HIGH US releases | slow digestion | indices, gold | NO historical calendar in the repo (event-calendar.json is a 2026 snapshot) | low | unknown | blocked on data |
| B8 | gold time-of-day seasonality under a seasonal null | none specific | XAUUSD | 2004+ | unknown | 24-hour mining risk without a mechanism | only with one window fixed from a cited source; none in hand |
| B9 | E5 with point-in-time selection (30-min metals continuation) | residual of the FVG retrace | XAUUSD | read | -- | excess z ~0.02 at -2 bp net (erratum §2) | dead on cost; listed to close the loop |
| -- | forex (OUTSIDE the allowlist) | a different macro driver | FX | no FX history in the repo | **not automatically low**: XAUUSD is partly a USD trade | owner decision | first test: daily correlation of FX trend streams with the gold book; prefer non-USD crosses |

## Experiment budget (this session, cumulative)

| item | market-data reads | status |
|---|---|---|
| reframes synthetic study | 0 | design |
| Test #1 E5 live fill | 1 pre-registered descriptive check (3 rules x 3 spreads x 2 components) + 3 post-hoc diagnostics | EXPOSED data |
| census PIT re-run | re-measure of the 40 census tests (34 unchanged, 6 E5 rows changed) | EXPOSED (development window) |
| F6 discovery | 12 tests, 0 candidates | discovery window only; family closed |
| F7 discovery | 4 tests, 0 candidates | discovery window only; family closed |
| A1 vol schedule | 6 policies | not run (waits on the owner's E5 decision) |
