# Family H7x -- the gold intraday-trend rules (H7, G9) transferred to crypto perps -- pre-registration (2026-10-03)

**Committed BEFORE any read of H7x outcomes.** Code: `scripts/research/edge_h7x.py`; tests: `scripts/tests/test_edge_h7x.py`
(hand-built bars) and the detector leakage probe. Origin: docs/plans/2026-10-03-crypto-cfd-design.md (rank 3; critic
corrections applied). Question: does the ONLY robust edge this repo has found (intraday trend continuation on gold, H7 / G9)
exist on BTC / ETH / SOL? The parameters come from gold, not from crypto data: a clean transfer test.

## 1. Rules (UTC day 00:00 -> 24:00; direction FIXED = continuation; one-sided)

- **H7x** (F3's H7, verbatim with the FTMO server day replaced by the UTC day): the first 5m bar of UTC day D whose close is
  above the previous complete UTC day's high (below its low) when MOM20 > 0 (< 0); MOM20 = the close of the last bar of D-1 /
  the close of the last bar of the 21st previous complete UTC day - 1 (20 UTC days, about 2.9 calendar weeks on a 7-day market,
  vs about 4 weeks on gold -- kept literal, not tuned). Long (short) in the breakout's direction.
- **G9x** (F4's G9 with the UTC open): the first 5m close beyond open(D) +/- 0.5 x the previous complete UTC day's range;
  either side; continuation. Declared NON-independent of H7x (the design workflow counted 76-81 % shared trigger days).
- Entry: the OPEN of the next 5m bar. Exit: the OPEN of the 23:55 UTC bar (strictly before the 00:00 funding stamp: no funding).
  A signal whose entry bar opens at or after 23:55 is not an event. One event per (symbol, day) per rule.
- Point-in-time completeness: day D is excluded only when D-1 or the MOM20 / range lookback is incomplete (fewer than 288
  bars), never because of bars missing AFTER the signal (then: exit at the last available open before 23:55).

## Amendment [H7x-A1] (2026-10-04, before any read, outcome-blind)

(1) §1 "no funding" was WRONG: Binance USDT-M settles funding at 00/08/16 UTC (and every 2 h on some SOL days), so an intraday
trade crosses settlements. A perp-era trade (entry >= 2020-01-01T00:00Z) pays side x rate_tau, a fraction of the entry
notional (longs pay a positive rate), for every settlement tau in `data/history/binance_um/funding.{SYM}.json.gz` with
entry_time <= tau < exit_time. cost = 12 bp + funding; stress = 14 bp + funding; spot era: no funding. Owner sizing pays the
settlements before its stop fill; the MOM20 comparator pays its own slot-matched funding; a read refuses if any perp-era
trade lacks funding coverage. (2) 2020-01-01, the spot -> perp switch day, is not eligible; MOM20 and sigma for the following
~20 days mix venues (disclosed and counted). (3) A complete day has exactly 288 distinct on-grid 5m bars. T1, T2 and BH are
unchanged. Report-only additions: a leave-own-day-out placebo; trade rows in the read JSON.
§6 note: the "138 per coin-year" figure was counted on 1H closes; the rule fires on the first 5m close. Outcome-blind dry-run
5m counts: discovery H7x 1,377 / G9x 2,010; confirmation 1,258 / 1,901; exposed 1,263 / 1,926 (pooled).
Found by an adversarial reviewer of the implementation (design workflow `implement-c1-m1-h7x`); the error was mine.

## 2. Data and periods

- BTCUSDT, ETHUSDT: Binance SPOT 5m 2017-08-17 -> 2019-12-31 (`data/history/binance_spot`), PERP 5m from 2020-01-01
  (`data/history/binance_um`); SOLUSDT: perp 5m from 2020-09-14. Spot bars before 2020 are charged perp fees, no funding.
- DEVELOPMENT 2017-08-17 -> 2024-02-29: DISCOVERY = the first 60 % of its calendar days, **2017-08-17 -> 2021-07-18**;
  CONFIRMATION 2021-07-19 -> 2024-02-29. EXPOSED 2024-03-01 -> 2026-09-30. Each read ONCE, in order, each in its own commit.

## 3. Measurement

- Return r = side x (O(exit) / O(entry) - 1). Cost: taker 0.05 % per side + 1 bp slippage per side (12 bp round trip);
  stress: 2x slippage (14 bp).
- Placebo (matched, so that plain crypto drift and time-series momentum are not credited to the breakout): the mean return,
  from the same entry 5m slot to the 23:55 exit, over every eligible day of the same period with the same weekday and the same
  MOM20 sign, signed by the trade's side. excess = r - placebo; scale = sigma_5m x sqrt(bars held) (sigma from the previous
  20 complete UTC days).
- Statistics: `edge_census.summarise` (CR1 by UTC date). **Primary tests are POOLED over the three coins** (their intraday
  moves co-move; per-symbol tests would triple the multiplicity for little independent evidence): T1 = H7x pooled,
  T2 = G9x pooled. **BH m = 2, q = 0.10** on the DISCOVERY one-sided p of the excess z. Per-symbol rows are reported only.

## 4. Decision rule

DISCOVERY -- CANDIDATE iff BH rejects it and mean net > 0. CONFIRMATION -- one-sided p < 0.05, net > 0, net > 0 at 2x
slippage. EXPOSED -- one-sided p < 0.10, net > 0. Zero survivors is a valid result ("not found at this power").

## 5. Diagnostics (outside the family)

- Owner sizing: stop at the opposite prior-day boundary (previous low for a long, high for a short), size so the loss at the
  stop = 1 % of equity; report R per trade, stop share, gap-through (R < -1.05) and the worst trade.
- H1-crypto comparator: MOM20 sign alone, traded from the same slot to 23:55 on every eligible day; H7x must beat it to mean
  anything beyond time-series momentum.
- Daily P&L correlation with fvg-book v3 (H7 + G9 gold) on the read's dates (UTC day -> the FTMO server day ending that day).
- Raw net returns per symbol and per year.

## 6. Power (stated before reading)

About 138 H7 triggers per coin-year (design workflow, counts only). BTC DISCOVERY (with spot from 2017) about 540 trades; per-
trade noise 190-260 bp (BTC) -> MDE about 25-35 bp gross for BTC alone; pooling helps less than 3x (co-movement). A gold-sized
edge (excess z ~0.1 per trade) has about a 10-15 % chance of surviving all three reads; costs of 12 bp are ~0.05-0.075 SD per
trade, most of a gold-sized edge. A null is "not found at this power".

## 7. Prior reads (disclosed)

- The design workflow counted H7 / G9 / shock triggers on the local 1H spot data 2022-09 -> 2026-09 and their overlap and
  direction agreement -- counts only, no post-trigger return.
- Earlier repo crypto work (ICT / Wyckoff, spot 2022-08 ->; research-ledger `crypto-history-2023-2026` = development) read
  the same bars for other mechanisms.
- Corbet et al. (Bitfinex 1-min, 2014-2018) report trading-range-break returns that "do not provide support" after
  correction; Caporale & Plastun report positive 2-sigma breakout returns without costs -- mixed literature, not chosen for.
