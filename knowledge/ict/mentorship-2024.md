# ICT Mentorship 2024 — objects absent from TTrades Core A/B and Models

**Provenance.** Synthesised from `docs/Mentorship 2024.pdf` — 21 lectures over 20 pages. Citations below are
`M L<n>` where `n` is the lecture number, which is more stable than a PDF page. Ingested 2026-09-17.

**Why this file exists.** `knowledge/ict/core-a.md`, `knowledge/ict/core-b.md` and `knowledge/ict/models.md`
cover the TTrades decks. This deck is a different source and carries objects those three do not: `core-a.md`
§7 explicitly lists NDOG and NWOG as **not in source**, and ORG/RTH, BPR, the Rejection Block, the Event
Horizon PD array, MMBM/MMSM as a *model*, the "Mohawk", 15-second precision and equity-curve psychology are
absent from all three. Only what they lack is recorded here; nothing is restated.

---

## 0. SCOPE — READ BEFORE USING ANY OBJECT BELOW

**This deck is CME index futures, New York session, US Eastern time.** Its own numbers say so: ES 5-handle and
NQ 15-handle targets (`M L10`), the 9:30 RTH open, 8:30 news, the 16:59 settlement → 18:00 reopen cycle
(`M L3`), an Asian range of 19:00–21:00 (`M L1`). Every one of those is an instrument- or venue-specific fact.

**The Opening-Gap family requires a session discontinuity.** NDOG, NWOG, ORG and their consequent encroachments
are defined as the price range *between one session's close and the next session's open*. That range only
exists where trading stops and restarts.

| Market | Does the gap object exist? | Why |
|---|---|---|
| **crypto** (BTCUSDT, ETHUSDT, …) | **NO** | Spot and perp trade 24/7. There is no close and no reopen, so there is no gap, no gap midpoint, and nothing to encroach. The 00:00 UTC daily boundary is a *label on a continuous tape*, not a discontinuity: it has no CE because there is no range. |
| **cfd** (XAUUSD, XAGUSD, USOIL, UKOIL) | **YES** | The broker's daily break and the weekend close both produce a real discontinuity. |
| **forex** (the 7 majors, added 2026-09-17) | **YES** | Friday close → Sunday 17:00 ET reopen is the canonical weekend gap; NWOG is at home here. |

Applying an Opening-Gap level to a 24/7 crypto chart would mean **inventing a price level from no data** — the
failure `docs/architecture/data-sources.md` and the hard safety rules exist to prevent. Do not do it, and do
not "approximate" it with the daily open.

**Time-of-day objects carry lower authority off their home market.** The killzone treatment in
`knowledge/ict/core-a.md` §2.1 already records that the decks give two EST session sets and no rule for
crypto or CFD, which is why this system uses its own `docs/architecture/session-model.md` parameters instead.
Everything in §6 below inherits that caveat.

**No number from this deck is adopted as a system parameter.** The 30-handle threshold (§2), the ES 5 / NQ 15
handle targets (`M L10`) and the −1 STDEV objective (§12) are instrument-specific to ES and NQ. They are
recorded here as *what the source says* and are deliberately **not** ported into
`docs/architecture/analysis-params.json`; a handle count on NQ has no meaning on BTCUSDT or EURUSD.

---

## 1. NDOG and NWOG — New Day / New Week Opening Gap

- **NDOG** (`M L3`): the range between the **16:59 settlement price** and the **18:00 reopen price** of the
  following session. The most recent **5 days** are kept on the chart.
- **NWOG** (`M L3`): the range between **Friday 16:59** and **Sunday 18:00**. The most recent **5 weeks** are
  kept.
- Both are treated as PD arrays: price is expected to react at the boundaries and at the midpoint.
- Both are **support and resistance in both directions** — an unfilled gap above is a draw on liquidity, and
  the same gap, once traded through, becomes the level price respects from the other side.

## 2. ORG — Opening Range Gap, and the 30-handle condition

- **ORG** (`M L10`, `M L15`): the gap between the prior session's close and the RTH open at **9:30**, divided
  into **quadrants** (25 % / 50 % / 75 %). The last **3 days** of ORGs are kept.
- The statistic the source actually gives is **conditional**: when the gap exceeds **30 handles**, the
  consequent encroachment is reached before 10:00 roughly **70 %** of the time (`M L18`). Stated without that
  condition the figure is not what the deck claims — this is one of the two corrections applied while ingesting
  a third-party summary of this deck.

## 3. CE — consequent encroachment, generalised

`knowledge/ict/core-a.md` treats the midpoint mainly for FVGs. This deck applies **CE = the 50 % level of
*any* gap-like range** (`M L3`): FVG, volume imbalance, NDOG, NWOG, ORG, and the body-to-wick span of a single
candle. The CE is where a retracement is expected to be respected or rejected; failure to hold it is
information, not noise.

## 4. Smooth vs rough edges

Relative equal highs/lows are graded (`M L1`, `M L2`, `M L4`):

- **Smooth** — a run of near-identical highs or lows. Reads as *engineered* liquidity: resting stops, a likely
  target for a sweep.
- **Rough** — ragged, uneven extremes. Weaker as a draw; less likely to be the reason price travels.

This is a *quality* judgement on a liquidity pool, which the TTrades liquidity material does not make.

## 5. The two First-FVG objects — do not merge them

The deck defines two different objects that both involve "the first FVG", and conflating them loses the
signal. This is the second correction applied during ingestion.

| Object | Where | What it means |
|---|---|---|
| The first FVG **before** the stop hunt | `M L2` | When price runs the stop and then trades back through this FVG, it becomes an **inversion** FVG, and that inversion is the **CISD signal** — evidence the move was a raid, not a trend. |
| The first FVG **after** 9:30 / after liquidity is taken | `M L8`, `M L18` | An **entry** setup: the retracement into it is the trade location. |

The first is a *read* about intent; the second is an *execution* level. One cannot substitute for the other.

## 6. Time precision, and the post-news window

- The deck works the **7:00, 8:00 and 9:00 EST 30-minute intervals** (`M L1`, `M L2`) and uses a
  **15-second chart** for entry timing (`M L2`) — finer than anything in the TTrades material or in this
  system, whose lowest scanned rung is 15m (`docs/architecture/timeframe-mapping.md`).
- **10:00–11:00 ET is named as a positive selection window** (`M L7`) — after the 8:30/9:30 news reaction has
  resolved. This is the inverse of a blackout rule: not "avoid news", but "trade the hour *after* it".
  Compare `scripts/strategy-runner.py`'s event blackout, which only knows how to *exclude* a window.

## 7. BPR — Balanced Price Range

`M L11`: where a bullish FVG and a bearish FVG **overlap**, the overlap is the BPR. It acts as a single
higher-confidence PD array because both sides have unfilled inefficiency in the same price band.

## 8. Rejection Block, and the CISD nullification rule

- **Rejection Block** (`M L14`): built from the **wicks** rather than the bodies — the zone a series of long
  wicks refused.
- **The invalidation rule** (`M L14`, load-bearing): when a rejection block and a CISD have both occurred,
  price **should not retrace back into the rejection block**. If it does, that **nullifies the order block and
  invalidates the trade.**

That last sentence is an *invalidation* condition stated by a source, which is rare and directly relevant to
`/invalidate` and `/exit`: this system requires every trade to name what would prove it wrong.

## 9. Event Horizon PD array

`M L16`: a PD array anchored on a prior high-impact event, with a lookback of **no more than ~60 days**. Beyond
that the level is treated as stale. An explicit expiry on a level's authority — which the TTrades material does
not give.

## 10. Turtle Soup inside the Market Maker Buy/Sell Model

`M L8`: **Turtle Soup** (the false breakout of a prior extreme) is placed as the *entry trigger* inside the
larger **MMBM / MMSM** structure — accumulation → manipulation (the soup) → distribution. `models.md` carries
the TTrades models but not MMBM/MMSM as a model in its own right.

## 11. OLHC / OHLC and IOFED

`M L12`: candle-shape reading — whether a candle opened at its low and closed at its high (OLHC) or the
reverse — used to judge delivery direction within the bar, together with **IOFED** (institutional order-flow
entry drill), the retracement entry into the last unfilled inefficiency in the direction of delivery.

## 12. STDEV measured moves

`M L5`: projected standard deviations of the manipulation leg as **targets**, with **−1 STDEV** called out as
the "low-hanging fruit" — the first, highest-probability objective. Handle-denominated on ES/NQ and therefore
not adopted numerically (see §0).

## 13. Minimum-threshold concept, and "Mohawk"

- A **minimum threshold** a setup must clear before it is taken at all (`M L18`) — the deck's own equivalent of
  a score floor.
- **"Mohawk"** (`M L18`): the deck's name for the tall, isolated candle profile left by a violent liquidity
  raid. Vocabulary, recorded so the term is recognisable, not a rule.

## 14. Ideal FVG Delivery

`M L17`: the sequence of how a *textbook* FVG is delivered — the shape a clean retracement-and-continuation
takes — used as a template to grade real ones against.

## 15. PDH/PDL remain valid after being run

`M L19`: a previous-day high or low that has already been swept **does not stop being a level**. It continues
to act as support/resistance afterwards. Worth stating because the natural assumption is that a level is
"used up" once taken.

## 16. Multi-day event caution

`M L14`, `M L21`: stand aside around **Jackson Hole (all three days)**, on **Fridays**, and **before
holidays**. A calendar-shaped caution broader than a single news timestamp — and broader than what
`scripts/strategy-runner.py` currently implements, which is a fixed ±30 minutes around one event.

## 17. Process and psychology

`M L1`, `M L6`, `M L7`, `M L13`, `M L14`: one setup traded well beats many; journal every trade; the equity
curve is the feedback signal, not the last trade; do not chase a missed move. Recorded as the source's own
framing. This system already enforces the mechanical half of it — a fixed risk fraction, a planned-R:R floor,
a required invalidation level — which is what makes the psychological half unnecessary to enforce by will.
