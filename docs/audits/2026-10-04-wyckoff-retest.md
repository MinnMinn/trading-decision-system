# Wyckoff re-test -- results (2026-10-04)

Owner, 2026-10-04: "Tao không tin một phương pháp nổi tiếng (Wyckoff) lại không có bất kì một kết quả tốt nào."

Sources:
- Pre-registration: docs/plans/2026-10-04-wyckoff-retest-preregistration.md [WY-P1], sealed at c0d6ccb before any outcome
  read.
- Records, each read once: docs/experiments/wyckoff-retest-2026-10-04/ (R1, V, L1, 13 ablation arms, reports) and the R0
  counts docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json.
- Code: scripts/research/edge_wyckoff.py, scripts/research/wyckoff_ablation.py.

What was tested: the books' mechanical core, read on price only (§3), point in time (truncation probe: 200 events, 0
violations), against a same-geometry placebo, net of real FTMO cost (server-hour frame). A real-volume family V used
Binance 2017-2022, and every engine defect documented earlier was ablated one at a time.

## Verdicts

| cell | n | net excess (R per trade) | verdict |
|---|---|---|---|
| W-C-long-15m: Spring / Shakeout, long | 63 | +0.25 (p = 0.18; 95 % upper bound +0.72) | **INCONCLUSIVE** |
| W-D-15m: Phase-D BU / LPS | 167 | -0.11 (upper bound +0.005) | **NO MECHANICAL EDGE** (>= 0.20R excluded) |
| W-D-1H | 78 | +0.06 (upper bound +0.19) | **NO MECHANICAL EDGE** |
| W-CAMP: the full campaign (Spring + Test + LPS thirds) | 97 | -0.54 | **AGAINST THE BOOK** |
| V2: Phase-D on real volume (crypto) | 94 | net -0.14 | **AGAINST THE BOOK** |
| V4: effort vs result on real volume | 5,532 | net -0.56 (gross +0.05) | **AGAINST THE BOOK** |
| L1: the DE40 / US500 15m lead, exposed years, 6 indices | 107 | net -0.22 | **FAIL, closed** |

Descriptive only (fewer than 30 events, or not confirmatory):

| item | result |
|---|---|
| W-C-long-1H | -0.42 (n 26) |
| W-C-long-4H | -0.70 (n 5) |
| W-D-4H | -0.19 (n 29) |
| W-CTX | -0.34 (n 18) |
| Upthrust / UTAD shorts, 15m / 1H / 4H | -0.22 / -0.50 / -0.56 |
| V1 (Spring on real volume) | +0.07 net (n 25) |

Within W-C-long-15m: the Shakeouts were +0.64 (n 14) and the Springs +0.26 (n 49). Against the point-in-time sweep
control (G-C, n ≈ 7,500), Wyckoff added +0.31R (p = 0.12).

**Closing rule:** not met. W-C-long-15m is inconclusive, and family V cannot close at its power. As the sealing record stated
before any read, a null here means "no LARGE edge found", not "Wyckoff has no edge".

## Engine ablation (descriptive, development window; ablation-report.md)

The book-faithful engine (ENGINE-BOOK), net excess per trade:

| leg | 15m | 1H | 4H |
|---|---|---|---|
| Spring | -0.13 (n 1,069) | -0.23 | -0.30 |
| Phase D | -0.09 (n 693) | -0.22 | -0.29 |

No single change makes it positive. That covers trading the Shakeouts, the R:R floor, the book's targets, a 600-bar window,
the stop, hour-normalised volume, the fill price and flattening before the rollover.

The one positive pocket is the arm that ADDS the ICT higher-timeframe gate. On 15m springs it gives +0.18 (n 162), but it is
one of 78 descriptive cells, found after the fact.

## What this means

1. Read as fixed, point-in-time rules on the FTMO CFDs (and on crypto with real volume), Wyckoff shows no edge of practical
   size. The Phase-D entries and the full campaign are excluded or worse. The one open cell, the 15m Spring / Shakeout long,
   is positive but small-sample: about +0.25R, 63 trades.
2. This does not test a discretionary Wyckoff trader. Reading context, scale and judgement is outside any mechanical rule.
3. The only way to settle the open cell is forward data (§4 R4). The pre-registration runs R4 only for survivors, and an
   inconclusive cell is not a survivor. Forward collection for W-C-long-15m would need an owner decision and its own
   pre-registered forward rule.
