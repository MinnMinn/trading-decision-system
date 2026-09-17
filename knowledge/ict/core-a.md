# TTrades Core A — Killzones, Position Sizing, Liquidity, Important Liquidity Levels, Intraday/Daily Bias, Discount/Premium, OTE, MSS vs Liquidity Grab, Fair Value Gaps, Inversion

Synthesis of 11 TTrades_edu slide-deck PDFs (folder `docs/TTrades PDFs/`). These decks are mostly annotated chart diagrams with short prose captions. Where a statement below is **quoted prose** from a slide it is marked `[text]`; where it is **read from the diagram** it is marked `[diagram]`. Nothing below is added from outside the PDFs except the clearly labelled **Adaptation notes** for crypto (BTC/ETH/SOL, 24/7) and commodity CFDs (Gold/Silver/Oil), and explicit "NOT in source" flags.

Citation format: `File p<physical PDF page> (printed <n>)`. Physical page 1 is the cover, page 2 is the table of contents, and the last page is always "Resources" (links only, no content). Sibling file: `knowledge/ict/core-b.md` (decks 16–24 + the four undated decks).

---

## 1. Source list

| # | File | Physical pages | Content pages (printed) | Sections (from TOC) |
|---|------|----------------|-------------------------|---------------------|
| 1 | `1. Killzones.pdf` | 5 | p3–p4 (1–2) | Killzones (1), Silver Bullet Windows (2) |
| 2 | `2. Position_Sizing.pdf` | 9 | p3–p8 (1–6) | Win Rate & Risk:Reward (1), Position Sizing Options (2), Fixed Contract (3–4), Fixed $ / % (5–6) |
| 3 | `3. Liquidity.pdf` | 8 | p3–p7 (1–5) | Swing Highs & Lows (1), Buyside & Sellside (2), Types Of Liquidity (3), Previous Day & Week (4), Session Highs & Lows (5) |
| 4 | `4. Important_Liquidity_Levels.pdf` | 10 | p3–p9 (1–7) | Candles (1), Monthly (2), Weekly (3), Daily (4), Killzones (5), Sessions (6–7) |
| 5 | `6. Intraday_Bias.pdf` | 8 | p3–p7 (1–5) | Previous Candle High (PCH) & Low (PCL) (1–2), Swing Points (3), Failure To Displace (4), Next Candle Model (5). TOC credits "The MMXM Trader" |
| 6 | `8. Discount__Premium.pdf` | 8 | p3–p7 (1–5) | Range High & Low (1), Discount & Premium (2), Why? (3), Premium PD Array (4), Discount PD Array (5) |
| 7 | `9. OTE.pdf` | 10 | p3–p9 (1–7) | Fibonacci Settings (1), Anchor Points (2), Optimal Trade Entry (3), Alignment With PD Arrays (4), Extra (5–7) |
| 8 | `11. MSS_vs_Liquidity_Grab.pdf` | 7 | p3–p6 (1–4) | Displacement (1), Market Structure Shift (2), Liquidity Grab (3), Example (4) |
| 9 | `12. Fair_Value_Gaps.pdf` | 9 | p3–p8 (1–6) | Fair Value Gaps (1), SIBI & BISI (2), VI & Opening Gap (3), Entries (4), Stop Losses (5), Inversion (6) |
| 10 | `13. Inversion.pdf` | 17 | p3–p16 (1–14) | Fair Value Gaps (1), Inversion (2–6), Consequent Encroachment (7–12), Old SIBI / BISI (13–14). **No prose at all** — entirely diagrams |
| 11 | `14. Daily_Bias.pdf` | 9 | p3–p8 (1–6) | Previous Day High & Low (1–2), Previous Week High & Low (3), Swing Points (4), Failure To Displace (5), Next Day Model (6). TOC credits "The MMXM Trader" |

Total: 100 physical pages, all read (text layer via `pdftotext -layout` plus full visual read of every page). Decks numbered 5, 7 and 10 do not exist in the folder.

---

## 2. Core concepts

### 2.1 Killzones (KZ)
- All times are labelled **"Eastern Standard Time (EST)"** on the slide header. `[text]` `1. Killzones p3 (1)`, `p4 (2)`; `4. Important_Liquidity_Levels p7 (5)`.
- `[text]` **Forex Killzones**: Asia **20:00 – 00:00**; London **02:00 – 05:00**; New York AM **07:00 – 10:00**; London Close **10:00 – 12:00**. `1. Killzones p3 (1)`.
- `[text]` **Indices Killzones**: Asia **20:00 – 00:00**; London **02:00 – 05:00**; New York AM **08:30 – 11:00**; New York PM **13:30 – 16:00**. `1. Killzones p3 (1)`; repeated verbatim (indices set only) at `4. Important_Liquidity_Levels p7 (5)`.
- `[diagram]` Drawn as four shaded vertical blocks on a time axis; the forex NY AM block (07:00–10:00) is immediately followed by the London Close block (10:00–12:00) with no gap; the indices NY AM and NY PM blocks are separated by a 2.5-hour gap (11:00–13:30). `1. Killzones p3 (1)`.
- No definition of *what to do* inside a killzone is given in these decks (the sibling file's Silver Bullet deck covers the AM framework).

### 2.2 Silver Bullet (SB) windows
- `[text]` London SB **03:00 – 04:00**; New York AM SB **10:00 – 11:00**; New York PM SB **14:00 – 15:00** (EST). `1. Killzones p4 (2)`.
- `[diagram]` The three SB windows are drawn as darker one-hour bands nested **inside the Indices killzones**: London SB inside London KZ (02:00–05:00), NY AM SB inside NY AM KZ (08:30–11:00, occupying its last hour), NY PM SB inside NY PM KZ (13:30–16:00). No SB is drawn in the Asia KZ. `1. Killzones p4 (2)`.

### 2.3 Win rate vs risk:reward profitability
- `[text]` Table titled "Win Rate & RR", footnote **"Assuming Same $ Risk Per Trade"**. Rows = Risk:Reward 1:1, 1:2, 1:3, 1:4, 1:5; columns = win rate 20%, 30%, 40%, 50%, 60%. `2. Position_Sizing p3 (1)`.
- `[text]` Cell values (NP = Not Profitable, BE = Breakeven, P = Profitable):

  | RR \ Win rate | 20% | 30% | 40% | 50% | 60% |
  |---|---|---|---|---|---|
  | 1:1 | NP | NP | NP | **BE** | P |
  | 1:2 | NP | NP | P | P | P |
  | 1:3 | NP | P | P | P | P |
  | 1:4 | **BE** | P | P | P | P |
  | 1:5 | P | P | P | P | P |

- The table is consistent with expectancy `E = W × RR − (1 − W)`; breakeven at `W = 1 / (1 + RR)` (50% at 1:1, 20% at 1:4). The formula itself is **not** printed — it is the arithmetic the table encodes.

### 2.4 Position sizing options
- `[text]` "Options For Position Sizing": **Fixed Contracts**, **Fixed Dollar**, **Fixed Percentage**. `2. Position_Sizing p4 (2)`.
- **Fixed Contract** `[text+diagram]`: "2 NQ Contracts Used In Each Scenario". 20 points risk → Risk = **$800**; 40 points risk → Risk = **$1600**; 10 points risk → Risk = **$400**. `p5 (3)`. Outcome box: `−$800 (−1R)`, `−$1600 (−1R)`, `+$1600 (+4R)` ⇒ `−$800 (+2R)???` — i.e. the trader is +2R on paper but **−$800** in cash because "R" was a different dollar amount each trade. `p6 (4)`.
- **Fixed $ / %** `[text+diagram]`: "Adjust Contracts Per Scenario To Maintain Fixed Risk Of $1000". 20 pts → `1000/20/20 = 2.5` contracts (= **25 Micros**); 40 pts → `1000/20/40 = 1.25` NQ contracts (= **12.5 Micros**); 10 pts → `1000/20/10 = 5` NQ contracts (= **50 Micros**). `p7 (5)`. Outcome box: `−$1000 (−1R)`, `−$1000 (−1R)`, `+$4000 (+4R)` ⇒ `+$2000 (+2R)`. `p8 (6)`.
- `[text]` **Formula**: **"$ of defined risk / $ per point / stop size"** = number of contracts. `p7 (5)`, `p8 (6)`.
- Implied but not stated: `$ per point` for NQ = **$20** (the middle divisor in every example); 1 mini = 10 micros.

### 2.5 Swing high / swing low
- `[text]` "A **Swing High** is formed when there is a high with a lower high to the left and right." `3. Liquidity p3 (1)`.
- `[text]` "A **Swing Low** is formed when there is a low with a higher low to the left and right." `3. Liquidity p3 (1)`.
- `[diagram]` Three-candle pattern; the middle candle's extreme (wick) is the swing point and is marked with a red arc; the neighbours' extremes are marked with black arcs. `p3 (1)`. The same 3-candle mini-diagrams reappear on the "Swing Points" slides of both bias decks. `6. Intraday_Bias p5 (3)`; `14. Daily_Bias p6 (4)`.

### 2.6 Buyside liquidity (BSL) / sellside liquidity (SSL)
- `[text]` "A Swing High at the top of the range will have stop losses from short positions (buy stops). This is called **buyside liquidity**." `3. Liquidity p4 (2)`.
- `[text]` "A Swing Low at the bottom of the range will have stop losses from long positions (sell stops). This is called **sellside liquidity**." `3. Liquidity p4 (2)`.
- `[diagram]` A horizontal line is projected right from the swing-high wick (labelled "Buyside Liquidity") and from the swing-low wick ("Sellside Liquidity"); these two lines define the range. `p4 (2)`; reused as the range definition in `8. Discount__Premium p3 (1)`.

### 2.7 Types of liquidity (as enumerated by the deck)
- `[text]` "**Old Highs & Lows** are previous highs and lows." Old High → Buyside Liquidity; Old Low → Sellside Liquidity. `3. Liquidity p5 (3)`.
- `[text]` "**Equal Highs & Lows** are when price reaches the same price level multiple times. Appearing to be support and resistance." Labelled "Relatively Equal Highs" → BSL and "Relatively Equal Lows" → SSL. `3. Liquidity p5 (3)`.
- `[diagram]` The "relatively equal" line is drawn across two wick highs that are close but not identical (the second slightly higher/lower); no tolerance is specified. `p5 (3)`.
- **NOT in source**: trendline liquidity is not mentioned in any of these 11 decks.

### 2.8 Higher-timeframe reference levels (PMH/PML, PWH/PWL, PDH/PDL)
- `[text]` "**Previous Week High & Low** are liquidity levels that can be used as a draw on liquidity or frame a reversal or continuation." `3. Liquidity p6 (4)`; `14. Daily_Bias p5 (3)`.
- `[text]` "**Previous Day High & Low** are liquidity levels that can be used as a draw on liquidity or frame a reversal or continuation." `3. Liquidity p6 (4)`; `14. Daily_Bias p3 (1)`.
- `[diagram]` PWH/PWL shown on the **Daily timeframe**: five grey candles labelled M, T, W, TH, F are the previous week; PWH is the highest wick of the week (Tuesday in the diagram), PWL the lowest wick (Thursday/Friday). `3. Liquidity p6 (4)`; `4. Important_Liquidity_Levels p5 (3)`; `14. Daily_Bias p5 (3)`.
- `[diagram]` PDH/PDL shown on the **4 Hour timeframe**: six grey H4 candles = previous day; PDH/PDL = the highest/lowest wick of those candles. `3. Liquidity p6 (4)`; `4. Important_Liquidity_Levels p6 (4)`; `14. Daily_Bias p4 (2)`.
- `[diagram]` **Previous Month High & Low** shown on the **Weekly timeframe** (grey weekly candles = previous month), same two-outcome treatment. No prose. `4. Important_Liquidity_Levels p4 (2)`.
- `[diagram]` Each level slide shows **two outcomes** stacked: (top) the level is swept by a wick and price **reverses** away from it; (bottom) the level is traded through with body closes and price **continues** (level acted as a draw, then breaks). `4. Important_Liquidity_Levels p4 (2), p5 (3), p6 (4)`.
- **NOT in source**: midnight open, NY 8:30 open, true day open, NWOG/NDOG, weekly open — none appear in these decks. The only "opening" concept is the Opening Gap in §2.20.

### 2.9 Session highs & lows
- `[text]` "**Session Highs & Lows** are liquidity levels that can be used as a draw on liquidity or frame a reversal or continuation". `3. Liquidity p7 (5)`.
- `[diagram]` Labels: "Asian Session High", "Asian Session Low", "London Session High", "London Session Low"; each projected right from the session's extreme wick. Two outcomes shown: (a) price forms London high above the Asian high, then sells through London Session Low and Asian Session Low (both taken) `3. Liquidity p7 (5)`; `4. Important_Liquidity_Levels p8 (6)`; (b) identical start, but the London low and Asian low **hold** and price rallies through the London Session High `4. Important_Liquidity_Levels p9 (7)`.
- Session boundaries are **not defined** on the session slides; the only times in the folder are the killzone times (§2.1), so "Asian session" = 20:00–00:00 and "London session" = 02:00–05:00 EST is an inference, not a statement.

### 2.10 Candle relationship to the previous candle ("Candles" slide)
- `[diagram]` No prose. Three labelled cases, each a big grey reference candle with its high and low projected right, and a following candle: **Consolidation** — the next candle is entirely inside the previous candle's high/low (neither side taken); **One Side** — the next candle takes out exactly one side (left example: takes the high; right example: takes the low); **Both Sides** — the next candle takes out both the high and the low. `4. Important_Liquidity_Levels p3 (1)`.
- This is the taxonomy of how PCH/PCL (§2.11) resolve on the next candle.

### 2.11 Previous Candle High / Low (PCH / PCL) — intraday bias unit
- `[text]` "**Previous Candle High & Low** are liquidity levels that can be used as a draw on liquidity or frame a reversal or continuation." `6. Intraday_Bias p3 (1)`.
- `[text]` Governing question: "**Is price more likely to reach for previous candle high or low?**" `6. Intraday_Bias p3 (1)`.
- `[text]` "Reversals can be framed off PCH and PCL when there is a failure to displace." `6. Intraday_Bias p3 (1)`.
- `[diagram]` Timeframes for the "previous candle": footer reads **"H4 / H1 / M30 / M15 Timeframe"** on every content slide. `6. Intraday_Bias p3–p7`.
- `[diagram]` Example (p4): the previous candle is drawn as a grey group of lower-time-frame candles; (top) LTF price trades down through PCL and keeps going (PCL used as **draw**, continuation); (bottom) LTF price wicks below PCL and then rallies (PCL used to **frame a reversal**). `6. Intraday_Bias p4 (2)`.
- `[diagram]` Sequence chart (p3, bottom): black candle → green candle wicks above its PCH but closes inside ("Reversal Framed Off PCH") → "Anticipate PCL As Draw" → large black candle → next green candle wicks below that candle's PCL, closes inside ("Reversal Framed Off PCL") → "Anticipate PCH As Draw" → green candles → "Anticipate PCH As Draw" repeats while continuation holds. `6. Intraday_Bias p3 (1)`.

### 2.12 Previous Day High / Low (PDH / PDL) — daily bias unit
- Identical framework to §2.11 with the daily candle as the unit. `[text]` "Is price more likely to reach for previous day high or previous day low?" and "Reversals can be framed off PDH and PDL when there is a failure to displace." Footer: **"Daily Timeframe"**. `14. Daily_Bias p3 (1)`.
- `[text]` "Example of Previous Day Low being used as a draw on liquidity and being used to frame a reversal. **H4 chart is shown.**" `14. Daily_Bias p4 (2)`.
- The Daily Bias deck and the Intraday Bias deck contain the **same six diagrams**; only the labels (PDH/PDL vs PCH/PCL) and the timeframe footers differ. The model is explicitly fractal.

### 2.13 Swing points as draw / reversal frame
- `[text]` "Swing points in the market can be used as a draw on liquidity or be used to frame a reversal." `6. Intraday_Bias p5 (3)`; `14. Daily_Bias p6 (4)`.
- `[diagram]` (top) "Anticipate As Draw On Liquidity": a 3-candle swing high is marked; later price rallies through it. (bottom) "Reversal Framed Off Swing Point": price wicks above the swing high and the candle closes back below; the next candle is bearish. Same slide in both decks.

### 2.14 Failure to displace (= liquidity grab)
- `[text]` "Failure to displace over old highs & lows can be used to frame a reversal." `6. Intraday_Bias p6 (4)`; `14. Daily_Bias p7 (5)`.
- `[diagram]` Old low (solid line, dotted extension): a black candle wicks below it and closes above → next candles rally; the rally then wicks above an old high (dotted extension) and closes below → labelled "Reversal Framed Off Swing Point" at both ends. `6. Intraday_Bias p6 (4)`.
- Formal definition given in the MSS deck under the name **Liquidity Grab** — see §2.17.

### 2.15 Next Candle Model / Next Day Model
- `[text]` "When price respects a PD array or fails to displace over a swing high or low, the next candle can be anticipated." `6. Intraday_Bias p7 (5)` ("Next Candle Model"); `14. Daily_Bias p8 (6)` ("Next Day Model").
- `[diagram]` (top-left) after a wick below a swing low that closes back above, the **next candle** is drawn hollow/light-green = anticipated bullish. (top-right) after a wick above a swing high that closes back below, the next candle is drawn grey = anticipated bearish. (bottom) after a failed sweep of a high, a **blue horizontal line** (a PD array) caps the pullbacks; each grey candle is the anticipated next candle, and the sequence continues down while price respects the line. Same diagrams in both decks.

### 2.16 Displacement
- `[text]` "Displacement is an aggressive move with full-bodied candles. This can form in a single candle or in multiple candles. Generally, displacement candle(s) have FVG present." `11. MSS_vs_Liquidity_Grab p3 (1)` (identical wording to `18. Market_Structure_Shift p3` in the sibling file).
- `[diagram]` Prior candles are drawn hollow; the displacement candle is a large solid body (black) closing below a line drawn from prior lows, and later a large green body closing above a line drawn from prior highs. `p3 (1)`.

### 2.17 Market Structure Shift (MSS) vs Liquidity Grab
- `[text]` "When displacement occurs over or below a swing high or low, a market structure shift occurs." Italic: "Having bodies close over/below previous structure is preferred. A stop raid before the MSS is preferred." "A market structure shift (MSS) indicates a change in trend from bullish to bearish or bearish to bullish." `11. MSS_vs_Liquidity_Grab p4 (2)`.
- `[diagram]` Bearish MSS: a dashed line marks a prior swing high; a yellow ▼ marks the raid high above it; a large black candle then closes **below the swing low that preceded the final push up** (bracket "Market Structure Shift"); yellow ▲ below that low. `p4 (2)`.
- `[text]` "When there is lack of displacement over or below a swing high or low, a **liquidity grab** occurs." Italic: "Having bodies fail to close over/below previous structure is preferred." "A liquidity grab indicates a **failure to continue** in one direction." `p5 (3)`.
- `[diagram]` Red ✗ "Failure to displace over previous high": a candle wicks above the projected prior high and its body closes below it; price then sells off. Red ✗ "Failure to displace below previous low": a candle wicks below the projected prior low and closes above; price then rallies. `p5 (3)`.
- `[diagram]` Example slide legend: ✗ = Failure To Displace, ✓ = Displacement. On one chart: ✗ at the wick above the high, ✓ at the black displacement candle closing below the swing-low line, ✗ at the wick below the low, ✓ at the green displacement candle closing above the swing-high line. `p6 (4)`.
- Distinction (faithful to text): **body close beyond the level with displacement = MSS (trend change)**; **wick beyond, body fails to close beyond = liquidity grab (failure to continue → reversal frame)**.

### 2.18 Range, equilibrium, premium, discount
- `[text]` "Discount and premium is based off the range high to the range low. An easy way to view a range is to look for where sell side and buyside liquidity is resting." `8. Discount__Premium p3 (1)`.
- `[text]` "A Gann Box or Fibonacci can be used from the high to the low, marking out the middle of the range, or **0.5**. The top 50% or above the 0.5 is considered a **premium**. The bottom 50% or below the 0.5 is considered a **discount**." `p4 (2)`.
- `[text]` The 0.5 level is called **equilibrium** on the "Why?" slide. `p5 (3)`.
- `[diagram]` Premium half shaded red, discount half shaded green, split at 0.5. `p4 (2)`, `p6 (4)`, `p7 (5)`.

### 2.19 Why premium/discount matters; premium & discount PD arrays
- `[text]` "Short positions in **premium** give better reward to risk than a short at equilibrium (0.5) or a short in discount." Bars: entry in Premium → **RR>1**; Equilibrium → **RR=1**; Discount → **RR<1**. `8. Discount__Premium p5 (3)`.
- `[text]` "Long positions in **discount** give better reward to risk than a long at equilibrium (0.5) or a long in premium." Discount → RR>1; Equilibrium → RR=1; Premium → RR<1. `p5 (3)`.
- `[diagram]` The RR bars are grey (risk) vs blue (reward) sized as if the **stop is at the range extreme behind the entry and the target is the opposite range extreme**; this is how RR=1 at exactly 0.5 arises. `p5 (3)`.
- `[text]` "Premium arrays, or PD arrays in a **premium** are used to frame a short setup." `[diagram]` An **OB** line drawn in the upper half of the range. `p6 (4)`.
- `[text]` "Discount arrays, or PD arrays in a **discount** are used to frame a long setup." `[diagram]` An **FVG** (two lines) drawn in the lower half of the range; price rallied into premium and retraces toward it. `p7 (5)`.

### 2.20 Optimal Trade Entry (OTE)
- `[text]` "The Fibonacci Settings: **0, 0.5, 0.62, 0.705, 0.79, 1**." `9. OTE p3 (1)`.
- `[diagram]` 0.705 is drawn in **orange**, 0.62 and 0.79 in bold black, 0 / 0.5 / 1 in grey. Two orientations shown: bearish (1 at top, 0 at bottom) and bullish (0 at top, 1 at bottom). `p3 (1)`.
- `[text]` "Anchored from swing high to swing low." (link to Liquidity PDF for swing definition). `[diagram]` Bearish example: red arc at the swing high = **1**, red arc at the swing low = **0**. `p4 (2)`. Combined with p3's bullish orientation: **1 = origin of the impulse leg, 0 = its terminus**; retracement levels are measured back toward the origin.
- `[diagram]` OTE slide (no prose): after the swing low, price retraces up; the retracement wicks reach the 0.705 line, bodies close between 0.5 and 0.62; price then reverses and trades below the 0 level (below the swing low). `p5 (3)`. The **OTE zone = 0.62 – 0.79**, with 0.705 the emphasised mid-level, is read from the settings and the drawing; the deck never prints "0.62–0.79" as a phrase.
- `[diagram]` "Alignment With PD Arrays": same chart with two black lines added from the down-leg — a bearish FVG (gap between an earlier candle's low and a later candle's high) whose band sits **between the 0.62 and 0.705 levels**, i.e. a PD array overlapping the OTE zone. Entry confluence = OTE band ∩ PD array. `p6 (4)`.
- `[diagram]` "Extra" (p7–p9): (p7) the same chart without anchor arcs; (p8) red arcs placed on the **retracement high** (the wick that touched 0.705) and the **small swing low that followed it**; (p9) the fib is **re-anchored on that smaller swing** (1 at the retracement high, 0 at the subsequent low) and price bounces into the 0.5–0.62 of the smaller fib before the final sell-off. This shows nesting the OTE on the internal (lower-timeframe) swing for a second entry. `p7 (5), p8 (6), p9 (7)`.

### 2.21 Fair Value Gap (FVG), SIBI, BISI
- `[text]` "Fair value gaps (FVG) are a **three-candlestick pattern** where the high/low of the candle(1) does not overlap the low/high of candle(3)." `12. Fair_Value_Gaps p3 (1)`.
- `[text]` Bearish detail: "The low of candle(1) does not overlap with the high of candle(3)." `[diagram]` Lines are drawn from the **wick** low of candle 1 and the **wick** high of candle 3 — the FVG is wick-to-wick, not body-to-body. `p3 (1)`; same drawing `13. Inversion p3 (1)`.
- `[text]` "**SIBI**: Sellside imbalance buyside inefficiency. This is a **bearish** FVG. Price offered sellside and made an imbalance. This leaves buyside inefficient. Candle(1) low does not overlap with Candle(3) high." `12. Fair_Value_Gaps p4 (2)`.
- `[text]` "**BISI**: Buyside imbalance sellside inefficiency. This is a **bullish** FVG. Price offered buyside and made an imbalance. This leaves sellside inefficient. Candle(1) high does not overlap with Candle(3) low." `p4 (2)`.

### 2.22 Volume Imbalance (VI) and Opening Gap
- `[diagram]` No prose; three side-by-side two/three-candle drawings, all bearish: **Fair Value Gap** — 3 candles, wick gap between candle 1 low and candle 3 high; **Volume Imbalance** — 2 candles whose **bodies** do not overlap (lines at candle 1's body bottom and candle 2's body top) but whose **wicks do** overlap; **Opening Gap** — 2 candles where **nothing** overlaps: candle 1's wick low is above candle 2's wick high (a true price gap). `12. Fair_Value_Gaps p5 (3)`.

### 2.23 FVG entry models
- `[diagram]` Three bullish (BISI) examples, no prose beyond the labels. **IOFED** — "Entry" line at the **upper edge** of the FVG (candle 3 low); price merely touches the edge and continues. **Consequent Encroachment** — "Entry" at the dashed **0.5** of the FVG. **FVG Fill** — "Entry" at the **lower edge** of the FVG (candle 1 high), i.e. the gap is fully filled. `12. Fair_Value_Gaps p6 (4)`.
- The abbreviation IOFED is **not expanded** in the PDF.

### 2.24 FVG stop-loss models
- `[diagram]` Three bullish examples: **FVG End** — red "Stop" line just below the FVG's lower edge; **Order Block** — stop below the low of the down-close candle(s) immediately preceding the displacement (the OB); **Swing** — stop below the swing low from which the displacement originated (the widest of the three). `12. Fair_Value_Gaps p7 (5)`.

### 2.25 Inversion (inverted FVG / IFVG)
- `[text]` "A **SIBI used as support** on the buyside of the curve. A **BISI used as resistance** on the sellside of the curve." `12. Fair_Value_Gaps p8 (6)`.
- `[diagram]` V-shaped chart: a SIBI left on the way down; a green candle later **closes above** the SIBI; price retests it from above (wicks into the gap), holds, and continues up. `12. Fair_Value_Gaps p8 (6)`; identical sequence expanded step-by-step in `13. Inversion p4–p8 (2–6)` and `p15 (13)`.
- `[diagram]` Step-by-step (Inversion deck, no text): p4 — plain downtrend, no gap lines yet; p5 — the SIBI (candle 1 low / candle 3 high) is marked **and** a green candle closes **through and above** it on the same slide (body spans the gap); p6 — visually the same as p5 (gap lines already extended right); p7 — price retraces **down into** the gap (a small black candle dips inside), then green candles push off it; p8 — strong continuation up. `13. Inversion p4 (2), p5 (3), p6 (4), p7 (5), p8 (6)`.

### 2.26 Consequent Encroachment (CE) as hold/fail line
- `[diagram]` No text. A bullish FVG is marked with its **0.5** dashed line. Two sequences: (a) p10–p11 — pullback candles trade into the gap, the lowest wick reaches about the 0.5, bodies stay above it, then a large green candle rallies away → **respected**. (b) p12–p14 — reset to the same FVG; a black candle **closes below the 0.5** (body through CE); the next black candle closes **below the whole gap** → the FVG has failed. `13. Inversion p9 (7), p10 (8), p11 (9), p12 (10), p13 (11), p14 (12)`.
- Read together with §2.25: a body close through CE is the early warning that the FVG will be traded through and **inverted** (become resistance).

### 2.27 Old SIBI / BISI
- `[diagram]` No text. On the V-reversal chart, three successive SIBIs from the prior downtrend are marked. Price rallies through the lowest (already inverted to support), then reaches and trades through the middle one, then the highest. Each older FVG acts as the next **draw** and, once closed through, as the next inverted support. `13. Inversion p15 (13), p16 (14)`.

---

## 3. Actionable rules / checklists (IF/THEN)

### 3.1 Time / context
- R1. IF trading an index-style instrument, THEN the killzones are Asia 20:00–00:00, London 02:00–05:00, NY AM 08:30–11:00, NY PM 13:30–16:00 (EST); IF forex, THEN NY AM is 07:00–10:00 and London Close 10:00–12:00 replaces NY PM. `[text]` `1. Killzones p3 (1)`.
- R2. IF looking for a Silver Bullet setup, THEN restrict to 03:00–04:00, 10:00–11:00 or 14:00–15:00 EST. `[text]` `1. Killzones p4 (2)`.
- R3. IF sizing a trade, THEN `contracts = $ defined risk / $ per point / stop size (points)`; do **not** use a fixed contract count. `[text]` `2. Position_Sizing p7 (5)`. Rationale: fixed contracts make R inconsistent (net +2R can be −$800). `[diagram]` `p6 (4)` vs `p8 (6)`.
- R4. IF your strategy's win rate is W and reward:risk is RR, THEN it is profitable only if the cell in the §2.3 table is "Profitable" (equivalently `W × RR > 1 − W`), assuming the same $ risk per trade. `[text]` `2. Position_Sizing p3 (1)`.

### 3.2 Bias determination (daily / intraday)
- R5. Before the session/candle, ask: "Is price more likely to reach for previous [day/candle] high or low?" — pick the draw. `[text]` `14. Daily_Bias p3 (1)`; `6. Intraday_Bias p3 (1)`.
- R6. IF price trades **through** PDH/PDL (or PCH/PCL, PWH/PWL, PMH/PML) with body closes, THEN treat the level as a **draw that was reached** and expect continuation in that direction. `[diagram]` `4. Important_Liquidity_Levels p4–p6` (bottom panels); `14. Daily_Bias p4 (2)` (top).
- R7. IF price **wicks** through PDH/PDL (or PCH/PCL, an old high/low, a swing point) but the body **fails to close beyond it** (failure to displace), THEN frame a **reversal** off that level and set the **opposite level as the new draw** ("Reversal Framed Off PDH → Anticipate PDL As Draw"). `[text+diagram]` `14. Daily_Bias p3 (1)`, `p7 (5)`; `6. Intraday_Bias p3 (1)`, `p6 (4)`.
- R8. IF a failure to displace has just occurred at a swing high/low, OR price is respecting a PD array (e.g. a level that keeps capping pullbacks), THEN **anticipate the next candle** in the direction away from the failed level / with the PD array (Next Candle / Next Day Model). `[text]` `6. Intraday_Bias p7 (5)`; `14. Daily_Bias p8 (6)`.
- R9. Apply R5–R8 fractally: Daily candle for daily bias (Daily Timeframe footer); H4 / H1 / M30 / M15 candle for intraday bias. `[diagram]` footers `14. Daily_Bias p3–p8`; `6. Intraday_Bias p3–p7`.

### 3.3 Confirmation (MSS vs liquidity grab)
- R10. IF a full-bodied displacement candle (or candles) **closes** over a swing high / below a swing low, THEN it is an **MSS** → expect trend change. Prefer **body** close beyond structure; prefer a **stop raid** immediately before. `[text]` `11. MSS_vs_Liquidity_Grab p4 (2)`.
- R11. IF price trades beyond a swing high/low **without** displacement (wick only, body fails to close beyond), THEN it is a **liquidity grab** → expect failure to continue → reversal frame, not a trend change. `[text]` `11. MSS_vs_Liquidity_Grab p5 (3)`.
- R12. IF displacement candle(s) are present, THEN expect an FVG inside them ("generally") — use it as the entry array. `[text]` `11. MSS_vs_Liquidity_Grab p3 (1)`.

### 3.4 Location (premium / discount)
- R13. IF you intend to short, THEN require entry in the **premium** (above 0.5 of the range from BSL to SSL); IF you intend to long, THEN require entry in the **discount** (below 0.5). Equilibrium entries yield RR=1; wrong-half entries yield RR<1. `[text]` `8. Discount__Premium p5 (3)`.
- R14. IF a PD array (OB, FVG, …) lies in the premium, THEN it frames a short; IF in the discount, THEN it frames a long. Ignore opposite-half arrays for that direction. `[text]` `8. Discount__Premium p6 (4), p7 (5)`.
- R15. Define the range from where buyside and sellside liquidity rest (nearest swing high / swing low pair). `[text]` `8. Discount__Premium p3 (1)`.

### 3.5 Entry
- R16. **OTE entry**: IF a swing high → swing low impulse is identified (bearish), THEN anchor fib 1 at the swing high, 0 at the swing low and look to short the retracement into **0.62–0.79** (0.705 emphasised); target below 0. Mirror for bullish (1 at swing low, 0 at swing high). `[text+diagram]` `9. OTE p3 (1), p4 (2), p5 (3)`.
- R17. IF a PD array (e.g. bearish FVG from the impulse leg) overlaps the OTE band, THEN prefer that overlap as the entry. `[diagram]` `9. OTE p6 (4)`.
- R18. IF the first OTE retracement has printed a new internal swing high and swing low, THEN re-anchor the fib on that smaller swing for a nested second entry. `[diagram]` `9. OTE p8 (6), p9 (7)`.
- R19. **FVG entry**: choose one of three fills — touch of the near edge (IOFED), the 0.5 (Consequent Encroachment), or the far edge (FVG Fill). `[diagram]` `12. Fair_Value_Gaps p6 (4)`.
- R20. **Inversion entry**: IF a SIBI is closed through by a bullish displacement, THEN buy the retest of that SIBI from above (it is now support); IF a BISI is closed through by bearish displacement, THEN sell the retest from below. `[text]` `12. Fair_Value_Gaps p8 (6)`; `[diagram]` `13. Inversion p5–p8`.
- R21. IF several older SIBIs (or BISIs) from the prior trend lie ahead, THEN use them sequentially as targets and, once closed through, as the next inverted-support/resistance entries. `[diagram]` `13. Inversion p16 (14)`.

### 3.6 Stops / invalidation
- R22. FVG-based long: stop below the FVG's far edge (tight), below the OB candle low (medium), or below the originating swing low (wide). Mirror for shorts. `[diagram]` `12. Fair_Value_Gaps p7 (5)`.
- R23. IF a pullback **body-closes through the 0.5 (CE)** of the FVG you are trading, THEN treat the FVG as failing; a subsequent close through the far edge completes the failure and inverts the gap. `[diagram]` `13. Inversion p13 (11), p14 (12)`.
- R24. OTE short: the diagrams show price never trading above the 0.79 / 1 after entry; a close above the 1 (swing high) breaks the anchor and invalidates. (Stop placement is not stated in the OTE deck — inferred from anchor logic.) `9. OTE p5 (3)`.
- R25. Reversal framed off a failure to displace is invalidated if a later candle **body-closes** beyond the same level (that would convert the grab into an MSS). Derived from R10/R11. `11. MSS_vs_Liquidity_Grab p4–p5`.

---

## 4. Patterns with identification criteria

| Pattern | Must be true | Must NOT be true | Source |
|---|---|---|---|
| Swing high | `high[i] > high[i-1]` and `high[i] > high[i+1]` (one candle each side) | — | `3. Liquidity p3 (1)` |
| Swing low | `low[i] < low[i-1]` and `low[i] < low[i+1]` | — | `3. Liquidity p3 (1)` |
| Buyside liquidity | Swing high at the top of the range; line projected right from its wick | — | `3. Liquidity p4 (2)` |
| Sellside liquidity | Swing low at the bottom of the range; line projected right | — | `3. Liquidity p4 (2)` |
| Relatively equal highs/lows | Two or more highs (lows) at approximately the same price, appearing as resistance (support) | — (tolerance not given) | `3. Liquidity p5 (3)` |
| PDH/PDL, PWH/PWL, PMH/PML | Highest/lowest wick of the previous day (H4 chart), week (Daily chart; Mon–Fri), month (Weekly chart) | — | `3. Liquidity p6 (4)`; `4. ILL p4–p6` |
| Session high/low | Highest/lowest wick within the Asian / London session | — | `3. Liquidity p7 (5)`; `4. ILL p8–p9` |
| Candle: Consolidation | Next candle high ≤ previous high AND low ≥ previous low | Either side taken | `4. ILL p3 (1)` |
| Candle: One Side | Exactly one of {high taken, low taken} | Both sides taken | `4. ILL p3 (1)` |
| Candle: Both Sides | Next candle high > previous high AND low < previous low | — | `4. ILL p3 (1)` |
| Displacement | Aggressive full-bodied candle(s), one or several, generally leaving an FVG | Small bodies / long wicks relative to body | `11. MSS_vs_LG p3 (1)` |
| MSS (bearish) | Prior swing high raided (wick above, preferred) THEN displacement candle **body closes below** the swing low preceding the raid leg | Only a wick below the swing low | `11. MSS_vs_LG p4 (2)` |
| MSS (bullish) | Prior swing low raided THEN displacement candle body closes above the swing high preceding the raid leg | Wick-only break | `11. MSS_vs_LG p4 (2)` |
| Liquidity grab / failure to displace (at a high) | Wick trades above the previous high; **body closes at or below** it | Body close above (that would be displacement) | `11. MSS_vs_LG p5 (3)`; `6. IB p6 (4)` |
| Liquidity grab (at a low) | Wick trades below the previous low; body closes at or above it | Body close below | same |
| Reversal framed off PDH/PCH | Failure to displace above PDH/PCH → next draw = PDL/PCL | Body close above PDH/PCH | `14. DB p3 (1)`; `6. IB p3 (1)` |
| Next Candle Model (bearish) | Failure to displace at a swing high, or a PD array capping pullbacks | Body close through the PD array / swing high | `6. IB p7 (5)`; `14. DB p8 (6)` |
| Premium | Price above 0.5 of (range high − range low), range = BSL↔SSL | — | `8. D&P p4 (2)` |
| Discount | Price below 0.5 of the range | — | `8. D&P p4 (2)` |
| Premium PD array (short frame) | OB/FVG/other array located in the premium half | Array in the discount half | `8. D&P p6 (4)` |
| Discount PD array (long frame) | Array located in the discount half | Array in the premium half | `8. D&P p7 (5)` |
| OTE (bearish) | Fib 1 = swing high, 0 = swing low; retracement reaches 0.62–0.79 (0.705 centre); reversal then trades below 0 | Retracement body-closes above 0.79 / 1 (inferred) | `9. OTE p3–p5` |
| OTE with PD array | A PD array (e.g. bearish FVG of the impulse) overlaps the 0.62–0.79 band | — | `9. OTE p6 (4)` |
| Nested OTE | New internal swing high/low inside the retracement; fib re-anchored on it | — | `9. OTE p8–p9` |
| FVG (SIBI, bearish) | 3 candles: `low[1] > high[3]`; gap = [high[3], low[1]] (wick-based) | Overlap of candle 1 low and candle 3 high | `12. FVG p3–p4` |
| FVG (BISI, bullish) | `high[1] < low[3]`; gap = [high[1], low[3]] | Overlap | `12. FVG p4 (2)` |
| Volume Imbalance | 2 candles: bodies do not overlap, wicks do overlap | Wick gap (that is an Opening Gap) | `12. FVG p5 (3)` |
| Opening Gap | 2 candles: no overlap at all between candle 1 range and candle 2 range | Any wick overlap | `12. FVG p5 (3)` |
| IOFED entry | Price touches the near edge of the FVG only | Deeper penetration required | `12. FVG p6 (4)` |
| CE entry | Price reaches the 0.5 of the FVG | — | `12. FVG p6 (4)` |
| FVG Fill entry | Price reaches the far edge of the FVG | — | `12. FVG p6 (4)` |
| Inverted SIBI (support) | SIBI exists; later candle **body closes above** the SIBI's upper edge; price retests the gap from above and holds | Retest body-closes back below the SIBI's lower edge | `12. FVG p8 (6)`; `13. Inv p4–p8` |
| Inverted BISI (resistance) | Mirror: body close below a BISI, retest from below holds | Retest closes back above | `12. FVG p8 (6)` |
| CE respected (bullish FVG) | Pullback wicks to ≈0.5; bodies stay above 0.5; displacement resumes | Body close below 0.5 | `13. Inv p10–p11` |
| CE failed (bullish FVG) | Body close below 0.5, followed by body close below the far edge | — | `13. Inv p13–p14` |
| Old SIBI/BISI chain | Multiple prior-trend FVGs stacked ahead; each acts as next draw then inverts once closed through | — | `13. Inv p16 (14)` |

---

## 5. Quantitative details

| Item | Value | Timezone / units | Source |
|---|---|---|---|
| Forex KZ — Asia | 20:00 – 00:00 | "EST" per slide (New York clock; DST not addressed) | `1. Killzones p3 (1)` |
| Forex KZ — London | 02:00 – 05:00 | EST | `1. Killzones p3 (1)` |
| Forex KZ — New York AM | 07:00 – 10:00 | EST | `1. Killzones p3 (1)` |
| Forex KZ — London Close | 10:00 – 12:00 | EST | `1. Killzones p3 (1)` |
| Indices KZ — Asia | 20:00 – 00:00 | EST | `1. Killzones p3 (1)`; `4. ILL p7 (5)` |
| Indices KZ — London | 02:00 – 05:00 | EST | same |
| Indices KZ — New York AM | 08:30 – 11:00 | EST | same |
| Indices KZ — New York PM | 13:30 – 16:00 | EST | same |
| London Silver Bullet | 03:00 – 04:00 | EST | `1. Killzones p4 (2)` |
| New York AM Silver Bullet | 10:00 – 11:00 | EST | `1. Killzones p4 (2)` |
| New York PM Silver Bullet | 14:00 – 15:00 | EST | `1. Killzones p4 (2)` |
| Win-rate columns | 20 / 30 / 40 / 50 / 60 % | — | `2. PS p3 (1)` |
| RR rows | 1:1 / 1:2 / 1:3 / 1:4 / 1:5 | — | `2. PS p3 (1)` |
| Breakeven cells | 1:1 @ 50 %; 1:4 @ 20 % | — | `2. PS p3 (1)` |
| Position-size formula | contracts = $risk / ($ per point) / stop(points) | — | `2. PS p7 (5)` |
| Fixed-$ example | $1000 risk; 20 pts → 2.5 minis (25 micros); 40 pts → 1.25 (12.5 micros); 10 pts → 5 (50 micros) | NQ; implies $20/pt/mini, 10 micros = 1 mini | `2. PS p7 (5)` |
| Fixed-contract example | 2 NQ: 20 pts = $800; 40 pts = $1600; 10 pts = $400 | NQ | `2. PS p5 (3)` |
| Swing definition width | 1 candle each side | — | `3. Liquidity p3 (1)` |
| Equilibrium | 0.5 of range (Gann box or fib, high → low) | — | `8. D&P p4 (2)` |
| Premium / discount | > 0.5 / < 0.5 | fraction of range | `8. D&P p4 (2)` |
| RR by entry zone | Premium short: RR>1; EQ: RR=1; Discount short: RR<1 (mirror for longs) | — | `8. D&P p5 (3)` |
| OTE fib levels | 0, 0.5, 0.62, 0.705, 0.79, 1 | fib retracement | `9. OTE p3 (1)` |
| OTE emphasised level | 0.705 (orange); 0.62 & 0.79 bold | — | `9. OTE p3 (1)` |
| OTE anchor | 1 = swing high, 0 = swing low (bearish); reversed for bullish | — | `9. OTE p3–p4` |
| FVG midpoint (CE) | 0.5 of the gap | — | `12. FVG p6 (4)`; `13. Inv p9 (7)` |
| Bias timeframes | Daily bias: Daily candle (H4 chart to execute); Intraday bias: H4 / H1 / M30 / M15 | — | `14. DB p3–p8`; `6. IB p3–p7` |
| Reference chart TFs for levels | PMH/PML on Weekly; PWH/PWL on Daily; PDH/PDL on 4H | — | `4. ILL p4–p6` |

No numeric thresholds are given for: displacement body ratio, "relatively equal" tolerance, FVG minimum size, session boundaries (other than KZ times), or stop distance.

---

## 6. Conflicts, ambiguities, gaps

1. **Two killzone sets.** Forex NY AM = 07:00–10:00 vs Indices NY AM = 08:30–11:00; forex has London Close (10:00–12:00), indices have NY PM (13:30–16:00). `1. Killzones p3 (1)`. The Important_Liquidity_Levels deck repeats only the **indices** set (`p7 (5)`), and the Silver Bullet windows are drawn on the indices blocks (`1. Killzones p4 (2)`), so indices is the author's default. Which set applies to non-forex, non-index instruments is not stated.
2. **NY AM Silver Bullet straddles two forex killzones** — 10:00–11:00 is the last hour of the indices NY AM KZ but the first hour of the forex London Close KZ. Only the indices framing is drawn.
3. **"EST" label** — slides say EST year-round; whether the times shift with US DST is not addressed (same issue as the sibling file).
4. **$ per point never stated** — the $20/pt for NQ and the 10:1 micro ratio are implied by the arithmetic (`1000/20/20 = 2.5`, "25 Micros") but never written. `2. PS p7 (5)`.
5. **"Fixed Percentage" is listed but not illustrated** — the slides are titled "Fixed $/%" yet every example uses a fixed $1000. `2. PS p4 (2), p7 (5)`. Treat fixed-% as fixed-$ recomputed from current equity (inference).
6. **Win-rate table is discrete** — only the five win rates × five RRs shown; intermediate values (e.g. 45% at 1:1) require the expectancy formula, which the deck implies but does not print.
7. **Liquidity "types" are only two** — Old highs/lows and Relatively Equal highs/lows. Trendline liquidity, midnight/session opens, NWOG/NDOG are **absent** from all 11 decks, despite being common ICT vocabulary.
8. **"Relatively equal" has no tolerance**; the diagram uses two wicks a few ticks apart. Detector needs a tunable tolerance (ATR- or tick-based) — not sourced.
9. **Session boundaries undefined** — "Asian Session" and "London Session" highs/lows are drawn but the session start/end times are never given; only killzone times exist. `3. Liquidity p7 (5)`; `4. ILL p8–p9`.
10. **Previous-candle timeframe** — the intraday footer lists four options (H4 / H1 / M30 / M15) without a rule for choosing; the "Lower Time Frame" example (`6. IB p4 (2)`) does not name the LTF.
11. **Failure-to-displace threshold** — "bodies fail to close over/below previous structure is preferred" (`11. MSS_vs_LG p5 (3)`) gives a binary body-close test, but "preferred" language means a marginal body close is a grey zone. Detector should treat body close beyond the level as MSS-side and anything else as grab-side, and log the margin.
12. **MSS reference swing** — the MSS bracket is at the swing low **immediately preceding the raid leg**, not an older structural low (`11. MSS_vs_LG p4 (2)`). Consistent with the sibling file's finding for deck 18.
13. **FVG boundaries are wick-based** (candle 1 wick ↔ candle 3 wick) in both `12. FVG` and `13. Inversion`, while the Volume Imbalance is body-based. Do not mix the two when coding detectors.
14. **Consequent Encroachment has two roles** — an entry price (`12. FVG p6 (4)`) and a hold/fail decision line (`13. Inv p9–p14`). Not contradictory, but a detector must expose both.
15. **IOFED is not expanded** anywhere in the folder; the definition here is purely the drawing (touch of the near edge). Do not assume any additional meaning from outside sources without flagging it.
16. **Inversion deck has zero prose** (17 pages). All Inversion/CE/Old-SIBI semantics are diagram readings; the only textual definition of inversion is the two sentences on `12. FVG p8 (6)`.
17. **OTE zone never named numerically** — the deck lists the six fib levels and draws the retracement into the 0.62–0.79 band with 0.705 highlighted; the phrase "OTE = 0.62–0.79" is an inference from settings + drawing. `9. OTE p3 (1), p5 (3)`.
18. **OTE stop placement not given**; only the entry band and the target (below 0) are drawn. Rule R24 is inferred.
19. **Premium/discount RR argument assumes stop at the range extreme and target at the opposite extreme** — inferred from the bar proportions on `8. D&P p5 (3)`; the text only says "better reward to risk".
20. **Daily Bias and Intraday Bias decks are duplicates** with different labels; both credit "The MMXM Trader". The Next Candle / Next Day Model shows anticipated candles (grey / light green) but gives **no confirmation or invalidation rule** for the anticipation.
21. **"Candles" slide (Consolidation / One Side / Both Sides)** has no prose; the category names are the only text. The reading that it classifies the next candle's relationship to PCH/PCL is an inference from placement (it opens the Important Liquidity Levels deck, before Monthly/Weekly/Daily).
22. **Week = Mon–Fri** in every PWH/PWL diagram (`3. Liquidity p6 (4)`; `14. DB p5 (3)`; `4. ILL p5 (3)`). Weekend candles are not contemplated.
23. **Cross-file overlap**: Displacement wording is identical in `11. MSS_vs_LG p3` and the sibling's `18. MSS p3`; the FVG 3-candle diagram is identical in `12. FVG p3`, `13. Inv p3` and the sibling's `19. Breaker` FVG section. No contradictions found between the two synthesis files.

---

## Adaptation notes (NOT in the PDFs — for crypto 24/7 and commodity CFDs)

- **Killzones / Silver Bullet** — all windows are New York-clock times. Convert for a 24/7 book: with US DST (EDT, Mar–Nov) add 4 h for UTC; with EST (Nov–Mar) add 5 h. E.g. indices NY AM KZ 08:30–11:00 NY = 12:30–15:00 UTC (EDT) / 13:30–16:00 UTC (EST); NY AM SB 10:00–11:00 NY = 14:00–15:00 UTC (EDT) / 15:00–16:00 UTC (EST). Crypto has no exchange session, but US-hours flow still concentrates in these windows; Gold/Silver/Oil CFDs track COMEX/NYMEX-centred hours, for which the **indices** set (08:30–11:00, 13:30–16:00) is the closer analogue. Whether the forex set (07:00–10:00 + London Close 10:00–12:00) is more relevant for Gold (London fix flows) is **not** something the source decides — treat as a parameter to backtest.
- **Asia session for crypto** — the only Asia definition in the folder is the 20:00–00:00 NY killzone. For session-high/low detection on BTC/ETH/SOL, either use that window or a fuller Asia window; the PDF does not choose.
- **PDH/PDL day boundary** — the decks use the charting platform's daily candle without defining it. For crypto, exchange daily candles are usually 00:00 UTC; for CFDs the broker's daily bar (often 17:00 NY rollover or 00:00 server time). Pick one boundary per instrument and keep it fixed; the source gives no guidance.
- **PWH/PWL for crypto** — the diagrams are Mon–Fri. Crypto trades Sat/Sun, so decide whether the previous week includes weekend candles (exchange-native weekly bar) or is restricted to Mon–Fri. Not covered by the source.
- **Position sizing** — the formula `units = $risk / ($ per point per unit) / stop(points)` generalises directly. Crypto: 1 BTC moves $1 per $1 of price, so `size_in_coins = $risk / stop_in_$`; fractional sizing is native (no micro-contract rounding). CFDs: `$ per point per lot` is broker-specific (e.g. 1 lot Gold = 100 oz ⇒ $100/pt — verify with the broker; not in source). The win-rate/RR table is instrument-agnostic.
- **Everything else** (swing, BSL/SSL, equal highs/lows, PD/discount/premium/EQ, OTE, FVG/SIBI/BISI/VI/opening gap, entry & stop models, inversion, CE, old FVGs, MSS vs liquidity grab, failure to displace, next-candle model) is pure price action and applies unchanged to any instrument and timeframe.

---

## 7. Machine-readable summary

```yaml
meta:
  source_folder: "docs/TTrades PDFs/"
  files: 11
  physical_pages: 100
  page_citation: "physical PDF page (printed label)"
  evidence_tags: {text: "quoted prose on slide", diagram: "read from chart drawing"}
  timezone_note: "All clock times are labelled 'Eastern Standard Time (EST)' in the source; DST handling is not specified."
  not_in_source: [trendline_liquidity, midnight_open, ny_open_0830, nwog_ndog, weekly_open, fixed_percentage_example, ote_stop_rule]

concepts:
  - name: killzone_forex
    definition: "Forex killzones: Asia 20:00-00:00, London 02:00-05:00, New York AM 07:00-10:00, London Close 10:00-12:00 (EST)."
    evidence: text
    detection_criteria:
      - "asia:   20:00 <= t_NY < 00:00"
      - "london: 02:00 <= t_NY < 05:00"
      - "ny_am:  07:00 <= t_NY < 10:00"
      - "london_close: 10:00 <= t_NY < 12:00"
    source: "1. Killzones.pdf"
    page: "p3 (1)"

  - name: killzone_indices
    definition: "Indices killzones: Asia 20:00-00:00, London 02:00-05:00, New York AM 08:30-11:00, New York PM 13:30-16:00 (EST). Author's default set (repeated alone in deck 4)."
    evidence: text
    detection_criteria:
      - "asia:   20:00 <= t_NY < 00:00"
      - "london: 02:00 <= t_NY < 05:00"
      - "ny_am:  08:30 <= t_NY < 11:00"
      - "ny_pm:  13:30 <= t_NY < 16:00"
    source: "1. Killzones.pdf; 4. Important_Liquidity_Levels.pdf"
    page: "1: p3 (1); 4: p7 (5)"

  - name: silver_bullet_window
    definition: "One-hour windows nested inside the indices killzones: London SB 03:00-04:00, NY AM SB 10:00-11:00, NY PM SB 14:00-15:00 (EST)."
    evidence: text+diagram
    detection_criteria:
      - "london_sb: 03:00 <= t_NY < 04:00"
      - "ny_am_sb:  10:00 <= t_NY < 11:00"
      - "ny_pm_sb:  14:00 <= t_NY < 15:00"
    source: "1. Killzones.pdf"
    page: "p4 (2)"

  - name: win_rate_rr_profitability
    definition: "Profitability grid of win rate (20-60%) vs risk:reward (1:1-1:5) assuming the same $ risk per trade; breakeven at 1:1@50% and 1:4@20%."
    evidence: text
    detection_criteria:
      - "expectancy E = W*RR - (1-W)  (formula implied by table, not printed)"
      - "profitable if E > 0; breakeven if E == 0; else not profitable"
      - "table cells: 1:1 -> NP,NP,NP,BE,P; 1:2 -> NP,NP,P,P,P; 1:3 -> NP,P,P,P,P; 1:4 -> BE,P,P,P,P; 1:5 -> P,P,P,P,P for W = 20,30,40,50,60%"
    source: "2. Position_Sizing.pdf"
    page: "p3 (1)"

  - name: position_sizing_fixed_dollar
    aliases: [fixed_percent, fixed_risk]
    definition: "Adjust contract count each trade so the dollar risk is constant: contracts = $ of defined risk / $ per point / stop size."
    evidence: text+diagram
    detection_criteria:
      - "contracts = risk_usd / usd_per_point_per_contract / stop_points"
      - "example: 1000/20/20 = 2.5 (25 micros); 1000/20/40 = 1.25 (12.5 micros); 1000/20/10 = 5 (50 micros)"
      - "usd_per_point_per_contract for NQ implied = 20; 1 mini = 10 micros (implied)"
      - "fixed_percent variant: risk_usd = equity * pct (not illustrated in source)"
    source: "2. Position_Sizing.pdf"
    page: "p7 (5), p8 (6)"

  - name: position_sizing_fixed_contract
    definition: "Same contract count regardless of stop distance; makes R inconsistent in dollars (deck's negative example)."
    evidence: text+diagram
    detection_criteria:
      - "risk_usd = contracts * usd_per_point * stop_points varies with stop (2 NQ: 20pts=$800, 40pts=$1600, 10pts=$400)"
      - "anti-pattern: -1R,-1R,+4R can net -$800 despite +2R"
    source: "2. Position_Sizing.pdf"
    page: "p5 (3), p6 (4)"

  - name: swing_high
    definition: "A high with a lower high on the candle to its left and to its right."
    evidence: text
    detection_criteria:
      - "high[i] > high[i-1] and high[i] > high[i+1]"
      - "level = high[i] (wick)"
    source: "3. Liquidity.pdf"
    page: "p3 (1)"

  - name: swing_low
    definition: "A low with a higher low on the candle to its left and to its right."
    evidence: text
    detection_criteria:
      - "low[i] < low[i-1] and low[i] < low[i+1]"
      - "level = low[i] (wick)"
    source: "3. Liquidity.pdf"
    page: "p3 (1)"

  - name: buyside_liquidity
    aliases: [BSL]
    definition: "Buy stops (from shorts) resting above a swing high at the top of the range."
    evidence: text
    detection_criteria:
      - "swing_high detected and not yet traded through"
      - "level = swing high wick, projected forward until price trades above it"
    source: "3. Liquidity.pdf"
    page: "p4 (2)"

  - name: sellside_liquidity
    aliases: [SSL]
    definition: "Sell stops (from longs) resting below a swing low at the bottom of the range."
    evidence: text
    detection_criteria:
      - "swing_low detected and not yet traded through"
      - "level = swing low wick, projected forward until price trades below it"
    source: "3. Liquidity.pdf"
    page: "p4 (2)"

  - name: old_high_low
    definition: "Previous highs and lows (older swing points) — buyside above old highs, sellside below old lows."
    evidence: text
    detection_criteria:
      - "any untaken prior swing_high / swing_low beyond the current range"
    source: "3. Liquidity.pdf"
    page: "p5 (3)"

  - name: relatively_equal_highs_lows
    aliases: [equal_highs, equal_lows, EQH, EQL]
    definition: "Price reaches the same level multiple times, appearing as support/resistance; treated as buyside (highs) or sellside (lows) liquidity."
    evidence: text+diagram
    detection_criteria:
      - ">= 2 swing highs with |high_a - high_b| <= tolerance  (tolerance NOT in source; tunable)"
      - ">= 2 swing lows with |low_a - low_b| <= tolerance"
      - "level = max of the highs (or min of the lows), projected forward"
    source: "3. Liquidity.pdf"
    page: "p5 (3)"

  - name: previous_day_high_low
    aliases: [PDH, PDL]
    definition: "High and low of the previous daily candle; a liquidity level used as a draw or to frame a reversal/continuation. Illustrated on a 4H chart."
    evidence: text+diagram
    detection_criteria:
      - "PDH = max(high) over previous day's candles; PDL = min(low)"
      - "day boundary = platform daily candle (unspecified in source)"
      - "outcome A (continuation): body close beyond level"
      - "outcome B (reversal): wick beyond level, body closes back inside"
    source: "3. Liquidity.pdf; 4. Important_Liquidity_Levels.pdf; 14. Daily_Bias.pdf"
    page: "3: p6 (4); 4: p6 (4); 14: p3 (1), p4 (2)"

  - name: previous_week_high_low
    aliases: [PWH, PWL]
    definition: "High and low of the previous week (Mon-Fri daily candles); liquidity level used as draw or reversal/continuation frame."
    evidence: text+diagram
    detection_criteria:
      - "PWH = max(high) of previous week's daily candles; PWL = min(low)"
      - "week shown as Mon..Fri; weekend handling not in source"
    source: "3. Liquidity.pdf; 4. Important_Liquidity_Levels.pdf; 14. Daily_Bias.pdf"
    page: "3: p6 (4); 4: p5 (3); 14: p5 (3)"

  - name: previous_month_high_low
    aliases: [PMH, PML]
    definition: "High and low of the previous month, shown on the weekly chart; same draw/reversal/continuation usage."
    evidence: diagram
    detection_criteria:
      - "PMH = max(high) of previous month's candles; PML = min(low)"
    source: "4. Important_Liquidity_Levels.pdf"
    page: "p4 (2)"

  - name: session_high_low
    definition: "Highs and lows of the Asian and London sessions; liquidity levels used as draw or to frame reversal/continuation."
    evidence: text+diagram
    detection_criteria:
      - "asian_high/low = max/min over Asian session; london_high/low = max/min over London session"
      - "session boundaries NOT defined in source; killzone times (Asia 20:00-00:00, London 02:00-05:00 EST) are the only candidates"
    source: "3. Liquidity.pdf; 4. Important_Liquidity_Levels.pdf"
    page: "3: p7 (5); 4: p8 (6), p9 (7)"

  - name: candle_relationship
    definition: "How the next candle relates to the previous candle's high/low: Consolidation (inside), One Side (takes exactly one extreme), Both Sides (takes both)."
    evidence: diagram
    detection_criteria:
      - "consolidation: high[t] <= high[t-1] and low[t] >= low[t-1]"
      - "one_side: (high[t] > high[t-1]) xor (low[t] < low[t-1])"
      - "both_sides: high[t] > high[t-1] and low[t] < low[t-1]"
    source: "4. Important_Liquidity_Levels.pdf"
    page: "p3 (1)"

  - name: previous_candle_high_low
    aliases: [PCH, PCL]
    definition: "High/low of the previous H4/H1/M30/M15 candle; liquidity level used as draw or to frame a reversal/continuation (intraday bias unit)."
    evidence: text+diagram
    detection_criteria:
      - "PCH = high[t-1], PCL = low[t-1] on the chosen TF in {H4,H1,M30,M15}"
      - "question: which of PCH/PCL is price more likely to reach"
    source: "6. Intraday_Bias.pdf"
    page: "p3 (1), p4 (2)"

  - name: failure_to_displace
    aliases: [liquidity_grab, stop_hunt_reversal]
    definition: "Price trades beyond a swing high/low or old high/low without displacement; bodies fail to close beyond the level; indicates failure to continue and frames a reversal."
    evidence: text+diagram
    detection_criteria:
      - "at high L: high[t] > L and close[t] <= L (body fails to close above)"
      - "at low L: low[t] < L and close[t] >= L"
      - "no full-bodied displacement candle closing beyond L"
      - "result: frame reversal; set opposite level as new draw"
    source: "11. MSS_vs_Liquidity_Grab.pdf; 6. Intraday_Bias.pdf; 14. Daily_Bias.pdf"
    page: "11: p5 (3), p6 (4); 6: p3 (1), p6 (4); 14: p3 (1), p7 (5)"

  - name: displacement
    definition: "Aggressive move with full-bodied candle(s), single or multiple; generally leaves an FVG."
    evidence: text
    detection_criteria:
      - "body/range ratio high (threshold not in source; tunable)"
      - "one or more consecutive same-direction candles"
      - "FVG usually present within the move"
    source: "11. MSS_vs_Liquidity_Grab.pdf"
    page: "p3 (1)"

  - name: market_structure_shift
    aliases: [MSS]
    definition: "Displacement closing over/below a swing high or low; indicates trend change. Body close beyond structure preferred; stop raid before it preferred."
    evidence: text+diagram
    detection_criteria:
      - "bearish: prior swing high raided (wick above) THEN displacement candle close < swing_low_preceding_raid_leg"
      - "bullish: prior swing low raided THEN displacement candle close > swing_high_preceding_raid_leg"
      - "distinguish from liquidity_grab by body close beyond the level"
    source: "11. MSS_vs_Liquidity_Grab.pdf"
    page: "p4 (2), p6 (4)"

  - name: draw_on_liquidity
    definition: "The liquidity level (PDH/PDL, PWH/PWL, PCH/PCL, swing point, session H/L, old FVG) price is expected to reach next."
    evidence: text+diagram
    detection_criteria:
      - "after reversal framed off level X, draw = opposite level"
      - "after continuation through X, draw = next level in that direction"
    source: "6. Intraday_Bias.pdf; 14. Daily_Bias.pdf; 13. Inversion.pdf"
    page: "6: p3 (1), p5 (3); 14: p3 (1), p6 (4); 13: p16 (14)"

  - name: next_candle_model
    aliases: [next_day_model]
    definition: "When price respects a PD array or fails to displace over a swing high/low, the next candle's direction can be anticipated."
    evidence: text+diagram
    detection_criteria:
      - "trigger A: failure_to_displace at swing high -> anticipate next candle bearish (mirror for lows)"
      - "trigger B: PD array level capping pullbacks -> anticipate continuation away from it"
      - "no confirmation/invalidation rule given in source"
    source: "6. Intraday_Bias.pdf; 14. Daily_Bias.pdf"
    page: "6: p7 (5); 14: p8 (6)"

  - name: daily_bias_method
    definition: "Daily candle framework: decide whether PDH or PDL is the draw; frame reversals off PDH/PDL on failure to displace; use PWH/PWL and swing points the same way; anticipate next day via Next Day Model. Credited to The MMXM Trader."
    evidence: text+diagram
    detection_criteria:
      - "inputs: PDH, PDL, PWH, PWL, daily swing points"
      - "if failure_to_displace at PDH -> bias bearish, draw = PDL"
      - "if failure_to_displace at PDL -> bias bullish, draw = PDH"
      - "if body close through PDH -> bias bullish continuation (next draw above); mirror for PDL"
      - "execution chart shown: 4H"
    source: "14. Daily_Bias.pdf"
    page: "p3 (1) - p8 (6)"

  - name: intraday_bias_method
    definition: "Same framework as daily bias applied to the previous H4/H1/M30/M15 candle (PCH/PCL), swing points, failure to displace, Next Candle Model."
    evidence: text+diagram
    detection_criteria:
      - "identical logic to daily_bias_method with PCH/PCL replacing PDH/PDL"
      - "TF in {H4,H1,M30,M15}; execution on a lower TF (unspecified)"
    source: "6. Intraday_Bias.pdf"
    page: "p3 (1) - p7 (5)"

  - name: range_high_low
    definition: "Range for premium/discount = from where buyside liquidity rests (range high) to where sellside liquidity rests (range low)."
    evidence: text
    detection_criteria:
      - "range_high = nearest relevant swing high (BSL); range_low = nearest relevant swing low (SSL)"
    source: "8. Discount__Premium.pdf"
    page: "p3 (1)"

  - name: equilibrium
    aliases: [EQ]
    definition: "The 0.5 of the range (Gann box or fibonacci from high to low)."
    evidence: text
    detection_criteria:
      - "eq = range_low + 0.5 * (range_high - range_low)"
    source: "8. Discount__Premium.pdf"
    page: "p4 (2), p5 (3)"

  - name: premium
    definition: "Top 50% of the range (above 0.5). Shorts here have RR>1 vs RR=1 at EQ and RR<1 in discount. PD arrays in premium frame shorts."
    evidence: text
    detection_criteria:
      - "price > eq"
      - "short setups only; PD array (OB/FVG) must lie in premium"
    source: "8. Discount__Premium.pdf"
    page: "p4 (2), p5 (3), p6 (4)"

  - name: discount
    definition: "Bottom 50% of the range (below 0.5). Longs here have RR>1 vs RR=1 at EQ and RR<1 in premium. PD arrays in discount frame longs."
    evidence: text
    detection_criteria:
      - "price < eq"
      - "long setups only; PD array (OB/FVG) must lie in discount"
    source: "8. Discount__Premium.pdf"
    page: "p4 (2), p5 (3), p7 (5)"

  - name: ote_fibonacci_settings
    definition: "Fibonacci retracement levels 0, 0.5, 0.62, 0.705, 0.79, 1; 0.705 emphasised."
    evidence: text+diagram
    detection_criteria:
      - "levels = [0, 0.5, 0.62, 0.705, 0.79, 1]"
    source: "9. OTE.pdf"
    page: "p3 (1)"

  - name: ote_anchor
    definition: "Anchored from swing high to swing low: 1 at the origin of the impulse (swing high for bearish, swing low for bullish), 0 at its terminus."
    evidence: text+diagram
    detection_criteria:
      - "bearish: fib(1) = swing_high, fib(0) = swing_low; level(x) = swing_low + x*(swing_high - swing_low)"
      - "bullish: fib(1) = swing_low, fib(0) = swing_high; level(x) = swing_high - x*(swing_high - swing_low)"
    source: "9. OTE.pdf"
    page: "p3 (1), p4 (2)"

  - name: optimal_trade_entry
    aliases: [OTE]
    definition: "Retracement of the impulse leg into the 0.62-0.79 band (0.705 centre) followed by reversal beyond the 0 (terminus). Numeric band inferred from settings + drawing."
    evidence: diagram
    detection_criteria:
      - "retracement wick reaches level(0.62) .. level(0.79)"
      - "bodies do not close beyond level(0.79)/level(1) (inferred invalidation)"
      - "target = beyond level(0)"
    source: "9. OTE.pdf"
    page: "p5 (3)"

  - name: ote_pd_array_alignment
    definition: "A PD array (e.g. bearish FVG from the impulse leg) whose band overlaps the OTE zone; confluence entry."
    evidence: diagram
    detection_criteria:
      - "exists FVG/OB from the impulse leg with [lo,hi] intersecting [level(0.62), level(0.79)]"
      - "entry = intersection"
    source: "9. OTE.pdf"
    page: "p6 (4)"

  - name: ote_nested_reanchor
    definition: "After the first OTE retracement prints an internal swing high and swing low, re-anchor the fib on that smaller swing for a second entry."
    evidence: diagram
    detection_criteria:
      - "new swing_high = retracement high (wick at ~0.705 of parent fib); new swing_low = subsequent low"
      - "apply ote_anchor + optimal_trade_entry to the child swing"
    source: "9. OTE.pdf"
    page: "p8 (6), p9 (7)"

  - name: fair_value_gap
    aliases: [FVG]
    definition: "Three-candle pattern where the high/low of candle 1 does not overlap the low/high of candle 3 (wick-based)."
    evidence: text+diagram
    detection_criteria:
      - "bearish (SIBI): low[1] > high[3]; gap = [high[3], low[1]]"
      - "bullish (BISI): high[1] < low[3]; gap = [high[1], low[3]]"
      - "boundaries use wicks of candles 1 and 3"
    source: "12. Fair_Value_Gaps.pdf; 13. Inversion.pdf"
    page: "12: p3 (1); 13: p3 (1)"

  - name: sibi
    aliases: [bearish_fvg]
    definition: "Sellside Imbalance Buyside Inefficiency: bearish FVG; price offered sellside and left buyside inefficient; candle 1 low does not overlap candle 3 high."
    evidence: text
    detection_criteria:
      - "low[1] > high[3] in a down move"
      - "zone = [high[3], low[1]]"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p4 (2)"

  - name: bisi
    aliases: [bullish_fvg]
    definition: "Buyside Imbalance Sellside Inefficiency: bullish FVG; price offered buyside and left sellside inefficient; candle 1 high does not overlap candle 3 low."
    evidence: text
    detection_criteria:
      - "high[1] < low[3] in an up move"
      - "zone = [high[1], low[3]]"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p4 (2)"

  - name: volume_imbalance
    aliases: [VI]
    definition: "Two consecutive candles whose bodies do not overlap while their wicks do."
    evidence: diagram
    detection_criteria:
      - "bearish: min(open[1],close[1]) > max(open[2],close[2]) and low[1] <= high[2]"
      - "bullish: max(open[1],close[1]) < min(open[2],close[2]) and high[1] >= low[2]"
      - "zone = between the two body edges"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p5 (3)"

  - name: opening_gap
    definition: "Two consecutive candles with no overlap at all (wick of candle 1 does not reach wick of candle 2)."
    evidence: diagram
    detection_criteria:
      - "bearish: low[1] > high[2]; bullish: high[1] < low[2]"
      - "zone = [high[2], low[1]] or [high[1], low[2]]"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p5 (3)"

  - name: fvg_entry_iofed
    aliases: [IOFED]
    definition: "Entry at the near edge of the FVG (price only touches the edge). Abbreviation not expanded in source."
    evidence: diagram
    detection_criteria:
      - "bullish: entry = low[3] (top of BISI); bearish: entry = high[3] (bottom of SIBI)"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p6 (4)"

  - name: fvg_entry_consequent_encroachment
    aliases: [CE]
    definition: "Entry at the 0.5 of the FVG."
    evidence: diagram
    detection_criteria:
      - "entry = (gap_hi + gap_lo) / 2"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p6 (4)"

  - name: fvg_entry_fill
    definition: "Entry at the far edge of the FVG (full fill)."
    evidence: diagram
    detection_criteria:
      - "bullish: entry = high[1] (bottom of BISI); bearish: entry = low[1] (top of SIBI)"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p6 (4)"

  - name: fvg_stop_models
    definition: "Three stop options for an FVG entry: just beyond the FVG far edge; beyond the order-block candle low/high; beyond the originating swing."
    evidence: diagram
    detection_criteria:
      - "fvg_end: stop = gap far edge - buffer (bullish) / + buffer (bearish)"
      - "order_block: stop = low of last down-close candle(s) before displacement (bullish); mirror bearish"
      - "swing: stop = swing low from which displacement started (bullish); mirror bearish"
    source: "12. Fair_Value_Gaps.pdf"
    page: "p7 (5)"

  - name: inversion_fvg
    aliases: [IFVG, inverted_fvg]
    definition: "A SIBI used as support on the buyside of the curve; a BISI used as resistance on the sellside. FVG is closed through by displacement then retested from the other side."
    evidence: text+diagram
    detection_criteria:
      - "bullish IFVG: SIBI exists; later close > SIBI upper edge (low[1]); subsequent pullback trades into [high[3], low[1]] and holds (no close back below high[3]); continuation up"
      - "bearish IFVG: BISI exists; later close < BISI lower edge (high[1]); pullback into gap holds; continuation down"
      - "entry = retest of the inverted gap; stop beyond its far edge (inferred)"
    source: "12. Fair_Value_Gaps.pdf; 13. Inversion.pdf"
    page: "12: p8 (6); 13: p4 (2) - p8 (6), p15 (13)"

  - name: consequent_encroachment_hold_fail
    definition: "The 0.5 of an FVG as a decision line: pullback wicks to CE with bodies holding = respected; body close through CE then through far edge = FVG failed (and inverts)."
    evidence: diagram
    detection_criteria:
      - "respected (bullish FVG): min(low) over pullback >= ~ce and all closes > ce, then displacement resumes"
      - "failed (bullish FVG): close < ce, followed by close < gap_lo"
      - "mirror for bearish FVG"
    source: "13. Inversion.pdf"
    page: "p9 (7) - p14 (12)"

  - name: old_sibi_bisi
    definition: "Older FVGs left by the prior trend; each is the next draw and, once closed through, the next inverted support/resistance."
    evidence: diagram
    detection_criteria:
      - "list untested SIBIs above (in an up-reversal) ordered by price"
      - "target_k = next SIBI; after close through it, treat as inversion_fvg support"
    source: "13. Inversion.pdf"
    page: "p15 (13), p16 (14)"
```
