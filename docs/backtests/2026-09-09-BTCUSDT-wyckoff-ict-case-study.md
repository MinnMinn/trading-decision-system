# BTCUSDT Wyckoff + ICT Case Study — historical validation (n=1)

**Purpose:** requested as part of "test Stage 1 until good enough for Stage 2." This is a real historical case study against genuine Binance data (not mock, not live-forward), using the Wyckoff + ICT dimensions only (Footprint/Heatmap still unavailable — no CoinGlass key yet). **Read the "What this is NOT" section before drawing conclusions from it.**

Data: `data/live/market-data/ohlcv.BTCUSDT.1D.json` (120 days, fetched live) and `ohlcv.BTCUSDT.4H.json` (33 days). Swing points and volume outliers were found programmatically (pivot detection + volume-outlier scan), not eyeballed — reduces (but doesn't eliminate) cherry-picking risk. See methodology note at the end.

---

## 1. Macro Wyckoff read (Daily, 120 days)

| Date | Event | Evidence |
|---|---|---|
| May 13–21 | Distribution top | Series of lower swing highs: 81,664 → 78,200 → 78,080 |
| Jun 2–5 | **Markdown / Selling Climax** | Jun 5: vol 55,027 (largest of the entire 120-day dataset), range 4,847, low 59,131 — textbook SC |
| Jun 14 | Automatic Rally | Bounce to 65,746 off the SC low |
| Jun 24–25, Jul 1 | **Secondary Test, undercutting the SC low** | Jun25 low 58,115 and Jul1 low 57,800, both below the Jun5 SC low (59,131) but on *declining* trend of volume relative to the climax itself — the marginal-undercut-then-hold pattern that precedes real accumulation |
| Jul 13 – Aug 16 | **Cause-building (accumulation range)** | Tightening range 61,825–66,956; notably low volume on the Aug 1 low (7,563 — well under the 16,478 daily average), consistent with genuine seller exhaustion |
| Aug 17–21 | **Sign of Strength (SOS)** | Aug 20 (vol 35,905) and Aug 21 (vol 44,340 — 2nd-largest of the dataset) break the entire multi-month range high (66,956) with matching effort and result — clean SOS |
| Aug 21 – Sep 9 | **Reaccumulation at a new, higher range** | See worked example below |

*Label sourcing note:* the event labels above (Selling Climax, Automatic Rally, Secondary Test, Sign of Strength) are classic Wyckoff-Advance schematic vocabulary — general market knowledge, **not** sourced from `knowledge/07-wyckoff-and-modern-tools.md`, whose §2.5 and §8 state that book deliberately omits PS/SC/AR/ST/SOS/LPS/UT/UTAD from its prose and declines to redefine them. Only the Spring/Upthrust typing (§2.6–2.7), Trading Range (§2.4) and phase structure (§2.5) claims in this document are grounded in the ingested corpus.

## 2. Worked example: the Aug 28 – Sep 2 Spring, with real outcome

### Setup identification (Wyckoff)
Three touches of a declining support level, each with same-bar recovery:

| Bar (4H) | Low | Close | Note |
|---|---|---|---|
| Aug 28 16:00 | 76,888 | 77,580 | First test |
| Sep 1 16:00 | 76,420 | 77,312 | Marginal new low, recovers |
| **Sep 2 08:00** | **76,264** | **76,829** | Deepest low, clear same-bar rejection off the low |

This matches the book's own **Spring Type 2** description almost exactly (`knowledge/07` §2.6): moderate-volume break of support, quick reclaim, market retests the broken level more than once before the real move. Wyckoff dimension score: phase clarity 7/8 (reaccumulation inside an already-confirmed bullish macro structure), Spring type & quality 9/10 (clean 3-touch pattern), Effort-vs-Result 6/7 (the eventual breakout bar, Sep 3 12:00, prints vol 7,602 — more than double any neighboring bar — with a matching huge result, high 81,370 from an open of 77,948). **Wyckoff: 22/25.**

### Setup confirmation (ICT)
The same three touches read as a **liquidity sweep** of resting sell-side stops below each prior low (IRL grab / "Turtle Soup" pattern) — a different theoretical lens on the same price action, not a restatement of the Wyckoff read (independence check: legitimate, since ICT and Wyckoff are genuinely separate methodologies even when citing the same swept level). HTF bias: the Aug 21 SOS is a confirmed bullish structural break (BOS above the prior 66,956 high) — this dip is a retracement *within* an already-bullish HTF structure, i.e., a discount buy into confirmed direction, not a countertrend guess. Score: HTF bias 7/8, structure/location 8/10, **timing 3/7** (no killzone/session data available for a purely historical daily/4H reconstruction — a real, honestly-scored limitation, not glossed over). **ICT: 18/25.**

### Confluence Score (per `SYSTEM-DESIGN.md` §6.2's corrected formula)
```
engaged_count = 2 (Wyckoff, ICT — Footprint/Heatmap unavailable, no CoinGlass)
raw_pct = (22 + 18) / (2 x 25) x 100 = 80
contradictions = none (Wyckoff and ICT agree on direction and location)
final_score = 80
mode = NORMAL (only mode reachable with 2 engaged dimensions, regardless of the numeric
       score clearing ENHANCED's 80 threshold too -- dimension_count_met caps the mode)
dimension_count_met = true (2 >= NORMAL's minimum of 2)
threshold_met = true (80 >= 70)
verdict = TRADE
```

### Trade plan (illustrative sizing — `risk-config.json`'s `account_equity` is still 0/unset, so this uses a **labeled example** $10,000, not your real configured value)
- Entry: 76,829 (Sep 2 08:00 4H close, the confirming reaction bar)
- Stop: 76,100 (below the Spring's lowest low, 76,264, with a small buffer)
- Risk: 0.75% of $10,000 = $75 → position size = $75 / (76,829−76,100) = **0.103 BTC**
- Target 1: 79,500 (top of the prior reaccumulation range)
- Target 2: 81,500 (next liquidity zone, per the 80%-Market-Profile-rule logic in `SYSTEM-DESIGN.md` §7)
- R:R: T1 ≈ 3.7R, T2 ≈ 6.4R

### Actual outcome (checked against real subsequent price action — not assumed)
- Stop (76,100) was **never threatened** — the lowest subsequent low before targets were hit was 76,612 (Sep 2 12:00).
- **T1 (79,500) hit intrabar on the Sep 3 12:00 4H candle** (high 81,370) — per `SYSTEM-DESIGN.md` §7, this is where stop moves to breakeven.
- **T2 (81,500) hit later the same day** (Sep 3 20:00 high, 82,300).
- **Result: WIN, ~6.4R if held to T2** (or ~3.7R if only T1 was taken).

---

## What this is NOT

- **This is one hand-selected case study, not a backtest.** I scanned 120 days, found the cleanest recent Wyckoff+ICT-aligned setup, and reported it. That's legitimate as a **proof that the scoring/sizing/exit logic works correctly on a real textbook case** — it is **not** evidence the system is profitable, and reporting only a winner would be actual cherry-picking if presented as validation.
- **No losing case is included yet.** A real validation needs both — the current stop-loss/invalidation logic has not been tested against a case where it should have triggered.
- **Timing (ICT) was scored low (3/7) because there's no session/killzone framework applied to historical reconstruction** — a real gap, not smoothed over.
- **n=1.** Nowhere near enough for "good enough for Stage 2." A real campaign needs a mechanical, reproducible setup-detection method (not me picking the cleanest chart by eye) run across many more setups — ideally including forward, not just historical, data — before touching the confirmation requirement in `/execute`.

## Recommended next step, if you want a real validation campaign

Mechanically re-scan a much longer window (e.g. 2+ years of daily/4H data across BTC/ETH/SOL) for every Wyckoff phase-boundary + volume-outlier pattern matching the Spring/Upthrust criteria — not just the cleanest one — score each with the same rubric, and report the full distribution of outcomes (wins, losses, and breakevens), not a single example. That's the actual bar for "good enough," and it's a materially bigger piece of work than this case study.
