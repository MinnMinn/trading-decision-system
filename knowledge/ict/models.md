# TTrades Models — TTrades Model (OSOK + Fractal), Sons Model (+HTF), TTRS Reversal Sequence, Unicorn, Timeframe Alignment

Synthesis of 6 TTrades PDFs (folder `docs/TTrades PDFs/`). `TTrades Model11.pdf` is a 118-page course document with substantial prose; the other five are annotated slide decks with almost no prose. Where a statement below is **quoted or paraphrased prose** it is marked `[text]`; where it is **read from a chart drawing** it is marked `[diagram]`. Nothing below is added from outside the PDFs except the clearly labelled **Adaptation notes** for crypto (BTC/ETH/SOL, 24/7) and commodity CFDs (Gold/Silver/Oil).

Citation format:
- `Model11 p<n>` — physical PDF page; in this file the printed page number **equals** the physical page (p1–2 = index, p3 = Overview).
- Slide decks: `File p<physical> (<printed>)`. Physical p1 = cover, p2 = contents, printed labels start at 1 on physical p3, last page = Resources (links only).

Sibling file: `knowledge/ict/core-b.md` covers CISD / OB / Breaker / MSS / SMT / PO3 / Std-Dev / IRL-ERL from the 13 concept decks. This file does not restate those definitions except where the model documents redefine or specialise them.

---

## 1. Source list

| # | File | Physical pages | Content pages | Sections |
|---|------|----------------|---------------|----------|
| 1 | `TTrades Model11.pdf` | 118 | p3–p118 | Overview (3); Concepts (5–23): Opposing Candles, Highs & Lows, FVG, Equilibrium, Projections; Swing Highs & Lows (24–43): Swing High & Low, Candle 2 Closure, Candle 3 Closure, Wicks & Equilibrium, Ideal Formation; Swing Confirmation (44–48); POI (49–59); TTrades OSOK Model (60–94): Economic Calendar, Monday rule, Daily Swing, Weekly Profile, Hourly Confirmation, Daily Profile, Entry Logic; TTrades Fractal Model (95–99); Examples (100–118): OSOK on CL (crude oil) daily/1H/15m, Fractal on NQ 1H/5m |
| 2 | `Sons_Model.pdf` | 6 | p3–p5 (1–3) | Draw On Liquidity (1), Stop Raid (2), Entry (3) |
| 3 | `Sons_Model_HTF.pdf` | 9 | p3–p8 (1–6) | Two HTF variants: DOL/Stop Raid/Entry (1–3) and DOL/Stop Raid/Entry (4–6) |
| 4 | `TTrades Reversal Sequence (TTRS).pdf` | 18 | p3–p17 (1–15) | Killzones (1), Timeframes (2), Concepts (3–10): FVG, Inversion, OB, Breaker, OTE, Premium & Discount ×2, SMT; Order of reversal (11–15) |
| 5 | `Timeframe Alignement TTrades.pdf` | 7 | p3–p6 (1–4) | Top Down Analysis (1), Timeframe Alignment (2–3), Example (4) |
| 6 | `Unicorn_Model.pdf` | 7 | p3–p6 (1–4) | Fair Value Gaps (1), Breaker Blocks (2–3), Unicorn (4) |

Total: 165 physical pages, all read (text layer via `pdftotext -layout` plus full visual read of every page). Note: `Model11` pages carry a third-party watermark ("share group with your friends / t.me/...") on many pages — this is not TTrades content and is ignored. Some Model11 diagram pages carry an `_amtrades` watermark (p67, p69) rather than `TTrades_edu`.

---

## 2. Core concepts & models

### 2.1 Foundational concepts (Model11 Section 1)

#### 2.1.1 Opposing (close) candles
- `[text]` "During an intraday expansion, anticipate price to respect opposing close candles to the objectives." — `Model11 p5`.
- `[text]` Two principles for marking opposing close candles — `Model11 p5`:
  1. "If there are a series of opposing close candles, use the opening price of the first candle in the series." Series of **downclose** candles → "use the opening price of the **highest** downclose candle in the series". Series of **upclose** candles → "use the opening price of the **lowest** upclose candle in the series".
  2. "Ignore opposing close candles that are within a larger series of opposing close candles" — focus on the larger series.
- `[diagram]` p6: four panels. Panel 1 (bullish left / bearish right): a blue line at the open of the first (highest) downclose candle of a downclose run; price later closes above it and expands. Panel 2: a smaller inner series is shown with a dotted line and is **ignored**; the blue line stays on the larger series. — `Model11 p6`.
- `[text]` **Where to look**: "Opposing close candles should be supported by one of three points of interest; highs or lows, fair value gaps, and opposing close candles. Any opposing close candles which are not paired with a point interest should be ignored and avoided." — `Model11 p6`.
- `[text]` **Highs and Lows**: "Once either a high or low is swept, a closure through a series of opposing candles is the confirmation." — `Model11 p7`. `[diagram]` p7: a prior low (bullish) / high (bearish) is swept (dashed line), the run into the sweep is a series of same-colour candles, blue line at the open of the first candle of that run, close through it, expansion.
- `[text]` **SMT**: "Opposing close candles on the failure swing are used when an SMT is present." — `Model11 p8`. `[diagram]` p8: the second (failure) swing is joined to the first by a red-dotted divergence line; the opposing candle line is taken on the failure-swing leg, not the original swing.
- `[text]` **Fair Value Gaps**: "Once a fair gap is traded into, a closure through a series of opposing candles is the confirmation." — `Model11 p8`. `[diagram]` p9: the FVG (two grey lines) is traded into; the opposing-candle line sits at the FVG; close through it → expansion.
- `[text]` **Opposing Candles as POI for opposing candles**: "Opposing close candles which form in respect to a previous series of opposing close candles." — `Model11 p9`. `[diagram]` p10: a second, later opposing-candle line (blue) forms at/near the first one after the sweep; both hold as price expands (stacked opposing candles in a trend).

#### 2.1.2 Highs & Lows — framing reversals
- `[text]` "Reversals are framed at highs and lows and confirmed by the close through the opposing close candles which ran into the level. Below are the two steps to this process: Swing high or low formation; Opposing candles." — `Model11 p11–p12`.
- `[diagram]` p12–p13: bullish — a prior low (grey line) is swept by a wick, then a blue line is drawn at the open of the first downclose candle of the leg into the sweep; the close above that line is the confirmation and expansion follows. Bearish mirror at a swept high.

#### 2.1.3 Fair Value Gaps — usage
- `[text]` "Fair value gaps are only used for two purposes: Defining order blocks; Point of interest for swing highs and lows to form." — `Model11 p14–p15`.
- `[diagram]` p14 ("Defining order blocks"): the opposing-candle/OB line (blue) is drawn where an FVG exists on the reversal leg — the OB is the opposing candle that sits with the FVG. p15 ("Point of interest for swing highs and lows to form"): the FVG (grey lines) is where the swing forms and the opposing-candle line is validated. — `Model11 p14–p15`.

#### 2.1.4 Equilibrium (discount / premium)
- `[text]` "There are two ways discount and premium, or equilibrium is used in the model." — `Model11 p16`.
- `[text]` **Ranges**: "By using equilibrium of ranges, targets can be framed when trading back into the range. Equilibrium is also used to identify points of interest for trading out of the range. When trading into the range, equilibrium is an objective. When trading out of a range, equilibrium is a point of interest." — `Model11 p16`. `[diagram]` p17: multiple range boxes with dotted midlines; price respects the midpoint as it trades out of each range.
- `[text]` **Previous Candle Equilibrium**: "The main way equilibrium is applied within this model is by using equilibrium of the previous candle range or the previous candle wick." — `Model11 p17`.
- `[text]` "For reversals with large wicks, equilibrium of the previous candle **wick** is used as framework. The following candle should remain in respect to this level for a valid reversal." — `Model11 p18`. `[diagram]` p18: bullish — a candle with a long lower wick; the wick's midpoint is a dotted line; the next candle's low holds above/at that midpoint. Bearish mirror on an upper wick.
- `[text]` "For a continuation, equilibrium of the previous candle **range** is used as framework. The following candle should remain in respect to this level for a valid continuation." — `Model11 p18`. `[diagram]` p19: the full range (high to low) of the prior expansion candle is bracketed; dotted midline; the next candle holds the upper half (bullish) / lower half (bearish).

#### 2.1.5 Projections (standard deviations) — determining targets
- `[text]` "For the TTrades Model, the main focus for identifying targets is using standard deviation projections. There are two ways to project the reversal:" — `Model11 p20`.
- `[text]` **Manipulation Projection** ("the majority of scenarios"): "Bullish: low to the previous high which made the highest high. Bearish: high to the previous low which made the lowest low." — `Model11 p20`.
- `[text]` **Failure Swing Projection**: "The projection changes in certain scenarios when the manipulation leg is large. What is a large manipulation leg? When the projection is far overextended from any price logical objective for candle 3 or 4 to reach. Bullish: lowest low to the high which formed the failure swing. Bearish: highest high to the low which formed the failure swing." — `Model11 p21–p22`.
- `[diagram]` p21–p22: fib drawn with **1 at the manipulation extreme** (the swept low for bullish / swept high for bearish) and **0 at the origin** (prior high / prior low); negative levels project beyond 0 in the direction of the expansion. Two shaded target zones are drawn: **−2 to −2.5** and **−4 to −4.5**. — `Model11 p21, p22, p47`.
- `[diagram]` **Fibonacci tool settings** (p23): levels enabled = `1, 0, -1, -2, -2.5, -4, -4.5`. — `Model11 p23`.

### 2.2 Swing Highs & Lows — the foundation (Model11 Section 2)

#### 2.2.1 Candle numbering
- `[text]` "The market must form a swing high or low in order for price to reverse; there is no other way. Using that understanding is the foundation of the TTrades Model. There are 3 candles that form a swing high or low. The focus will be on those 3 candles with the 3rd and 4th candles having potential opportunity following the swing high or low." — `Model11 p24`.
- `[text]` Numbering — `Model11 p24`:
  - Candle 1 = the candle **before** the high or low
  - Candle 2 = the candle **that forms** the high or low
  - Candle 3 = the candle **following** the high or low
  - Candle 4 = the candle following candle 3
- `[diagram]` p25: bullish 1-2-3-4 (1 black, 2 small black with long lower wick making the low, 3 white, 4 large white); bearish mirror.
- `[text]` "The next two sections will discuss the two types of candle closures used to anticipate a swing formation." — `Model11 p25`.

#### 2.2.2 Candle 2 Closure (Reversal Candle Closure) — formation type 1
- `[text]` "Candle 2 — Bullish: takes the low of candle 1 and closes back above candle 1 low. Bearish: takes the high of candle 1 and closes back below candle 1 high." — `Model11 p26`.
- `[text]` "With a valid candle 2 closure, there is an anticipation for candle 3 to expand." — `Model11 p27`.
- `[text]` "With a strong bearish or bullish closure on candle 3, candle 4 is likely to be a continuation." — `Model11 p28`.
- `[diagram]` p27–p29: candle 2's wick pierces candle 1's low (bracket drawn from candle 1 low to candle 2 low) and the body closes back inside candle 1's range; candle 3 expands; candle 4 continues.

#### 2.2.3 Candle 3 Closure (Conditional Rule) — formation type 2
- `[text]` "Due to candle 2 failing to close inside the range of candle 1, more data is needed to determine if this is likely a swing formation. Allow candle 3 to form without participating, this is the best option in this scenario." — `Model11 p30`.
- `[text]` "If candle 3 forms a strong bearish or bullish candle close, this validates the formation of the swing. Due to this closure on candle 3, candle 4 becomes a likely continuation away from the previously established swing point." — `Model11 p31`.
- `[diagram]` p31–p33: candle 2 closes **beyond** candle 1's low (bullish) — i.e. it did not close back inside; candle 3 is a strong opposite-colour close; candle 4 continues.

#### 2.2.4 Wicks & Equilibrium (order-flow framework per formation)
- `[text]` "Candle wicks and the equilibrium of candle ranges are crucial to the understanding of order flow." — `Model11 p34`.
- `[text]` **Candle 2 Closure: Wick** — "With a candle 2 closure inside the range of candle 1, the wick is used to frame the candle 3 continuation. Bullish: the upper half of the wick to support price higher. Bearish: the lower half of the wick to support price lower." — `Model11 p34`. "Candle 3 remains in respect to equilibrium of the candle 2 wick." — `p35`. "With a strong closure of candle 3 in respect to the wick of candle 2, candle 4 is a probable continuation. The framework is used by taking equilibrium of the candle 3 range. Bullish: the upper half of candle 3 to support candle 4 higher. Bearish: the lower half of candle 3 to support candle 4 lower." — `p36`.
- `[text]` **Candle 2 Closure: No Wick** — "With a candle 2 closure lack[ing] a large wick for framework, equilibrium should be taken using the candle range. Bullish: the upper half of candle 2 to support price higher. Bearish: the lower half of candle 2 to support price lower." — `Model11 p37`.
- `[text]` **Candle 3 Closure: Condition** — "With candle 2 failing to close back within the range of candle 1, candle 3 should be avoided. Bullish: the upper half of candle 3 to support price higher. Bearish: the lower half of candle 3 to support price lower." "Candle 4 expansion occurs in respect to equilibrium of the candle 3 range." — `Model11 p38–p39`.
- `[diagram]` p35–p40: the wick or range being used is bracketed with a dotted midline; the subsequent candle's retracement stops at or above/below that midline.

#### 2.2.5 Ideal Swing Formation
- `[text]` "Coming from experience, this is the most ideal formation of a swing point." — `Model11 p41`.
  1. "Candle 2 closure back into the range of candle 1 with a large wick." — `p41`
  2. "Candle 3 expansion off the wick of candle 2 with a strong close which validates the opposing close candle." — `p42`
  3. "Candle 4 continuation from both the opposing close candle and in respect to equilibrium of candle 3 range." — `p42`
- `[diagram]` p42–p43: the blue opposing-candle line is at the **open of candle 1** (candle 1 is the last opposing-colour candle before the reversal); candle 3 closes through it; candle 4 retraces to that line **and** to the midpoint of candle 3's range, then continues.

### 2.3 Swing Confirmation — CISD confirmation & projection (Model11 Section 3)
- `[text]` "Lower timeframes are used for both change in state of delivery confirmation and anchoring projection targets. The swing formation is confirmed by a lower timeframe change in state of delivery (CISD) within candle 2. While the CISD is most often validated within candle 2, it can also be validated by candle 3." — `Model11 p44`.
- `[text]` **Timeframe Pairing** (Swing Point → CISD) — `Model11 p44` (repeated verbatim `p95`):

  | HTF swing point | LTF CISD |
  |---|---|
  | Weekly | 4 Hour |
  | Daily | 1 Hour |
  | 4 Hour | 15 Minute |
  | 1 Hour | 5 Minute |
  | 30 Minute | 3 Minute |
  | 15 Minute | 1 Minute |

- `[text]` "Candle 2 Closure CISD: Following a candle 2 closure, move to the lower timeframe to confirm the CISD within candle 2. Candle 3 Closure CISD: Following a candle 3 closure, move to the lower timeframe to confirm the CISD within candle 2 which can often be validated on candle 3." — `Model11 p44`.
- `[text]` **Step-by-step** — `Model11 p45–p47`: (1) "Following the candle 2 closure, the lower timeframes should be examined for a CISD confirmation." (2) "Identify and annotate the CISD which acts as a reversal confirmation." (3) "Projecting out the manipulation leg of the reversal for targets on candle 3 expansion and candle 4 continuation." (4) "The first projection target at −2 is reached with candle 3 expansion."
- `[diagram]` p45–p48: the HTF candles 1/2/3 are shown as vertical columns over the LTF chart. Within the candle-2 column, price sweeps the candle-1 high (dashed line), the last run of upclose candles into that high defines the CISD line (blue, at the open of the lowest upclose candle of the run); a close below it confirms. The fib is anchored 1 = candle-2 high, 0 = the low before the run-up (the manipulation leg); −2/−2.5 and −4/−4.5 zones are drawn below; candle 3 trades to the −2/−2.5 zone.

### 2.4 Point of Interest (POI) — where swing formations count (Model11 Section 4)
- `[text]` "It is crucial to understand that not every swing high or low should be considered as a trade opportunity." — `Model11 p4`.
- **Opposing candles as POI** — `[text]` "Opposing candles formed and validated on a close through. Price trades into the opposing candles and has a candle 2 closure within candle 1 range. Candle 2 closure at the opposing candle gives anticipation of candle 3 expansion." — `Model11 p49–p51`. `[diagram]` p50–p52: an earlier validated blue opposing-candle line; later price retraces into it, candle 2 wicks through it and closes back inside candle 1; candle 3 expands away.
- **Highs & Lows as POI** — `[text]` "High or low is swept and candle 2 closes back into the range. Candle 3 is an expansion away from the previously swept high or low in respect to candle 2." — `Model11 p53–p54`.
- **Fair Value Gaps as POI** — `[text]` "While the fair value gap is being retested, entries are not taken within candle 1 as the swing formation is yet to be confirmed in candle 2 or candle 3. Candle 2 closure confirms the swing point within the fair value gap. Candle 3 is an expansion away from the fair value gap in respect to candle 2." — `Model11 p56–p58`.

### 2.5 TTrades OSOK ("one-shot-one-kill") Model (Model11 Section 5)

`[text]` "The section on the TTrades OSOK Model combines all the previous sections into a one-shot-one-kill system. It includes lessons on the economic calendar, Monday rule, daily swings, hourly confirmation, daily profile, price objectives, and entry logic." — `Model11 p4`.

#### 2.5.1 Economic calendar (forexfactory.com/calendar)
- `[text]` Settings — Step 1: remove gray, yellow and orange folder events. Step 2: choose the currencies correlated to the market you trade. Step 3: set the calendar to the current-week view. Result: only **red-folder** events, current week, relevant currency. — `Model11 p60`.
- `[text]` Currency selection: "Indices: USD (direct correlation). Forex Major Pairs: USD (main focus) and the cross currency. **Crypto: USD (secondary correlation)**." — `Model11 p60`.
- `[text]` "The economic calendar is the foundation to anticipating market conditions. ... If the market is in anticipation for a news event, the previous price action is likely to be manipulative in the form of consolidations or opposing runs. If the market has released news events, the following price action is more likely to expand in the intended direction." — `Model11 p61–p62`.
- `[text]` "High Impact News ... will have an impact on the **weekly** range. This will determine the **days** which are chosen to seek potential trade opportunities. Medium Impact News ... will have an impact on the **daily** range. This will determine the **sessions** which are chosen to seek potential trade entries." — `Model11 p62`. "Expansion is a requirement to make money from the markets; without a directional move, there is no profit to be made." — `p62`.
- `[text]` **The Rules** — `Model11 p64`:
  1. "Avoid opening trades the **day prior** to a high impact news event."
  2. "Avoid opening trades any **session prior** to a medium impact news event." "Within the scenario there is a medium impact news event (or high impact news event) on a day you are seeking a potential trade opportunity, only seek entries **following the release**."
  3. "**Never hold** an open position through either a high or medium impact news event."
- `[text]` High impact events: Consumer Price Index M/M (CPI), Non-Farm Payroll (NFP), FOMC Press Conference. Medium impact events: Core PCE Price Index M/M, Producer Price Index M/M (PPI), FOMC Statement. — `Model11 p64–p65`. `[diagram]` p65 Venn: "avoid day prior" = CPI/NFP/FOMC Press Conference; "avoid session prior" = Core PCE/PPI/FOMC Statement; the three high-impact events fall in "both".
- `[diagram]` p61 sample calendar (all USD, red folder): Tue 8:30am Core CPI m/m, CPI m/m, CPI y/y; 1:01pm 10-y Bond Auction; Wed 1:01pm 30-y Bond Auction; Thu 8:30am Core PPI, Core Retail Sales, PPI, Retail Sales, Unemployment Claims, Empire State Mfg; Fri 8:30am/10:00am Prelim UoM Consumer Sentiment. p68 second sample: Tue 08:30 Core PCE; Wed 14:00 FOMC Statement, 14:30 FOMC Press Conference; Thu 08:30 CPI, 08:30 PPI; Fri 08:30 Non-Farm Employment Change. Times are shown as ForexFactory displays them (no timezone stated on the page; the example charts label NY open "NYO 8:30").

#### 2.5.2 Monday rule
- `[text]` "Monday is a day of the week that trading will be avoided in all scenarios." — `Model11 p66`. Three reasons:
  1. `[text]` "Based on data collected across the past three years, Monday is the smallest ranged day on average in both the range from the daily candle high to low and from the daily candle open to close." — `p66`. `[diagram]` p67 (watermark `_amtrades`): average ranges (high-low / open-close): Mon 262/129, Tue 310/158, Wed 316/166, Thu 332/179, Fri 312/163. Instrument and units are not stated on the page.
  2. `[text]` "There is never medium or high impact news events on Monday. ... on Monday, the market is always waiting in anticipation for something more significant." — `p67–p68`.
  3. `[text]` "Utilizing weekly range profiles ... on Monday there is no day within the week to look back on. ... avoiding Monday is an indisputable rule to simplify the approach." — `p68–p69`.

#### 2.5.3 Daily swing (daily chart analysis)
- `[text]` "The majority of the analysis is done on the daily chart. If the following daily candle cannot be anticipated with a clear one-sided expectation, then there is no reason to be seeking entries within that day. Look for a candle 2 or candle 3 closure on the daily chart at a point of interest. If a swing formation can be used to anticipate the next daily candle direction, then the analysis will continue." — `Model11 p70`.

#### 2.5.4 Weekly profiles (blending with daily swing points)
- `[text]` "Weekly profiles offer the element of time to the weekly range and partially reduces discretion by applying a series of 'if this, then that' statements." "Tuesday is more obvious than Monday, Wednesday is more obvious than Tuesday, Thursday is more obvious than Wednesday, and Friday is more obvious than Thursday." "What if you are unclear on the weekly profile at any point? Then you wait for another daily candle to print for additional narrative." — `Model11 p72`.
- `[text]` Four profiles: Classic Expansion, Midweek Reversal, Consolidation Reversal, Thursday Counter. — `p72`.
- `[text]` "Each weekly profile has a daily swing point which forms the high or low of week. The best trade opportunities exist within the candle 3 and candle 4 following the confirmation of the swing point on candle 2 close." — `p73`.
- `[diagram]` p73: Classic Expansion = M(1) T(2) W(3) Th(4) F; Midweek Reversal = M T(1) W(2) Th(3) F(4); Consolidation Reversal = M T W(1) Th(2) F(3); Thursday Counter = M T W(1) Th(2) F(3) with M/T/W all expanding the same way first.
- `[text]` "Determining the Weekly Profile: ... Following the hourly change in state of delivery at the relevant point of reversal on candle 2, look back on how the previous days traded. This will either invalidate or add to your anticipation for the following expansion." — `p73–p74`.
- **Classic Expansion** — `[text]` `Model11 p74`: "Anticipating a reversal on a Tuesday? Look back at how Monday traded. If Monday was consolidated or made a shallow opposing run from the weekly opening price, then the narrative is supported for Tuesday (candle 2) to reverse into an expansion. ... expectation? Wednesday (candle 3) and Thursday (candle 4) expansion away from the Tuesday reversal. If Monday had a large range expansion to either direction, then the narrative is not supported ... You then wait for the narrative to reestablish." Italic note: "This same logic applies to a classic expansion weekly profile which forms the reversal on a Monday. The only difference is that candle 1 is the Friday from the previous week."
- **Classic Expansion (Counter-Trend)** — `[text]` `Model11 p75–p76`: "Anticipating a reversal on a Friday? Look back at how Monday, Tuesday, Wednesday, and Thursday traded. If Monday or Tuesday formed an opposing reversal and expanded through Thursday, then the narrative is supported for Friday to reverse into an expansion. You then focus on trading back into **20.0% to 50.0%** back into the weekly range as an objective. If Monday or Tuesday did not form an opposing reversal or there was no expansion through Thursday, then the narrative is not supported ... You then end your trading week." Italic note: "**This is the only scenario within this model to seek trades on candle 2 within the anticipated swing point.**"
- **Midweek Reversal** — `[text]` `Model11 p77–p78`: "Anticipating a reversal on a Wednesday? Look back at how Monday and Tuesday traded. If Monday and Tuesday consolidated or make any amount of an opposing run from the weekly opening price, then the narrative is supported for Wednesday (candle 2) to reverse into an expansion. ... Thursday (candle 3) and Friday (candle 4) expansion away from the Wednesday reversal. If Monday and Tuesday expanded off another point of reversal, then the narrative is not supported."
- **Consolidation Reversal** — `[text]` `Model11 p79`: "Anticipating a reversal on a Thursday? Look back at how Monday, Tuesday, and Wednesday traded. If Monday, Tuesday, and Wednesday were consolidated, then the narrative is supported for a Thursday reversal into an expansion. ... Friday (candle 3) expansion away from the Thursday reversal (candle 2). If Monday, Tuesday, and Wednesday failed to consolidate, then the narrative is not supported."
- **Thursday Counter** — `[text]` `Model11 p80–p81`: "Anticipating a reversal on a Thursday? ... If Monday, Tuesday, and Wednesday each expanded in the same direction, then the narrative is supported for a Thursday reversal into an expansion. ... Friday (candle 3) expansion away from the Thursday (candle 2) reversal. If Monday, Tuesday, or Wednesday failed to expand in the same direction, then the narrative is not supported."

#### 2.5.5 Hourly confirmation
- `[text]` "After aligning the daily swing and the weekly profile, the hourly chart is used to identify a 1-hour change in state of delivery which confirms the candle 2 reversal. Once the CISD is established and confirmed, anchor the manipulation leg to project out the expansion targets for the following days of the week." — `Model11 p82`. `[diagram]` p83 bullish / p84 bearish: same CISD + projection drawings as §2.3 with daily candles 1/2/3 as columns over the hourly chart.

#### 2.5.6 Daily profiles
- `[text]` "For the TTrades Model, everything is refined down to only two daily profiles. 1. London Reversal 2. New York Reversal. Just as every week has a point of reversal, every day has a point of reversal. The intraday reversal which is framed through daily profiles is the foundation for how entries are positioned." — `Model11 p85`.
- `[text]` **London Reversal**: "If London reverses, then seek New York continuations." — `p85`. `[diagram]` p86: London sweeps a low, CISD (blue) forms in London; New York continues higher.
- `[text]` **New York Reversal**: "If London consolidates or makes an opposing run, then seek a New York reversal." — `p86`. `[diagram]` p87: London ranges; the low and CISD form at New York; expansion follows.
- `[text]` **Invalidation**: "If London expands in either direction, then avoid New York participation." — `p87`. `[diagram]` p88: "london expansion" runs up strongly; New York chops/reverses — no participation.

#### 2.5.7 Entry logic (OSOK entries)
- `[text]` "Entries are considered only after the following steps are completed: Identified a swing forming on the daily chart; Aligned with one of the four weekly profiles; Confirmed and projected targets on the hourly chart; Aligned the directional bias with a daily profile." — `Model11 p89`.
- `[text]` "The daily profile will be aligned after an intraday CISD is established. Following this signature, opposing candles and swing formations will be used for entries on the 15-minute, 5-minute, and sub 5-minute timeframes." — `p89`.
- `[text]` **CISD and Opposing Candle Entries**: "Entering following the confirmation of a relevant opposing candle; either market on the opening of the first candle following the validation or a limit on the opposing candles." — `p89`. `[diagram]` p90: entry (blue) at the opposing-candle line; STP (red) below the swing low.
- `[text]` **Candle 2 Closure Entry**: "With a valid candle 2 closure, enter on the opening of candle 3 with a stop loss on the candle 2 swing point." — `p90`. `[diagram]` p91: entry line at candle-3 open (= candle-2 close), STP at candle-2 low (bullish) / high (bearish).
- `[text]` **Candle 3 Closure Entry**: "With a valid candle 3 closure, enter on the opening of candle 4 with a stop loss on the candle 2 swing point." — `p91`. `[diagram]` p92: entry at candle-4 open, STP still at candle-2 extreme.
- `[text]` **Minimum Risk to Reward**: "2R is the minimum requirement before taking profit on an open position. Profit will be taken at projections, liquidity levels, opposing candles, and opposing swing formations." — `p92`. `[diagram]` p93: risk box (grey) below entry, reward box "2R minimum" above.
- `[text]` **Trailing Stop Loss**: "Stop loss will be trailed to opposing candles or validated swing points that should not be returned back to." — `p93`. `[diagram]` p94: three successive STP lines, each moved up to below the most recent validated swing low / opposing candle.
- `[diagram]` tick labels on the entry diagrams (p90 "−23 ticks", p91 "+86"/"+94 ticks", p92 "+76"/"+83 ticks", p93 "+379 ticks") are illustrative position P&L tags, not rules.

### 2.6 TTrades Fractal Model (Model11 Section 6)
- `[text]` "The TTrades Fractal Model is made up of three components: 1. Higher timeframe swing formations 2. Lower timeframe CISD confirmation and projection 3. Positioning entries within expansion candles." — `Model11 p95`.
- `[text]` "Candle 2 closure: finding lower timeframe entries within candle 3 and candle 4. Candle 3 closure: finding lower timeframe entries within candle 4." — `p95`.
- `[text]` Timeframe pairings: identical table to §2.3 (Weekly→4H, Daily→1H, 4H→15m, 1H→5m, 30m→3m, 15m→1m). — `p95`.
- `[text]` Example walk-through — `Model11 p95–p98`:
  1. "On the higher timeframe, there is a valid candle 2 closure. The next step is to identify a lower timeframe CISD to confirm the anticipated swing formation."
  2. "Annotate the CISD and anchor the projection for targets on the lower timeframe. In addition to this, mark out equilibrium of the candle 2 wick on the higher timeframe. Price should remain in respect to equilibrium of the candle 2 wick in order to begin trading towards objectives."
  3. "Candle 3 expanded away from the candle 2 swing point while remaining in respect to equilibrium of the higher timeframe wick. Several entries off opposing close candles and swing formations are offered within candle 3."
  4. "With a valid closure, annotate the equilibrium of the candle 3 range. Identify a lower timeframe point of interest which remains in respect to equilibrium of the candle 3 range as that provides framework for a candle 4 continuation."
  5. "Candle 4 is a continuation in respect to equilibrium of the candle 3 range and trades to the −4 projection."
- `[diagram]` p96–p99: HTF candles 1–4 as columns; within candle 3 and candle 4, nested LTF 1-2-3-4 swing formations (labelled 2,3,4 in small type) appear at each opposing-candle retest, each offering an entry; −2/−2.5 reached in candle 3, −4/−4.5 in candle 4. The pairing row `H4/W1, H1/D1, M15/H4, M5/H1, M3/M30, M1/M15` is printed under each chart (LTF above HTF).

### 2.7 Worked examples (Model11 Section 7)

#### 2.7.1 OSOK example — CL (crude oil futures, `CL1!`), 26 Apr – 1 May 2024
- Daily — `[text]` "Following the valid candle 2 closure, equilibrium of the wick is annotated in order to frame candle 3. It is expected that candle 3 is an expansion to the downside while remaining in respect to the lower half of the candle 2 wick." — `Model11 p100`. `[diagram]` p100: daily candle 2 (26 Apr) wicks above candle 1's high and closes back inside; a prior daily low sits below.
- Hourly — `[text]` "The CISD is identified and annotated on this hourly chart as the opening price of the lowest upclose candle in the series of upclose candles which reversed price. Once price closes below this level to confirm the reversal, the projection is anchored to the manipulation leg." "On the following day which is candle 3, New York session trades back into the opposing close candles on the hourly chart. This is an area that is expected to resist price in order to begin trading to the downside." — `p100–p102`.
- 15-minute — `[text]` "Did London form a high and reverse? No, so the daily profile is not a London Reversal. Did London make an opposing run back into the range within a point of interest? Yes, so the daily profile is a New York Reversal." "What are the targets for a bearish New York Reversal daily profile? London Lows, Asia Lows, Projections. With the targets marked out on the chart, wait for an intraday CISD to be established before attempting to get onside with the expansion." — `p102–p103`.
- `[text]` "During the New York session, the market displaces lower. ... The CISD is confirmed with this displacement lower as there is a close below the opening price of the lowest upclose candle within the series of upclose candles. This is expected to be the high of candle 3 and the expansion can begin to the downside. Projections are then anchored on the manipulation leg in the same way it is done on the higher timeframe. The opposing close candles create swing highs for price to push lower into the overnight lows and projected targets. Several entries are offered within the candle 3 expansion." — `p103–p105`. `[diagram]` p104–p105: chart labels "NYO 8:30" mark the New York open.
- Candle 4 framing — `[text]` "Following the candle 3 closure, move back out to the daily chart ... Candle 3 had a strong bearish close which validated the upclose candle as a point of interest; this is the ideal swing formation. Annotate both the opening price of the upclose candle and equilibrium of the candle 3 range. It is expected that candle 4 will offer a continuation to the downside while remaining in respect to the opposing candle and equilibrium of candle 3 range." — `p105–p106`. Hourly: "Identify a point of interest within the lower half of the candle 3 range and around the opening price of the daily upclose candle. Opposing close candles are annotated as a point of interest in the lower half of the candle 3 range. Price trades up into the point of interest on the hourly chart." — `p106–p107`.
- 15-minute, candle 4 — `[text]` same two London questions → New York Reversal. "With the targets marked out on the chart, wait for an intraday CISD to be established before attempting to get onside with the continuation. **As there is yet to be a confirmed CISD, no entry is to be taken.** With the higher high being made, the CISD moves to the newly established upclose candles. Following the formation of a new high and a valid candle 2 closure, there is a lower series of candles that made the new high. Mark out this opposing candle on the 15-minute chart. This upclose candle provides the confirmation of a CISD with the close below. Anchor the projections from the low of the move up that made the new higher high." — `p107–p110`.
- Entry & management — `[text]` "The candle 2 closure below validates the opposing candles and the entry is on the open of candle 3 with a stop loss at the high of candle 2. The first target is achieved at the overnight low which is beyond the 2R minimum requirement. The second target is achieved at the −4 projection from the intraday manipulation leg. The third target remains open for a candle 5 continuation lower while remaining in respect to equilibrium of the candle 4 range. All targets are traded through." — `p111–p113`.
- `[text]` "While possible, it is not necessary to trade the candle 2 reversal at the highs. The continuations which follow on candle 3 and candle 4 often give both a larger expansion and a more simple framework to trade." — `p113`. `[diagram]` p114: final daily chart with candles 1-2-3-4 labelled and the swept prior daily low reached.

#### 2.7.2 Fractal example — NQ (`NQ1!`), 20 Jun 2024, 1H → 5m
- `[text]` "The valid candle 2 closure within the range of candle 1 gives the anticipation for the following hourly candle 3 to be an expansion to the downside." — `Model11 p115`.
- `[text]` "Moving down to the 5-minute chart from the hourly, identify a change in state of delivery within candle 2 in order to confirm the swing formation. Once identified and confirmed with a close through, anchor the manipulation leg to project targets for the candle 3 expansion and candle 4 continuation lower. Also, annotate equilibrium of the hourly candle 2 wick as the lower half should be respected." — `p115`.
- `[text]` "Price respects the opposing close candles at the equilibrium of the candle 2 wick. This signature forms a valid candle 2 closure on the 5-minute chart which offers an additional sell entry. Price validates a new upclose candle as it moves lower off the previous candle 2 closure. Both the retest of the upclose candle and the valid candle 3 closure offer an entry to get onside with the move lower." — `p116–p117`.
- `[text]` "As the hourly candle 3 closed strong to the downside, mark out equilibrium of the candle 3 range as candle 4 should trade lower in respect to the lower half of the range. The hourly range can be refined by identifying opposing candles on the 5-minute within the lower half of the candle 3 range; these act as the point of interest. The opposing close candles within the lower half of the hourly candle 3 range provide framework for the candle 4 continuation lower. Maximum expansion is achieved once the −4 projection is traded into." — `p117–p118`. `[diagram]` p118: an "8:00" time label sits next to the candle-4 consolidation/expansion zone (the earlier "8:30" reading was a misread).

### 2.8 Timeframe Alignment deck
- `[diagram]` **Top Down Analysis** (three panels) — `TFA p3 (1)`:
  - **Bias** (HTF) (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`): a **green candle with a long upper wick** — it is the candle that sweeps and gets rejected (Model11 candle 2 shape); then a **black full-bodied candle whose high is below the green candle's high** and whose body closes below the green candle's low (candle 3 expansion); a third grey (expected) candle drawn lower = candle 4 continuation. The bias is read after the expansion candle closes, not after the sweep candle.
  - **Structure** (mid TF): price sweeps a prior high (dashed); the run into it is one green candle, three small black pullback candles, then a **single green candle that sweeps the dotted high**; the blue **CISD** line sits at the open of that last green candle (the first — and only — candle of the final up-close run); close below it.
  - **Entry** (LTF): a black candle first **closes below** the blue **OB** line (open of the last upclose series — an LTF CISD through the OB); the retest is a green candle whose upper wick touches the line without closing above it; then expansion. Grey box above = risk, green box below = reward.
- `[diagram]` **Timeframe Alignment** — `TFA p4 (2)`: Structure (CISD) and Entry (OB) panels only, same drawings.
- `[diagram]` **Pairing table** — `TFA p5 (3)`: Weekly→H4, Daily→H1, H4→M15, H1→M5, M30→M3, M15→M1 (identical to Model11 pairings).
- `[diagram]` **Example** — `TFA p6 (4)`: Structure chart (HTF): uptrend, then decline into a **Key Level** = a prior swing low from the left (dotted line), with a circle highlighting the candle that reaches it. Entry chart (LTF zoom): a lower low sweep (dotted line at the prior LTF low), a blue OB/CISD line at the open of the last downclose run, the close above it, entry with green reward box above and grey risk box below. Bottom row of pairs printed as `H4/W1, H1/D1, M15/H4, M5/H1, M3/M30, M1/M15`.
- No prose in the deck beyond titles.

### 2.9 TTrades Reversal Sequence (TTRS) — "Build an entry model"
- Subtitle `[text]`: "Find an entry model that works for you." — `TTRS p1`.
- **Killzones** (`[diagram]` clock, labelled "Eastern Standard Time (EST)") — `TTRS p3 (1)`:
  - Asia: 20:00–00:00
  - London: 02:00–05:00
  - NY AM – Forex: 07:00–10:00
  - NY AM – Indices: 08:30–11:00
  - London Close – Forex: 10:00–12:00
  - NY PM – Indices: 13:30–16:00
- **Timeframes** `[text]` — `TTRS p4 (2)`: "Choose an entry timeframe that suits your personality. Impatient people are generally better suited with a lower time frame entry. Patient people are generally better suited on a higher time frame for entry." Labels: **M15 (Patient)**, **M1 (Impatient)**.
- **Concepts** (`[diagram]` only):
  - FVG — `p5 (3)`: three-candle sequence numbered 1-2-3; gap lines at candle-1 low / candle-3 high (bearish) and candle-1 high / candle-3 low (bullish).
  - Inversion — `p6 (4)`: a bearish FVG on the way down is closed through by the reversal; retested from above as support; continuation up.
  - OB — `p7 (5)`: "Important Level" (yellow) above/below; prior swing swept (dotted) and the sweep wick pierces the Important Level itself; **OB** blue line at the open of the last opposing-colour candle before displacement; identical to the CISD construction in `05-ttrades-core-B` §2.3/2.5.
  - Breaker — `p8 (6)`: bearish: high (▼) → low (▲) → higher high (▼) → displacement below the low (▲); blue box on the candles that formed the low. Bullish mirror.
  - OTE — `p9 (7)`: fib from swing high (1) to swing low (0) on a bearish leg, with levels **0.79, 0.705 (highlighted), 0.62, 0.5**; the retracement into 0.62–0.79 is the OTE zone.
  - Premium & Discount — `p10 (8)` bullish: range low→high, 0.5 EQ line; a bullish FVG (two lines) sits in the **discount** half; the last candles turn down toward it but the slide stops above 0.5 (the return is implied, not drawn). `p11 (9)` bearish: OB/CISD line (blue) sits in the **premium** half; price falls into discount.
  - SMT — `p12 (10)`: "Stronger Asset" makes a higher low while "Weaker Asset" makes a lower low (yellow divergence lines); both then rally.
- **Order of reversal** (`[diagram]`, one element added per slide) — `TTRS p13–p17 (11–15)`:
  1. **turtle soup** — a prior low (dotted) is swept; pink box marks the sweep. `p13 (11)`
  2. **inversion** — the bearish FVG left on the way down is closed through and marked (two lines, label 2). `p14 (12)`
  3. **cisd / ob** — blue line at the open of the last downclose run before the up-move; the close above it (label 3). `p15 (13)`
  4. **fvg** — the bullish FVG created by the displacement candle (yellow box, label 4), sitting just above the CISD line; price retests it. `p16 (14)`
  5. **breaker** — grey box (label 5) from the **swing high** (wick of the first down-close candle, which is also the CISD-line candle) down to the **swept prior low**: it encloses the up-close candles that made the high *and* the down-close candles into the sweep, i.e. the whole pre-sweep swing, both colours (re-verified against the PDF at 110–150 dpi, 2026-09-12 — `docs/audits/2026-09-12-ict-pdf-recheck.md`). Same construction on `p8 (6)` and `Unicorn p5`. `p17 (15)`
  Sequence reads: liquidity sweep → inversion → CISD/OB → FVG → breaker. The deck draws **one** pullback candle that wicks through the FVG (4), through the CISD line (3) and into the breaker box (5) in a single move, then expands — three nested zones and one confluence retest, not three separate retests (§6 item 16).

### 2.10 ICT Son's Model (as presented by TTrades)
- Three steps `[text]`: 1 Draw On Liquidity, 2 Stop Raid, 3 Entry. — `Sons p2`.
- **Draw On Liquidity** — `[diagram]` "H1 or M15 Chart": a prior swing high (red arc, line extended right) is the draw; a prior swing low (red arc) is the level being raided; price sells off into the low and reverses up toward the high. — `Sons p3 (1)`.
- **Stop Raid** — `[diagram]` "M5 Chart": "Draw On Liquidity" line above; a prior M5 swing low (dotted) is swept by a yellow-highlighted green candle that closes back above the low ("Stop Raid"); price then rallies. — `Sons p4 (2)`.
- **Entry** — `[diagram]` "30s Chart": "M5 Stop Raid" line at the low; after the raid, a displacement up leaves a gap (two horizontal lines: the high of the candle before the displacement candle and the low of the candle after it — an FVG); price retraces into it and expands to the draw. — `Sons p5 (3)`.
- **HTF variant** — `Sons_HTF`: identical drawings at two higher scales:
  - Variant A: DOL on **H4 or H1** → Stop Raid on **M15** → Entry on **1m** ("M15 Stop Raid" line). — `Sons_HTF p3–p5 (1–3)`.
  - Variant B: DOL on **D1 or H4** → Stop Raid on **H1** → Entry on **m5** ("H1 Stop Raid" line). — `Sons_HTF p6–p8 (4–6)`.
- No prose beyond titles and chart labels in either deck.

### 2.11 Unicorn Model
- Contents `[text]`: 1 Fair Value Gaps, 2 Breaker Blocks, 4 Unicorn (numbering skips 3 in the deck). — `Unicorn p2`.
- **FVG** — `[diagram]` `Unicorn p3 (1)`: bearish FVG = gap between candle-1 low and candle-3 high across a down candle; bullish mirror.
- **Breaker Blocks** — `[diagram]` `Unicorn p4 (2)`: bearish: swing high (▼), swing low (▲), higher high (▼, sweep of the first high — dotted line), then a large black candle closes below the swing low (▲ lower low). Bullish mirror. `p5 (3)`: the grey **breaker box** is drawn over the candles that formed the swing low between the two highs (bearish) / the swing high between the two lows (bullish).
- **Unicorn** — `[diagram]` `Unicorn p6 (4)` "Bearish Breaker Block + FVG" / "Bullish Breaker Block + FVG": the displacement candle that breaks structure leaves an FVG (two lines) whose range **overlaps the breaker box**; the overlap is the Unicorn entry zone; price retraces into it and continues.
- Cross-reference: the same construction with more steps is in `19. BreakerBlocks.pdf` (see `08-ttrades-core-B` §2.7).

---

## 3. Actionable rules / checklists (IF/THEN)

### 3.1 TTrades OSOK Model — full sequence (`Model11 p60–p94`, example p100–p114)

**Context (week/day filter)**
1. IF today is Monday THEN no trading, in all scenarios. — `p66`
2. IF tomorrow has a high-impact event (CPI, NFP, FOMC Press Conference) THEN do not open trades today. — `p64`
3. IF a medium-impact event (Core PCE, PPI, FOMC Statement) or high-impact event falls later today THEN do not open trades in the sessions before it; only seek entries after the release. — `p64`
4. IF holding a position into any high/medium-impact release THEN close it — never hold through. — `p64`

**Setup (daily swing)**
5. On the daily chart, IF there is a candle 2 closure (wick through candle-1 extreme, close back inside candle-1 range) at a POI (swept high/low, FVG, or validated opposing candle) THEN anticipate candle 3 expansion away from the swing. — `p26–p27, p70`
6. IF candle 2 failed to close back inside candle 1 THEN do not participate in candle 3; wait. IF candle 3 then closes strongly in the reversal direction THEN anticipate candle 4 continuation. — `p30–p31`
7. IF the next daily candle cannot be anticipated with a clear one-sided expectation THEN no entries that day. — `p70`
8. Mark the framework: candle-2 wick EQ (large wick) or candle-2 range EQ (no wick) — the next candle must hold the correct half. After a strong candle 3, mark candle-3 range EQ — candle 4 must hold the correct half. — `p34–p39`

**Setup (weekly profile alignment)** — `p74–p81`
9. Tuesday reversal candidate: IF Monday consolidated or made a shallow opposing run from the weekly open THEN Classic Expansion is supported → expect Wed (c3) + Thu (c4) expansion. IF Monday expanded large either way THEN not supported → wait.
10. Wednesday reversal candidate: IF Mon+Tue consolidated or made any opposing run from the weekly open THEN Midweek Reversal → expect Thu (c3) + Fri (c4). IF Mon+Tue expanded off another reversal THEN not supported.
11. Thursday reversal candidate: IF Mon+Tue+Wed all consolidated THEN Consolidation Reversal → expect Fri (c3). IF Mon+Tue+Wed all expanded the same direction THEN Thursday Counter → expect Fri (c3). Otherwise not supported.
12. Friday reversal candidate: IF Mon or Tue formed an opposing reversal and price expanded through Thu THEN Classic Expansion (Counter-Trend) → trade back into 20–50% of the weekly range; this is the ONLY case where entries are sought on candle 2 itself. Otherwise end the week.
13. IF the weekly profile is unclear THEN wait for another daily candle. — `p72`

**Trigger (hourly confirmation)**
14. IF a 1H CISD forms inside daily candle 2 (or, for a candle-3 closure, inside candle 2 often validated on candle 3) THEN the daily swing is confirmed. CISD line = open of the first candle of the final opposing-colour run into the swing; trigger = close through it. — `p44, p82, p101`
15. THEN anchor the fib on the manipulation leg (1 at the manipulation extreme, 0 at the origin high/low that made the highest high / lowest low) and mark −1, −2, −2.5, −4, −4.5. IF the manipulation leg is far overextended THEN use the failure-swing anchor instead (lowest low → failure-swing high / highest high → failure-swing low). — `p20–p23, p82`

**Trigger (daily profile)** — `p85–p88`, example `p102, p108`
16. Ask: Did London form a high/low and reverse? IF yes → London Reversal → seek New York continuation.
17. Ask: Did London consolidate or make an opposing run back into the range at a POI? IF yes → New York Reversal → seek the New York reversal; targets = London lows/highs, Asia lows/highs, projections.
18. IF London expanded in either direction THEN avoid New York.

**Entry** — `p89–p92`
19. Wait for an intraday CISD (15m / 5m / sub-5m). IF no confirmed CISD THEN no entry ("As there is yet to be a confirmed CISD, no entry is to be taken." `p108`).
20. IF a higher high (bearish case) is made during the wait THEN the CISD moves to the newly established upclose candles — re-mark. — `p109`
21. Entry types (choose one):
    - Opposing-candle entry: market at the open of the first candle after the CISD validation, or limit at the opposing candle line. — `p89`
    - Candle 2 closure entry (LTF swing): enter at the open of candle 3; stop at the candle-2 swing point. — `p90`
    - Candle 3 closure entry (LTF swing): enter at the open of candle 4; stop at the candle-2 swing point. — `p91`

**Stop / Target / Management**
22. Stop = candle-2 swing point (high for shorts, low for longs). — `p90–p91`
23. Minimum 2R before any profit is taken. Take profit at projections (−2/−2.5, −4/−4.5), liquidity levels (overnight/London/Asia lows or highs), opposing candles, opposing swing formations. — `p92`, example `p111–p112`
24. Trail the stop to opposing candles or validated swing points that should not be revisited. — `p93–p94`
25. IF the −4 projection is reached THEN maximum expansion is achieved (fractal example). A third target may be left open for a candle-5 continuation while price respects candle-4 range EQ. — `p112, p118`
26. Prefer trading candle 3 / candle 4 continuations over the candle 2 reversal itself. — `p113`

### 3.2 TTrades Fractal Model — any timeframe (`Model11 p95–p99`, example p115–p118)
1. Pick an HTF from the pairing table; IF a valid candle 2 closure forms on the HTF THEN go to the paired LTF.
2. IF a CISD forms on the LTF inside HTF candle 2 THEN confirm the swing; annotate the CISD; anchor the manipulation-leg fib on the LTF.
3. Mark HTF candle-2 wick EQ (or range EQ if no large wick). IF price keeps to the correct half THEN begin trading toward objectives; entries inside HTF candle 3 come from LTF opposing-candle retests and nested LTF candle 2 / candle 3 closures.
4. IF HTF candle 3 closes strong THEN mark candle-3 range EQ; find LTF opposing candles inside the correct half of candle 3; these are the POI for candle 4 entries.
5. Targets: −2/−2.5 zone in candle 3; −4/−4.5 in candle 4 (maximum expansion). Stops per §3.1 rule 22; 2R minimum per §3.1 rule 23.
6. Candle 3 closure variant: IF HTF candle 2 did not close back inside candle 1 but candle 3 closed strongly THEN entries are sought only within candle 4.

### 3.3 ICT Son's Model (`Sons p3–p5`, `Sons_HTF p3–p8`) — `[diagram]`-derived
1. Context: on the DOL timeframe (H1/M15; or H4/H1; or D1/H4) identify the draw on liquidity (an untested swing high for longs / low for shorts) and the opposing pool that will be raided.
2. Setup: on the stop-raid timeframe (M5; or M15; or H1) wait for a candle to trade below a prior swing low (longs) and close back above it (the stop raid). Mirror for shorts.
3. Trigger/Entry: on the entry timeframe (30s; or 1m; or M5) after the raid, wait for a displacement away from the raid low that leaves an FVG; enter on the retrace into that gap.
4. Stop: not stated in the deck (see §6). Target: the draw on liquidity from step 1.

### 3.4 TTRS Order of Reversal (`TTRS p13–p17`) — `[diagram]`-derived
1. Context: trade inside a killzone (EST times in §2.9). Choose entry TF by temperament: M15 (patient) or M1 (impatient). Use premium/discount: longs from discount (below 0.5 of the range), shorts from premium.
2. Step 1 turtle soup: a prior low (longs) is swept.
3. Step 2 inversion: the bearish FVG on the way down is closed through and now acts as support.
4. Step 3 CISD/OB: close above the open of the last downclose run → reversal confirmed; the OB line is an entry reference.
5. Step 4 FVG: the displacement leaves a bullish FVG just above the CISD line.
6. Step 5 breaker: the whole pre-sweep swing (swing high down to the swept low, both candle colours) becomes a breaker box. Steps 3–5 are nested at one price region; the deck shows a single retest through all three followed by expansion. Treat OB line ∩ FVG ∩ breaker as **one** location at a higher quality grade (`10-integrated-method` §4.3), not three entries.
7. Optional confluence: SMT (stronger asset fails to make the lower low) at step 1; OTE (0.62–0.79, 0.705 focus) for the retracement entry.
8. Stops/targets: not stated in the deck (see §6).

### 3.5 Unicorn (`Unicorn p3–p6`) — `[diagram]`-derived
1. Identify a breaker: high → low → higher high sweep → displacement close below the low (bearish) / mirror.
2. Draw the breaker box over the candles that formed the intermediate low (bearish) / high (bullish).
3. Confirm an FVG on the displacement candle whose range overlaps the breaker box.
4. Entry: limit or reaction in the overlap zone on the retrace. Stop/target: not stated in the deck (the 19. Breaker deck in `08-ttrades-core-B` covers breaker stop placement).

### 3.6 Timeframe Alignment (`TFA p3–p6`)
1. Bias TF: read the HTF candle profile — a sweep-and-reject candle (long wick, Model11 candle 2) **followed by a full-bodied expansion candle closing beyond it** (candle 3) → expect the next HTF candle (candle 4) to continue. The bias is decided after the expansion candle closes (`TFA p3`, §2.8).
2. Structure TF (one pairing step down): find the sweep + CISD confirming the bias.
3. Entry TF (next pairing step down, or the LTF of the pair): enter on the OB/CISD retest with the risk box beyond the OB and reward toward the draw.
4. Pairings: Weekly→H4, Daily→H1, H4→M15, H1→M5, M30→M3, M15→M1.

---

## 4. Patterns with identification criteria

### 4.1 Valid Candle 2 Closure (reversal formation) — `Model11 p26–p29`
Must be true: candle 2's range exceeds candle 1's low (bullish) / high (bearish); candle 2's **close** is back inside candle 1's range; the swing forms at a POI (`p49–p58`). Must NOT: candle 2 closing beyond candle 1's extreme (that becomes the conditional formation). Confirmed by: LTF CISD inside candle 2 (`p44`). Invalidated if: the following candle fails to hold candle-2 wick EQ (large wick) or candle-2 range EQ (no wick) (`p34–p37`).

### 4.2 Valid Candle 3 Closure (conditional formation) — `Model11 p30–p33, p38–p39`
Must be true: candle 2 failed to close inside candle 1; candle 3 closes strongly in the reversal direction. Must NOT: enter during candle 3. Confirmed by: LTF CISD inside candle 2, often validated on candle 3 (`p44`). Continuation framework: candle-3 range EQ (`p39`).

### 4.3 Ideal Swing Formation — `Model11 p41–p43`
Candle 2 closes back inside candle 1 with a large wick; candle 3 expands off the wick with a strong close through the opposing candle (open of candle 1's opposing-colour body); candle 4 continues off both the opposing candle and candle-3 range EQ.

### 4.4 Opposing (close) candle level — `Model11 p5–p10`
Must be true: level = open of the first candle of a same-colour run (highest downclose / lowest upclose); the run is paired with a POI (swept high/low, FVG, or a prior opposing candle series); validated by a close through it. Must NOT: be an inner series inside a larger same-colour series; be unpaired with a POI.

### 4.5 CISD (as used in these models) — `Model11 p44–p48, p101, p104, p110`; `TFA p3–p4`; `TTRS p15`
Must be true: a sweep of a prior high/low or arrival at a POI; the final run of opposing-colour candles into it; a candle **close** through the open of the first candle in that run. Level moves to the newest opposing-colour run if a new extreme is made before confirmation (`p109`). Not confirmed by wicks.

### 4.6 Weekly profiles — `Model11 p73–p81`
| Profile | Candle 1 | Candle 2 (reversal day) | Candle 3 / 4 | Precondition on prior days |
|---|---|---|---|---|
| Classic Expansion | Mon (or prior Fri if reversal is Mon) | Tue (or Mon) | Wed / Thu | Mon consolidated or shallow opposing run from weekly open |
| Classic Expansion (Counter-Trend) | Thu | Fri (trades ON candle 2) | — (target 20–50% of weekly range) | Mon or Tue reversal that expanded through Thu |
| Midweek Reversal | Tue | Wed | Thu / Fri | Mon+Tue consolidated or any opposing run from weekly open |
| Consolidation Reversal | Wed | Thu | Fri | Mon+Tue+Wed consolidated |
| Thursday Counter | Wed | Thu | Fri | Mon+Tue+Wed all expanded the same direction |

### 4.7 Daily profiles — `Model11 p85–p88`
London Reversal: London sweeps a level and forms the CISD → NY continues. New York Reversal: London consolidates or makes an opposing run into a POI → NY sweeps and forms the CISD. Invalid: London expands directionally → no NY participation.

### 4.8 Sons Model — `Sons`, `Sons_HTF` (`[diagram]`)
Must be true: an identifiable DOL on the HTF; a stop raid (wick below prior LTF low, close back above) on the mid TF; a displacement + FVG on the entry TF after the raid. Entry = FVG retrace. The three TFs must be one of the three listed triplets.

### 4.9 TTRS reversal — `TTRS p13–p17` (`[diagram]`)
Must be true, in order: sweep (turtle soup) → inversion of the prior FVG → CISD/OB close → FVG from the displacement → breaker retest. Optional: SMT at the sweep; OTE retrace; discount/premium alignment; inside a killzone.

### 4.10 Unicorn — `Unicorn p4–p6` (`[diagram]`)
Must be true: breaker (sweep of a swing high/low then displacement through the opposite swing) AND an FVG on the displacement candle that **overlaps** the breaker box. A breaker without an overlapping FVG is a plain breaker, not a Unicorn.

---

## 5. Quantitative details

| Item | Value | Source |
|---|---|---|
| Timeframe pairings (swing → CISD) | W→4H, D→1H, 4H→15m, 1H→5m, 30m→3m, 15m→1m | `Model11 p44, p95`; `TFA p5 (3)` |
| Sons Model TF triplets (DOL → raid → entry) | H1/M15 → M5 → 30s; H4/H1 → M15 → 1m; D1/H4 → H1 → M5 | `Sons p3–p5`; `Sons_HTF p3–p8` |
| Fib projection levels | 1, 0, −1, −2, −2.5, −4, −4.5 | `Model11 p23` |
| Target zones drawn | −2 to −2.5 (candle 3); −4 to −4.5 (candle 4, "maximum expansion") | `Model11 p21–p22, p47, p98, p112, p118` |
| Fib anchor | 1 = manipulation extreme; 0 = origin (prev. high that made the highest high / prev. low that made the lowest low); failure-swing variant when the leg is overextended | `Model11 p20–p22` |
| Equilibrium | 0.5 of previous candle wick (reversal, large wick), 0.5 of previous candle range (continuation / no wick); 0.5 of ranges as objective (into range) or POI (out of range) | `Model11 p16–p19, p34–p39` |
| OTE levels | 0.79, 0.705 (highlighted), 0.62, 0.5 on a 1→0 retracement | `TTRS p9 (7)` |
| Counter-trend Friday objective | 20.0%–50.0% back into the weekly range | `Model11 p76` |
| Minimum R:R | 2R before taking profit | `Model11 p92` |
| Stop placement | candle-2 swing point (both entry types) | `Model11 p90–p91` |
| Entry timeframes (OSOK) | 15m, 5m, sub-5m | `Model11 p89` |
| Entry timeframes (TTRS) | M15 (patient), M1 (impatient) | `TTRS p4 (2)` |
| Killzones (EST) | Asia 20:00–00:00; London 02:00–05:00; NY AM Forex 07:00–10:00; NY AM Indices 08:30–11:00; London Close Forex 10:00–12:00; NY PM Indices 13:30–16:00 | `TTRS p3 (1)` |
| NY open reference on example charts | "NYO 8:30" | `Model11 p104–p105, p107–p112` |
| High-impact events | CPI m/m, NFP, FOMC Press Conference | `Model11 p64` |
| Medium-impact events | Core PCE m/m, PPI m/m, FOMC Statement | `Model11 p64–p65` |
| Monday average range (3-yr data, instrument unstated) | Mon 262/129, Tue 310/158, Wed 316/166, Thu 332/179, Fri 312/163 (high-low / open-close) | `Model11 p67` |
| Calendar currency | Indices USD; FX USD + cross; Crypto USD (secondary) | `Model11 p60` |
| Example instruments | CL1! (crude oil) daily/1H/15m, 26 Apr–1 May 2024; NQ1! 1H/5m, 20 Jun 2024 | `Model11 p100–p118` |

No other thresholds (wick size for "large wick", "strong close" body ratio, "shallow" vs "large" Monday range, consolidation definition) are quantified in the sources.

---

## 6. Conflicts, ambiguities, gaps

1. **Candle 2 "closes back above candle 1 low" vs "closes inside the range of candle 1"** — `Model11 p26` states the rule as close back above/below the candle-1 extreme; `p30` and `p34` restate it as "inside the range of candle 1". These coincide except when candle 2 closes beyond candle 1's *other* extreme (an engulfing reversal). The source does not address that case; treat "inside candle 1 range" as the operative test and flag engulfing closes for review.
2. **Which candle's open is the "opposing candle" in the ideal formation** — `p42–p43` draw the blue line at the open of **candle 1**, whereas `p5` defines the level as the open of the first candle of the whole opposing-colour run. Consistent only if candle 1 is the first (highest/lowest) candle of that run. Detector should compute the run, not assume candle 1.
3. **CISD validated "within candle 2" vs "on candle 3"** — `p44` allows the CISD to print during HTF candle 3 for the candle-3-closure formation. The candle-2-closure entry (open of candle 3) can therefore fire before the LTF CISD exists. The OSOK example (`p108`) says "no entry" without a CISD; the Fractal example enters on nested LTF candle-2 closures after the CISD. Reconcile: LTF CISD is a prerequisite; HTF candle 2/3 closure entries are taken only once the CISD exists.
4. **"Expansion / retracement / reversal / consolidation" candle profiling** — the request framed the model as a 4-class HTF candle profile. Model11 does not use that taxonomy. It classifies **candle roles** as reversal (candle 2), expansion (candle 3), continuation (candle 4) and classifies **days** in weekly/daily profiles as "consolidated", "opposing run" (shallow / any amount), or "expanded". Do not encode a 4-class candle profiler as sourced content.
5. **Monday rule vs Classic Expansion on Monday** — `p66` says Monday is avoided "in all scenarios"; `p74` (italic) says Classic Expansion logic "applies to a classic expansion weekly profile which forms the reversal on a Monday", with Friday as candle 1. Reconcile: Monday may be the *reversal day* (candle 2) whose CISD is read after the fact; entries are still taken Tue/Wed (candles 3/4), not on Monday.
6. **Stops and targets for Sons, TTRS and Unicorn** are not stated in those decks; only Model11 gives explicit stop (candle-2 swing point) and target (projections, 2R minimum) rules. Applying Model11's stop/target to the other models is an extrapolation.
7. **Sons Model entry element** is not labelled; at 200 dpi the two lines on the 30s/1m/5m entry chart start exactly at the high of the candle before the displacement candle and the low of the candle after it, with no candle body at either line — only the FVG reading fits (the earlier "OB body" alternative is dropped, 2026-09-12). The pullback traverses the whole gap and overshoots below its lower line before the reversal candle closes back above; a stop under the FVG would have been hit.
8. **Timeframe Alignment: 3 panels vs 2-column table** — `TFA p3` shows Bias / Structure / Entry (three TFs) but the pairing table (`p5`) has two columns and the example (`p6`) shows two charts. Whether "Bias" is a third, higher TF or the HTF of the pair is not stated. The example's bottom row prints pairs LTF-over-HTF (`H4/W1 ...`), inverting the table's left/right order — same pairs, different layout.
9. **Failure-swing projection threshold** — "far overextended from any price logical objective" (`p21`) is discretionary; no numeric cutoff.
10. **Monday range statistics** (`p67`) carry an `_amtrades` watermark, give no instrument or unit, and are for an unspecified 3-year window. Treat as anecdotal for non-index instruments.
11. **Killzone timezone** — `TTRS p3` says "Eastern Standard Time (EST)" while Model11 charts use "NYO 8:30" with no zone. In practice these are New York local (ET) clock times; DST handling is not addressed.
12. **Unicorn deck contents numbering** skips "3" (`Unicorn p2`) — cosmetic; the breaker section spans two slides (printed 2 and 3).
13. **Weekly profile "consolidated" / "shallow opposing run" / "large range expansion"** are unquantified; classification is discretionary.
15. **TFA Bias panel — which candle sweeps** (2026-09-12 re-check): the green candle carries the sweep wick; the black candle is the expansion whose high stays below the green high. The previous reading (black candle sweeps) was wrong and would have placed the bias one candle early. See §2.8, §3.6 rule 1.
16. **TTRS breaker box and "three entries"** (2026-09-12 re-check): the breaker box spans the whole pre-sweep swing (both colours), wider than `19. Breaker`'s single-candle box; and the deck draws one confluence pullback through OB line, FVG and breaker, not three sequential retests. See §2.9 step 5, §3.4 rules 4–6. `Unicorn p4` also draws a solid line at the intermediate swing the displacement closes through (the break level), in addition to the dotted swept level.
14. **CISD naming** — Model11 uses "opposing close candles" and "CISD" for the same construction; TFA and TTRS label the same line "CISD" (structure) and "OB" (entry). Treat OB / opposing candle / CISD line as one level with three roles (see `08-ttrades-core-B` §6 item 2).

---

## Adaptation notes (NOT in the PDFs — for crypto 24/7 and commodity CFDs)

- **Economic calendar**: the source itself says Crypto uses **USD as a secondary correlation** (`Model11 p60`); Gold/Silver/Oil are USD-priced and the same USD red-folder filter applies. For Oil add EIA/OPEC events at your discretion (not in source). The CL example (`p100–p114`) is a direct crude-oil application of the OSOK model.
- **Monday rule / weekly profiles**: crypto prints Saturday and Sunday daily candles. The Mon–Fri profile logic (`p72–p81`) needs a mapping decision: either treat the Mon–Fri candles only (ignore weekend candles, as CFD charts do) or treat Sunday as "candle 1" for a Monday reversal. The source gives no guidance; the "no news on Monday" reason still holds, the "smallest range" statistic is unverified for crypto.
- **Daily profiles (London/NY)**: session labels remain meaningful for crypto and commodity CFDs because US/London flow still dominates; convert TTRS killzones (EST) to UTC (add 5h in winter, 4h in summer — DST not addressed by source). For 24/7 crypto, "Asia" (20:00–00:00 EST) is a real session; for CFDs, check broker session breaks (Gold/Silver/Oil have a daily ~1h maintenance gap around 17:00 ET on most brokers) which can distort the "candle 1 / candle 2" hourly logic near the break.
- **Daily candle open**: Model11 uses the futures daily candle (CL/NQ). For crypto the daily close/open is exchange-dependent (00:00 UTC standard); for CFDs use the broker's daily candle — the choice changes which candle is "candle 2".
- **Tick-based P&L labels** (`p90–p93`) are futures ticks; irrelevant to CFD/crypto sizing.
- **SMT** (`TTRS p12`) needs pairs: BTC/ETH/SOL among themselves; Gold/Silver; WTI/Brent (see `08-ttrades-core-B` adaptation notes).
- Everything else (swing candle logic, CISD, projections, EQ framework, order-of-reversal, Sons TF triplets, Unicorn) is price-action-only and applies unchanged.

---

## 7. Machine-readable summary

```yaml
meta:
  source_folder: "docs/TTrades PDFs/"
  files: 6
  physical_pages: 165
  page_citation: "Model11: physical=printed; decks: physical (printed)"
  evidence_tags: {text: "quoted prose", diagram: "read from chart drawing"}
  timezone_note: "TTRS killzones labelled EST; Model11 charts label NY open 'NYO 8:30' (ET); DST not addressed"

shared_definitions:
  candle_numbering:
    candle_1: "candle before the high/low"
    candle_2: "candle that forms the high/low"
    candle_3: "candle after the high/low (expansion)"
    candle_4: "candle after candle 3 (continuation)"
    source: "TTrades Model11.pdf"
    page: "p24"
  candle_2_closure:
    bullish: "candle_2.low < candle_1.low AND candle_2.close > candle_1.low (close back inside candle 1 range)"
    bearish: "candle_2.high > candle_1.high AND candle_2.close < candle_1.high"
    source: "TTrades Model11.pdf"
    page: "p26, p30, p34"
  candle_3_closure_conditional:
    condition: "candle_2 did NOT close back inside candle_1 range"
    rule: "do not participate in candle 3; if candle_3 closes strongly in reversal direction -> swing validated -> candle 4 continuation"
    source: "TTrades Model11.pdf"
    page: "p30-p33"
  opposing_candle_level:
    definition: "open of the first candle of the final same-colour run (highest downclose / lowest upclose); ignore inner runs; must pair with POI (swept high/low, FVG, prior opposing series)"
    source: "TTrades Model11.pdf"
    page: "p5-p10"
  cisd:
    definition: "close through the opposing_candle_level after a sweep / POI touch; level re-marks to newest opposing run if a new extreme prints first"
    source: "TTrades Model11.pdf; Timeframe Alignement TTrades.pdf; TTrades Reversal Sequence (TTRS).pdf"
    page: "Model11 p44-p48, p101, p104, p109-p110; TFA p3-p4 (1-2); TTRS p15 (13)"
  equilibrium_framework:
    reversal_large_wick: "next candle must hold 0.5 of candle_2 wick (upper half bullish / lower half bearish)"
    reversal_no_wick: "next candle must hold 0.5 of candle_2 range"
    continuation: "candle_4 must hold 0.5 of candle_3 range"
    ranges: "into range -> 0.5 is objective; out of range -> 0.5 is POI"
    source: "TTrades Model11.pdf"
    page: "p16-p19, p34-p39"
  projection:
    tool: "fibonacci retracement"
    levels: [1, 0, -1, -2, -2.5, -4, -4.5]
    anchor_manipulation: "1 = manipulation extreme (swept low/high); 0 = previous high that made the highest high (bullish) / previous low that made the lowest low (bearish)"
    anchor_failure_swing: "when manipulation leg is far overextended: 1 = lowest low / highest high; 0 = failure-swing high / low"
    target_zones: {candle_3: "-2 to -2.5", candle_4: "-4 to -4.5 (maximum expansion)"}
    source: "TTrades Model11.pdf"
    page: "p20-p23, p47, p98, p112, p118"
  timeframe_pairs:
    - {htf: "W1", ltf: "H4"}
    - {htf: "D1", ltf: "H1"}
    - {htf: "H4", ltf: "M15"}
    - {htf: "H1", ltf: "M5"}
    - {htf: "M30", ltf: "M3"}
    - {htf: "M15", ltf: "M1"}
    source: "TTrades Model11.pdf; Timeframe Alignement TTrades.pdf"
    page: "Model11 p44, p95; TFA p5 (3)"

models:
  - name: ttrades_osok
    full_name: "TTrades OSOK (one-shot-one-kill) Model"
    timeframe_pairs:
      bias: "D1"
      confirmation: "H1"
      entry: ["M15", "M5", "sub-M5"]
    sequence_steps:
      - "Filter: skip Monday; skip day before CPI/NFP/FOMC-Press; skip sessions before Core PCE/PPI/FOMC-Statement; never hold through releases"
      - "Daily: find candle 2 closure (or conditional candle 3 closure) at a POI; if next daily direction is not one-sided -> no trade"
      - "Weekly profile: classify prior days (consolidated / opposing run / expanded) and match Classic Expansion, Counter-Trend Friday, Midweek Reversal, Consolidation Reversal, Thursday Counter; unclear -> wait one more daily candle"
      - "Hourly: confirm CISD inside daily candle 2 (or on candle 3 for conditional); anchor projection on manipulation leg; mark -2/-2.5, -4/-4.5"
      - "Framework: mark candle-2 wick EQ (or range EQ); after strong candle 3 mark candle-3 range EQ; price must hold correct half"
      - "Daily profile: London reversed -> seek NY continuation; London consolidated / opposing run into POI -> seek NY reversal; London expanded -> no NY"
      - "Intraday: wait for CISD on M15/M5/sub-M5; no CISD -> no entry; new extreme -> re-mark CISD"
      - "Enter (see entry_trigger); stop at candle-2 swing point; take profit >= 2R at projections / liquidity / opposing candles; trail to validated swings"
    entry_trigger:
      opposing_candle: "market at open of first candle after CISD validation, or limit at the opposing candle line"
      candle_2_closure: "enter at open of LTF candle 3"
      candle_3_closure: "enter at open of LTF candle 4"
    invalidation:
      - "candle 2 fails to close back inside candle 1 -> stand aside for candle 3"
      - "following candle violates candle-2 wick/range EQ or candle-3 range EQ"
      - "London expansion -> no NY participation"
      - "weekly profile precondition not met -> no trade that day"
      - "stop: candle-2 swing point hit"
    targets:
      minimum: "2R"
      levels: ["-2/-2.5 projection (candle 3)", "-4/-4.5 projection (candle 4)", "overnight / London / Asia lows or highs", "opposing candles", "opposing swing formations", "counter-trend Friday: 20-50% of weekly range"]
    management: "trail stop to opposing candles / validated swing points; optional third target left for candle-5 continuation while candle-4 range EQ holds"
    weekly_profiles:
      classic_expansion: {c1: "Mon (or prior Fri)", c2: "Tue (or Mon)", c3_c4: "Wed/Thu", precondition: "Mon consolidated or shallow opposing run from weekly open; NOT large expansion"}
      classic_expansion_counter_trend: {c1: "Thu", c2: "Fri (only case trading on c2)", target: "20-50% back into weekly range", precondition: "Mon or Tue reversal expanded through Thu"}
      midweek_reversal: {c1: "Tue", c2: "Wed", c3_c4: "Thu/Fri", precondition: "Mon+Tue consolidated or any opposing run from weekly open; NOT expansion off another reversal"}
      consolidation_reversal: {c1: "Wed", c2: "Thu", c3: "Fri", precondition: "Mon+Tue+Wed consolidated"}
      thursday_counter: {c1: "Wed", c2: "Thu", c3: "Fri", precondition: "Mon+Tue+Wed all expanded same direction"}
    daily_profiles:
      london_reversal: "London reverses -> NY continuation"
      new_york_reversal: "London consolidates / opposing run into POI -> NY reversal; targets London lows, Asia lows, projections"
      invalid: "London expands -> avoid NY"
    news_rules:
      high_impact: ["CPI m/m", "NFP", "FOMC Press Conference"]
      medium_impact: ["Core PCE m/m", "PPI m/m", "FOMC Statement"]
      calendar_currency: {indices: "USD", forex: "USD + cross", crypto: "USD (secondary)"}
    example: "CL1! 26 Apr-1 May 2024 (daily/1H/15m), bearish New York Reversal, targets overnight low then -4"
    source: "TTrades Model11.pdf"
    page: "p60-p94 (rules), p100-p114 (example)"

  - name: ttrades_fractal
    full_name: "TTrades Fractal Model (any timeframe, personal scalping model)"
    timeframe_pairs: "any row of shared_definitions.timeframe_pairs (example H1 -> M5)"
    sequence_steps:
      - "HTF valid candle 2 closure (or conditional candle 3 closure)"
      - "LTF CISD inside HTF candle 2 confirms; annotate; anchor manipulation-leg projection on LTF"
      - "Mark HTF candle-2 wick EQ; price must hold correct half before trading toward objectives"
      - "Entries inside HTF candle 3 from LTF opposing-candle retests and nested LTF candle 2 / candle 3 closures"
      - "After strong HTF candle 3 close: mark candle-3 range EQ; LTF opposing candles inside correct half = POI for candle 4"
      - "Candle 4 continuation to -4 projection = maximum expansion"
    entry_trigger: "same three entry types as ttrades_osok, applied on the LTF; candle-2-closure HTF -> entries in candle 3 and 4; candle-3-closure HTF -> entries in candle 4 only"
    invalidation:
      - "price breaks the wrong half of HTF candle-2 wick EQ / candle-3 range EQ"
      - "no LTF CISD -> no entry"
      - "stop: LTF candle-2 swing point"
    targets: ["-2/-2.5 in candle 3", "-4/-4.5 in candle 4", "2R minimum"]
    example: "NQ1! 20 Jun 2024, 1H candle 2 closure -> 5m CISD -> -4 reached in candle 4 (chart label 08:00)"
    source: "TTrades Model11.pdf"
    page: "p95-p99 (rules), p115-p118 (example)"

  - name: sons_model
    full_name: "ICT Son's Model"
    timeframe_pairs:
      - {dol: "H1 or M15", stop_raid: "M5", entry: "30s"}
    sequence_steps:
      - "DOL TF: identify draw on liquidity (untested swing high for longs) and the opposing swing low to be raided"
      - "Stop-raid TF: candle wicks below prior swing low and closes back above it"
      - "Entry TF: displacement away from the raid leaves an FVG; enter on retrace into it"
    entry_trigger: "retrace into the post-raid FVG on the entry TF [diagram inference]"
    invalidation: "not stated in source; implied: close back below the raid low"
    targets: "draw on liquidity identified in step 1"
    evidence: diagram
    source: "Sons_Model.pdf"
    page: "p3-p5 (1-3)"

  - name: sons_model_htf
    full_name: "ICT Son's Model - HTF variants"
    timeframe_pairs:
      - {dol: "H4 or H1", stop_raid: "M15", entry: "M1"}
      - {dol: "D1 or H4", stop_raid: "H1", entry: "M5"}
    sequence_steps: "identical to sons_model at higher scale"
    entry_trigger: "retrace into the post-raid FVG on the entry TF [diagram inference]"
    invalidation: "not stated in source"
    targets: "draw on liquidity"
    evidence: diagram
    source: "Sons_Model_HTF.pdf"
    page: "p3-p5 (1-3) variant A; p6-p8 (4-6) variant B"

  - name: ttrs_reversal_sequence
    full_name: "TTrades Reversal Sequence (order of reversal)"
    timeframe_pairs:
      entry: ["M15 (patient)", "M1 (impatient)"]
    killzones_est:
      asia: "20:00-00:00"
      london: "02:00-05:00"
      ny_am_forex: "07:00-10:00"
      ny_am_indices: "08:30-11:00"
      london_close_forex: "10:00-12:00"
      ny_pm_indices: "13:30-16:00"
    sequence_steps:
      - "1 turtle soup: prior low (longs) / high (shorts) swept"
      - "2 inversion: prior FVG closed through and retested as support/resistance"
      - "3 cisd/ob: close through open of last opposing-colour run"
      - "4 fvg: displacement FVG retested"
      - "5 breaker: box over the whole pre-sweep swing (swing high -> swept low, both colours) retested; expansion follows"
    entry_trigger: "one retest into the nested step-3/4/5 zone (OB line, FVG, breaker overlap); count as ONE location [diagram, TTRS p17]"
    confluence: ["SMT at the sweep (stronger asset holds higher low)", "OTE retrace 0.62-0.79 (0.705 focus)", "longs from discount (<0.5) / shorts from premium (>0.5)", "inside killzone"]
    invalidation: "not stated in source"
    targets: "not stated in source"
    evidence: diagram (killzones/timeframes text)
    source: "TTrades Reversal Sequence (TTRS).pdf"
    page: "p3 (1) killzones; p4 (2) timeframes; p5-p12 (3-10) concepts; p13-p17 (11-15) order of reversal"

  - name: unicorn
    full_name: "Unicorn Model (Breaker Block + FVG overlap)"
    timeframe_pairs: "not specified"
    sequence_steps:
      - "swing high -> swing low -> higher high (sweep) -> displacement closes below swing low (bearish); mirror bullish"
      - "breaker box on candles that formed the intermediate swing"
      - "displacement candle leaves FVG overlapping the breaker box"
      - "retrace into overlap zone -> continuation"
    entry_trigger: "retrace into breaker+FVG overlap [diagram]"
    invalidation: "not stated in source (see 19. BreakerBlocks stop options in 08-ttrades-core-B)"
    targets: "not stated in source"
    must_have: "FVG range overlaps breaker box; otherwise plain breaker"
    evidence: diagram
    source: "Unicorn_Model.pdf"
    page: "p3 (1) FVG; p4-p5 (2-3) breaker; p6 (4) unicorn"

  - name: timeframe_alignment
    full_name: "Timeframe Alignment (top-down: bias -> structure -> entry)"
    timeframe_pairs: "shared_definitions.timeframe_pairs"
    sequence_steps:
      - "Bias: HTF sweep-and-reject candle (long wick) followed by a full-bodied expansion candle closing beyond it -> expect the next candle to continue; decided after the expansion candle closes (TFA p3)"
      - "Structure: sweep + CISD on the paired LTF at the key level"
      - "Entry: OB/CISD retest on the entry TF; risk box beyond OB, reward toward draw"
    entry_trigger: "LTF close through the OB line (CISD), then a wick retest of the line without a close back beyond it [diagram, TFA p3 Entry panel]"
    invalidation: "not stated; implied: close beyond OB / risk box"
    targets: "not stated; reward box drawn toward the draw"
    ambiguity: "3 panels (bias/structure/entry) vs 2-column pairing table; example prints pairs LTF-over-HTF"
    evidence: diagram
    source: "Timeframe Alignement TTrades.pdf"
    page: "p3 (1) top-down; p4-p5 (2-3) alignment + table; p6 (4) example"
```
